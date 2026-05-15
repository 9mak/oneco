"""大分市犬の保護収容情報サイト rule-based adapter

対象ドメイン: https://www.city.oita.oita.jp/kurashi/pet/inunohogo/index.html

特徴:
- 大分市公式 CMS (`tmp_*` テンプレート) で構築された静的 list + detail 構造。
- 一覧ページ本文 (`<div id="tmp_contents">`) 内に
  `<ul><li><a href="/oNNN/kurashi/pet/NNNNNNNNNNNNN.html">{タイトル} (YYYY年M月D日 登録)</a></li></ul>`
  形式で個別記事 (詳細ページ) へのリンクが並ぶ。
  サイドメニュー (`<div id="tmp_lnavi">`) や パンくず・グローバルナビにも
  `/kurashi/pet/...` の自身を含むリンクが多数あるため、本文エリア
  (`#tmp_contents`) 限定のセレクタで詳細リンクのみを抽出する。
- 詳細ページの実 HTML は本リポジトリ内に fixture として入手できていない
  ため、自治体 CMS 共通で多用される `<th>項目名</th><td>値</td>` の
  テーブル、または `<dt>項目名</dt><dd>値</dd>` の定義リストいずれかで
  各フィールドが並ぶ前提で `WordPressListAdapter` の既定実装に乗せる。
  さらに `<th>` を持たない 2 カラムテーブル
  (`<td>label</td><td>value</td>`) にもフォールバックする。
- 動物種別 (species) はラベル抽出を優先し、空のときはサイト名
  ("大分市（保護犬）") から「犬」を推定する。
- 在庫 0 件の状態 (お知らせ記事のみで動物個別記事 0 件) も発生し得るため、
  一覧ページから 1 件も詳細リンクが拾えなかった場合は ParsingError ではなく
  空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class CityOitaAdapter(WordPressListAdapter):
    """大分市犬の保護収容情報 rule-based adapter

    list_url 本文エリアから `/oNNN/kurashi/pet/...` の詳細リンクを抽出し、
    各 detail ページの定義リスト/テーブルから RawAnimalData を構築する。
    """

    # 一覧ページ本文 (`#tmp_contents`) 内の `/kurashi/pet/` 配下リンクを抽出。
    # サイドメニュー (`#tmp_lnavi`) やパンくず・グローバルナビの同種リンクは
    # `#tmp_contents` 配下ではないため自然に除外される。
    LIST_LINK_SELECTOR: ClassVar[str] = "#tmp_contents a[href*='/kurashi/pet/']"

    # detail ページの想定ラベル。実 HTML が入手できていないため、自治体 CMS
    # 共通で見られる一般的な見出し ("品種"/"性別"/"毛色"/"収容日"/
    # "収容場所"/"連絡先") を採用する。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬")
        "species": FieldSpec(label="品種"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "成犬", "子犬", "推定3歳")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 収容日 / 保護日
        "shelter_date": FieldSpec(label="保護日"),
        # 収容場所 / 発見場所
        "location": FieldSpec(label="場所"),
        # 連絡先 (電話番号)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は detail ページ内 `<img>` から拾い、テンプレート由来
    # (/shared/images/, favicon 等) を除外する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # 詳細記事 URL の典型パターン: `/oNNN/kurashi/pet/NNNNNNNNNNNNN.html`
    # サイドメニュー等の `/kurashi/pet/{slug}/index.html` を二重に弾くために用いる。
    _ARTICLE_HREF_RE: ClassVar[re.Pattern[str]] = re.compile(r"/o\d+/kurashi/pet/\d+\.html$")

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、本サイトは
        在庫 0 件の状態 (お知らせ記事のみ掲載されない時期) も発生し得る。
        link が 0 件の場合は空リストを返す。
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
            # 本文エリア内であっても、まれに `/kurashi/pet/{slug}/index.html`
            # のようなカテゴリトップへのリンクが混在する可能性があるため、
            # `/oNNN/kurashi/pet/NNNNNNNNNNNNN.html` 形式の記事リンクのみ採用する。
            if not self._ARTICLE_HREF_RE.search(href):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の大分市固有処理を行う:
        - species (動物種別) はラベル抽出を優先し、空のときは
          site_config.name ("大分市（保護犬）") から「犬」を推定する。
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

        # species 補完: 空の場合はサイト名から推定 (大分市は犬専用サイト)
        if not fields.get("species"):
            inferred = self._infer_species_from_site_name(self.site_config.name)
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

    # ─────────────────── 抽出ヘルパー拡張 ───────────────────

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す

        本サイトの詳細ページは実 HTML が入手できていないが、自治体 CMS では
        `<th>` を持たない 2 列テーブル (左 td: ラベル, 右 td: 値) も
        頻出するため、フォールバックとして対応する
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

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """テンプレート (/shared/) の装飾画像を除外する

        大分市 CMS は `/shared/images/` 配下にロゴ・装飾画像を置いているため、
        これらを除外したリストを返す。除外後に 0 件になった場合は元リストを
        返す (フェイルセーフ)。
        """
        filtered = [
            u
            for u in urls
            if "/shared/images/" not in u and "/shared/style/" not in u and not u.endswith(".ico")
        ]
        return filtered if filtered else urls

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("大分市（保護犬）" 等) から動物種別を推定する

        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - 両方含む → "その他"
        - いずれにも該当しない → ""
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
# `sites.yaml` の `name` フィールドと完全一致するサイト名で登録する。
for _site_name in ("大分市（保護犬）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityOitaAdapter)
