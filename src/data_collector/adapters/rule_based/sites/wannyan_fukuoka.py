"""福岡市わんにゃんよかネット (wannyan.city.fukuoka.lg.jp) rule-based adapter

対象ドメイン: https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/

特徴:
- 福岡市保健福祉局の動物管理情報サイト。一覧ページは
  `?type_id={1=犬,2=猫}&sorting_id={4=保護,5=譲渡}` の URL パラメータで
  4 種類のビュー (犬保護中 / 猫保護中 / 犬譲渡 / 猫譲渡) を切り替える。
- ページ全体が JavaScript で動的に描画される SPA 構造のため、`requests`
  ベースの fetch では一覧テーブルが空 HTML として返る。本 adapter は
  `PlaywrightFetchMixin` を組み合わせて JS 実行後の HTML を取得する。
- 一覧ページは `<table>` の各 `<tr>` に「番号 / 写真 / 収容日 / 状況 /
  区 / 場所 / その他特徴 / 詳細」の列が並び、最後の「詳細」セルに
  detail ページへの `<a href="/yokanet/animal/animal_posts/view/...">`
  リンクが置かれる。これを `a[href*='/animal_posts/view']` で抽出する。
- 在庫 0 件の状態 (例えば 2026 年時点では「データが見つかりませんでした」
  表示) が常態的に発生し得るため、一覧ページから 1 件も詳細リンクが
  拾えなかった場合は ParsingError ではなく空リストを返す。
- 動物種別 (species) はラベル抽出を優先し、空のときは list URL の
  `type_id=1` (犬) / `type_id=2` (猫) パラメータから推定する。

カバーサイト (4):
- 福岡市わんにゃん（犬保護中）
- 福岡市わんにゃん（猫保護中）
- 福岡市わんにゃん（犬譲渡）
- 福岡市わんにゃん（猫譲渡）
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class WannyanFukuokaAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """福岡市わんにゃんよかネット 共通 rule-based adapter

    4 サイト (犬保護中 / 猫保護中 / 犬譲渡 / 猫譲渡) を共通テンプレートで
    扱う。`type_id` パラメータで動物種別を、`sorting_id` で保護/譲渡を
    判定する (URL 解析は species 推定でのみ利用)。

    JavaScript で一覧テーブルが描画されるため、`PlaywrightFetchMixin` を
    第一基底に配置して `_http_get` を Playwright 版で上書きする。
    """

    # Playwright が一覧テーブルの描画完了を待つセレクタ。
    # わんにゃんよかネットは <table> 配下に動物の <tr> 行を JS で挿入する。
    # 0 件のときは「データが見つかりませんでした。」のメッセージのみ表示
    # されるが、いずれにせよ <table> 自体は静的 HTML に存在する想定。
    WAIT_SELECTOR: ClassVar[str | None] = "table"

    # 一覧ページの「詳細」列に置かれる detail リンクを抽出する。
    # `/yokanet/animal/animal_posts/view/{ID}` 形式の href を持つ <a> のみ
    # 拾い、サイドメニュー (`/index`) やヘッダ (`/yokanet/static/...`) などの
    # ナビゲーションリンクは自然に除外される。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href*='/animal_posts/view']"

    # detail ページの想定ラベル。実 HTML が安定して入手できないため、
    # 福岡市の動物管理票で一般的な見出し ("品種"/"性別"/"毛色"/"収容日"/
    # "場所"/"特徴"/"連絡先") を採用する。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬", "三毛猫")
        "species": FieldSpec(label="品種"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 推定年齢 (例: "成犬", "推定3歳")
        "age": FieldSpec(label="推定年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 収容日 / 保護日
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所 (発見場所 / 区)
        "location": FieldSpec(label="場所"),
        # 連絡先 (区の保健福祉センター / 動物愛護管理センターの電話)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は detail ページ内 `<img>` から拾い、テンプレート由来
    # (common/, header/, footer/, logo) を除外する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、本サイトは
        在庫 0 件の状態 (「データが見つかりませんでした」表示) が日常的に
        発生し得るため、link が 0 件の場合は空リストを返す。
        """
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

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

    def extract_animal_details(
        self, detail_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の福岡市固有処理を行う:
        - species (動物種別) はラベル抽出を優先し、空のときは
          detail URL → site_config.list_url → site_config.name の順で
          `type_id=1`/`type_id=2` または「犬」「猫」の語から推定する。
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

        # species 補完: 空の場合は detail URL → list URL → site name の順で推定
        if not fields.get("species"):
            inferred = (
                self._infer_species_from_url(detail_url)
                or self._infer_species_from_url(self.site_config.list_url)
                or self._infer_species_from_site_name(self.site_config.name)
            )
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
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=detail_url
            ) from e

    # ─────────────────── 抽出ヘルパー拡張 ───────────────────

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` 2 列も探す

        福岡市の detail ページが `<th>` 無しの 2 列テーブル
        (左 td: ラベル, 右 td: 値) で組まれているケースにも対応する
        (city_kumamoto / yokosuka_doubutu と同等の方針)。
        """
        # まず基底の dl / th-td パターンを試す
        value = super()._extract_by_label(soup, label)
        if value:
            return value

        # フォールバック: <td>label</td><td>value</td> の 2 列テーブル
        for td in soup.find_all("td"):
            if not isinstance(td, Tag):
                continue
            cell_text = td.get_text(strip=True)
            if not cell_text or label not in cell_text:
                continue
            sibling = td.find_next_sibling("td")
            if sibling is None:
                continue
            sibling_text = sibling.get_text(strip=True)
            if sibling_text:
                return sibling_text
        return ""

    def _filter_image_urls(
        self, urls: list[str], base_url: str
    ) -> list[str]:
        """テンプレート由来 (header/footer/logo/common) の装飾画像を除外する

        除外後に 0 件になった場合は元リストを返す (フェイルセーフ)。
        """
        filtered = [
            u for u in urls
            if "/common/" not in u
            and "/header/" not in u
            and "/footer/" not in u
            and "logo" not in u.lower()
            and "icon" not in u.lower()
        ]
        return filtered if filtered else urls

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_url(url: str) -> str:
        """URL クエリ `type_id=1` (犬) / `type_id=2` (猫) から動物種別を推定

        - `type_id=1` を含む → "犬"
        - `type_id=2` を含む → "猫"
        - それ以外 → ""
        """
        if not url:
            return ""
        if "type_id=1" in url:
            return "犬"
        if "type_id=2" in url:
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 (例: "福岡市わんにゃん（犬保護中）") から動物種別を推定

        - 「犬」と「猫」両方含む → "その他"
        - 「犬」のみ → "犬"
        - 「猫」のみ → "猫"
        - それ以外 → ""
        """
        has_dog = bool(re.search(r"犬", name))
        has_cat = bool(re.search(r"猫", name))
        if has_dog and has_cat:
            return "その他"
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name` フィールドと完全一致する 4 サイト名で登録する。
for _site_name in (
    "福岡市わんにゃん（犬保護中）",
    "福岡市わんにゃん（猫保護中）",
    "福岡市わんにゃん（犬譲渡）",
    "福岡市わんにゃん（猫譲渡）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, WannyanFukuokaAdapter)
