"""兵庫県動物愛護センター rule-based adapter

対象ドメイン: https://hyogo-douai.sakura.ne.jp/

特徴:
- ホームページ・ビルダー (HPB) で生成された静的サイト。
  WordPress ではなく、`shuuyou.html` 1 ページに本所 (センター) と
  4 支所 (三木 / 龍野 / 但馬 / 淡路) × (犬 / 猫) の収容状況サマリー
  テーブル (`#sp-table-7`) が掲載される。
- サマリーテーブルの各セルには「収容あり」を示すマーク (〇) と
  支所別詳細ページへのリンク (`<a href="hogo3.html">`,
  `<a href="hogo5.html">`) が入る。マークのみで詳細リンクが
  無い支所は、詳細ページが用意されていない (本所 / 三木支所 等)。
- 一覧 → 詳細 (list+detail) 構造として `WordPressListAdapter`
  ベースで実装する。一覧ページからは `hogo*.html` への
  `<a>` を集めて detail URL とし、詳細ページの実体は
  `<th>項目名</th><td>値</td>` 形式の HPB 標準テーブルを想定して
  ラベル一致で各フィールドを抽出する。
- 在庫 0 件 (どの支所もマークが立っていない) の状態が日常的に
  発生し得るため、`fetch_animal_list` で detail link 0 件のときは
  `ParsingError` ではなく空リストを返す。
- 動物写真は HPB 既定の `img/` 相対パス配下に置かれる想定で、
  `/wp-content/uploads/` を期待する基底 `_filter_image_urls` の
  uploads フィルタは機能しない。フィルタが空集合になった場合は
  元リストを返すフェイルセーフがあるため挙動は崩れない。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class HyogoDouaiAdapter(WordPressListAdapter):
    """兵庫県動物愛護センター用 rule-based adapter

    `shuuyou.html` のサマリーテーブル `#sp-table-7` 配下に並ぶ
    `<a href="hogo*.html">` を detail link として収集する list+detail 形式。
    """

    # サマリーテーブル `#sp-table-7` の `<td>` 内に並ぶ
    # `hogo*.html` 形式のリンクのみを対象にする。
    # ヘッダ/フッタのナビゲーションリンク (例: `inunekonojyouhou.html`,
    # `keihatsu_maigo.html` 等) や外部参照リンク (神戸市/姫路市等) を
    # 確実に除外するためスコープを限定する。
    LIST_LINK_SELECTOR: ClassVar[str] = "#sp-table-7 td a[href*='hogo']"

    # 詳細ページ (`hogo*.html`) の HPB 標準テーブル
    # (`<th>項目名</th><td>値</td>`) のラベルに合わせる。
    # 同一サイト内の他ページで使われる典型ラベルを採用しており、
    # ヒットしない場合は空文字列となる (RawAnimalData 上は許容)。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬")。
        # ラベルが無いケースでは空となるが、`extract_animal_details`
        # 側でサイト名から推定する (本所はそもそも犬猫サマリー上
        # 「犬」「猫」の行で分かれる)。
        "species": FieldSpec(label="種類"),
        # 性別
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "成犬", "推定2歳")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 体格 / 大きさ
        "size": FieldSpec(label="大きさ"),
        # 収容日 (HPB 標準では「収容年月日」のことも)
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所 (本所 / 各支所名)
        "location": FieldSpec(label="収容場所"),
        # 連絡先 (電話番号)
        "phone": FieldSpec(label="連絡先"),
    }

    # HPB 既定の `img/<file>.jpg` 相対参照を拾う。
    # 基底 `_filter_image_urls` は uploads パスを優先するが、
    # 該当が 0 件のときは元リストを返すため、HPB 構造でも
    # 動物写真 URL がそのまま残る。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、本サイトは
        在庫 0 件の状態が日常的に発生し得る (どの支所も収容なし)。
        link が 0 件の場合は ParsingError ではなく空リストを返す。

        サマリーテーブルそのものが見つからない (テンプレート崩壊)
        場合は ParsingError を出す。
        """
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        # 本文サマリーテーブルが完全に消えていれば異常状態として例外
        if soup.select_one("#sp-table-7") is None:
            raise ParsingError(
                "サマリーテーブル (#sp-table-7) が見つかりません",
                selector="#sp-table-7",
                url=self.site_config.list_url,
            )

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            return []

        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
        for link in links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "sheltered") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に対し以下の兵庫県動物愛護センター固有処理を加える:
        - species がラベル抽出で取れない場合、URL パス / サイト名から
          「犬」「猫」を推定する (HPB の hogo*.html は通常、犬または
          猫のどちらかの一覧ページとして運用される)。
        - 1 フィールドも抽出できなかった場合は ParsingError。
        """
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            value = self._extract_field(soup, spec)
            fields[name] = value

        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

        # species 補完: 空の場合は URL パス → サイト名 の順で推定
        if not fields.get("species"):
            inferred = self._infer_species_from_url(
                detail_url
            ) or self._infer_species_from_site_name(self.site_config.name)
            if inferred:
                fields["species"] = inferred

        image_urls = self._extract_images(soup, detail_url)

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_url(url: str) -> str:
        """URL パスに含まれる単語から動物種別を推定する

        HPB 系では URL に直接「dog」「cat」が入ることは稀だが、
        将来 hogo3_dog.html 等のスラッグ運用に切り替わったケースに
        備えてフォールバックを残す。
        """
        lowered = url.lower()
        if "dog" in lowered or "inu" in lowered:
            return "犬"
        if "cat" in lowered or "neko" in lowered:
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の name と完全一致で登録する。
_SITE_NAME = "兵庫県動物愛護センター（収容動物）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, HyogoDouaiAdapter)
