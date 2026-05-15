"""高松市 わんにゃん高松 rule-based adapter

対象ドメイン: https://www.city.takamatsu.kagawa.jp/udanimo/

特徴:
- 静的 HTML + jQuery で動的にテーブル行を組み立てる構成。
  一覧ページ (`ani_infolist1.html?infotype=1&animaltype=1|2`) は
  `<table id="hoken_tbl">` (保健所からの情報) と `<table id="ippan_tbl">`
  (一般からの情報) の 2 ブロックを持ち、サーバから取得した在庫データを
  JS が `<tr>` として追加挿入する。
- 各行の「詳細」セルに `ani_infodetail1.html?infoid=XXXX` 形式の
  リンクが張られるため、`a[href*='ani_infodetail']` で detail URL を
  抽出する。
- **在庫 0 件の場合 (本フィクスチャがこのケース)**: 両テーブルとも
  `<tr class="ttr">` (見出し行) しか持たない静的 HTML となる。
  この状態は ParsingError ではなく "0 件" として扱い、
  `fetch_animal_list` は空リストを返す。
- 同一テンプレート上で 2 サイト (収容中犬 / 収容中猫) を運用しており、
  URL クエリ `animaltype=1` (犬) / `animaltype=2` (猫) / `animaltype=3`
  (その他) で切り替わる。動物種別はこの URL クエリから判定し、
  サイト名 (「収容中犬」「収容中猫」) を補助的なフォールバックとする。
- 詳細ページ (`ani_infodetail1.html?infoid=XXXX`) は実際の HTML 構造が
  入手できていないため、一覧表のカラム (収容日 / No. / 写真 / 収容場所 /
  品種 / 毛色 / 性別) に対応するラベル付きの `<th>/<td>` または
  `<dt>/<dd>` のいずれかで値が並ぶ前提で `WordPressListAdapter` の
  既定実装に乗せる。さらに 2 カラムテーブル (`<td>label</td><td>value</td>`)
  にもフォールバックする。
"""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class CityTakamatsuKagawaAdapter(WordPressListAdapter):
    """高松市 わんにゃん高松 共通 rule-based adapter

    収容中犬 / 収容中猫 の 2 サイトで共通テンプレートを使用する。
    URL クエリ `animaltype` で動物種別を判定する。
    """

    # 一覧ページ内の `ani_infodetail1.html?infoid=XXXX` への遷移リンクを抽出。
    # サイドメニューの `ani_infolist1.html?...` (一覧切替) や
    # ヘッダ/フッタの遷移リンクは混入しないセレクタになっている。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href*='ani_infodetail']"

    # detail ページの想定ラベル。一覧表のカラム見出しと同等。
    # 実 HTML が入手できていないためラベルは複数候補を持たず、
    # 一般的な命名 (「品種」「毛色」「性別」「収容日」「収容場所」) を採用する。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬")
        "species": FieldSpec(label="品種"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "成犬", "推定3歳")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 収容日
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所
        "location": FieldSpec(label="収容場所"),
        # 連絡先 (本文ラベル経由)。本文に無い場合は extract_animal_details
        # 側でフッタの `<span id="katelno">` から全角数字を補完する。
        "phone": FieldSpec(label="連絡先"),
    }

    # フッタの問合せ先電話番号 (高松市保健所 生活衛生課)。
    # `<span id="katelno">０８７－８３９－２８６５</span>` の形で全角数字
    # で記載されているため、半角化してから `_normalize_phone` に渡す。
    _FOOTER_PHONE_SELECTOR: ClassVar[str] = "#katelno"

    # 動物写真は詳細ページ内 `<img>` のうち、テンプレート由来 (common/image
    # 配下のロゴ・装飾画像) を除外したものを採用する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、高松市の
        わんにゃん高松サイトは在庫 0 件の状態が日常的に発生する
        (一覧テーブルの `<tbody>` には見出し行 `<tr class="ttr">` しか
        無く、データ行は JS でサーバから動的に追加される)。
        link が 0 件の場合は空リストを返し、ページャ等の自然な 0 件状態
        として扱う。
        """
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            # 在庫 0 件 (テンプレートが正常に表示されている状態) として扱う
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

        基底実装に加え、以下の高松市固有処理を行う:
        - 種類 (species) はラベル抽出を優先し、空のときは
          一覧 URL (`site_config.list_url`) または detail URL の
          `animaltype` クエリから推定する (1=犬, 2=猫, 3=その他)。
        - 0 件 (= 1 フィールドも抽出できない) のときは ParsingError。
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

        # phone 補完: 本文に「連絡先」ラベルが無いケースでは
        # フッタの `<span id="katelno">` から全角数字の電話番号を拾う。
        if not fields.get("phone"):
            footer = soup.select_one(self._FOOTER_PHONE_SELECTOR)
            if footer is not None:
                fields["phone"] = self._zenkaku_to_hankaku(
                    footer.get_text(strip=True)
                )

        # species 補完: 抽出値が空の場合は URL クエリ → サイト名の順で推定
        if not fields.get("species"):
            inferred = self._infer_species_from_url(
                detail_url
            ) or self._infer_species_from_url(
                self.site_config.list_url
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
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=detail_url
            ) from e

    # ─────────────────── 拡張: 抽出ヘルパー ───────────────────

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す

        高松市の CMS テンプレートは `<table>` を多用しており、
        詳細ページの実 HTML が入手できていないため、`<th>` を持たない
        2 列テーブル (左 td: ラベル, 右 td: 値) でも値が拾えるように
        フォールバックを追加する (yokosuka_doubutu と同等の方針)。
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
        """高松市テンプレート (common/image/) の装飾画像を除外する

        高松市の HTML はロゴ・ナビゲーション画像を `common/image/` 配下に
        置いているため、これらを除外したリストを返す。除外後に 0 件に
        なった場合は元リストを返す (フェイルセーフ)。
        """
        filtered = [u for u in urls if "/common/image/" not in u]
        return filtered if filtered else urls

    # ─────────────────── 全角→半角 変換 ───────────────────

    @staticmethod
    def _zenkaku_to_hankaku(text: str) -> str:
        """全角数字・全角ハイフン (U+FF10-FF19, U+FF0D 等) を半角に変換する

        高松市フッタの電話番号は `０８７－８３９－２８６５` のように
        全角数字 + 全角ハイフンで記載されているため、`_normalize_phone`
        の半角ベース正規表現が走るように事前変換する。
        - 全角数字 (U+FF10-U+FF19) → 半角数字 (U+0030-U+0039)
        - 全角ハイフン類 (U+FF0D, U+2212, U+30FC) → 半角ハイフン (U+002D)
        """
        if not text:
            return text
        # 全角数字 → 半角
        translated = text.translate(
            str.maketrans(
                "０１２３４５６７８９",
                "0123456789",
            )
        )
        # ハイフン類 (全角ハイフン/マイナス/長音記号) → 半角ハイフン
        for ch in ("－", "−", "ー"):
            translated = translated.replace(ch, "-")
        return translated

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_url(url: str) -> str:
        """URL クエリ `animaltype=1|2|3` から動物種別を推定する

        - `animaltype=1` → "犬"
        - `animaltype=2` → "猫"
        - `animaltype=3` → "その他"
        - それ以外 / クエリ無し → ""
        """
        if not url:
            return ""
        try:
            qs = parse_qs(urlparse(url).query)
        except ValueError:
            return ""
        values = qs.get("animaltype", [])
        if not values:
            return ""
        v = values[0]
        if v == "1":
            return "犬"
        if v == "2":
            return "猫"
        if v == "3":
            return "その他"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("収容中犬" / "収容中猫") から動物種別を推定する

        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - いずれにも該当しない → ""
        """
        # 「犬猫」の包含順を考慮して、両方含むケースは「その他」扱い
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
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 香川県` かつ `city.takamatsu.kagawa.jp`
# ドメインのもの。
for _site_name in (
    "高松市 わんにゃん高松（収容中犬）",
    "高松市 わんにゃん高松（収容中猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityTakamatsuKagawaAdapter)
