"""岡山市保護動物情報サイト rule-based adapter

対象ドメイン: https://www.city.okayama.jp/kurashi/category/1-15-1-0-0-0-0-0-0-0.html

特徴:
- 岡山市公式 CMS のカテゴリページに、保護犬・保護猫の個別記事リンクが
  日付付きで列挙されている list + detail 構造。
- 一覧ページ本文の `<ul class="category_end">` 配下の `<li>` 各要素が
  1 件 = 1 動物 (もしくは 1 件のお知らせ記事) を表し、
  `<a href="./../0000067714.html">1D2026023保護犬個別情報</a>` のように
  10 桁数字 + `.html` の記事 URL がリンクされている。
- サイドメニュー (`aside.page_right`) や「同じ階層の情報」リスト、
  パンくず・グローバルナビにも `/kurashi/...` のリンクが多数あるため、
  本文エリアの `ul.category_end` に絞ることでサイドリンクの混入を防ぐ。
- お知らせ記事 (例: 「保護犬の人馴れ訓練プロジェクト」「岡山市保護猫情報」
  「保護犬情報一覧」) も同じ `<ul>` に並ぶため、URL からの完全な動物/
  お知らせ判定はできない。本 adapter は detail URL を一覧として返し、
  detail ページ抽出時に 1 フィールドも取れない場合 (お知らせ記事等) は
  `ParsingError` を出す既定動作に任せる。
- 詳細ページの実 HTML は本リポジトリ内に fixture として入手できていない
  ため、自治体 CMS 共通で多用される `<th>項目名</th><td>値</td>` の
  テーブル、または `<dt>項目名</dt><dd>値</dd>` の定義リストいずれかで
  各フィールドが並ぶ前提で `WordPressListAdapter` の既定実装に乗せる。
  さらに `<th>` を持たない 2 カラムテーブル
  (`<td>label</td><td>value</td>`) にもフォールバックする。
- 動物種別 (species) はラベル抽出を優先し、空のときは記事タイトル
  (例: "1D2026023保護犬個別情報") またはサイト名から「犬/猫」を推定する。
- 在庫 0 件 (記事リンク 0 件) のときは ParsingError ではなく空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class CityOkayamaAdapter(WordPressListAdapter):
    """岡山市保護動物情報 rule-based adapter

    list_url 本文の `ul.category_end` 配下から detail URL を抽出し、
    各 detail ページの定義リスト/テーブルから RawAnimalData を構築する。
    """

    # 一覧ページ本文の記事リスト `<ul class="category_end">` 配下の
    # `<a>` のみを拾う。サイドメニュー (`aside.page_right`) やパンくず・
    # グローバルナビの同種リンクは `ul.category_end` 配下ではないため
    # 自然に除外される。
    LIST_LINK_SELECTOR: ClassVar[str] = "ul.category_end li a"

    # detail ページの想定ラベル。実 HTML が入手できていないため、
    # 自治体 CMS 共通で見られる一般的な見出しを採用する。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬", "三毛")
        "species": FieldSpec(label="種類"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "成犬", "子犬", "推定3歳")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 収容日 / 保護日
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所 / 発見場所
        "location": FieldSpec(label="収容場所"),
        # 連絡先 (電話番号)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は detail ページ内 `<img>` から拾い、テンプレート由来
    # (/css/img/, /design_img/, /images/, favicon 等) を除外する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # 詳細記事 URL の典型パターン: 10 桁数字 + `.html`
    # 例: "/kurashi/0000067714.html", "./../0000067714.html"
    _ARTICLE_HREF_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"/?\d{10}\.html$"
    )

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、本サイトは
        在庫 0 件 (お知らせ記事も無い) の状態も想定し得るため、link が
        0 件の場合は空リストを返す。
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
            # 念のため、10 桁数字 + .html の記事リンクのみ採用する。
            # `category/...` のカテゴリトップへのリンクが混入することを防ぐ。
            if not self._ARTICLE_HREF_RE.search(href):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(
        self, detail_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の岡山市固有処理を行う:
        - species (動物種別) はラベル抽出を優先し、空のときは
          ページタイトル ("1D2026023保護犬個別情報" 等) または
          site_config.name から「犬/猫」を推定する。
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

        # species 補完: 空のときはページタイトル、サイト名の順で推定
        if not fields.get("species"):
            title_text = ""
            title_el = soup.find("title")
            if isinstance(title_el, Tag):
                title_text = title_el.get_text(strip=True)
            h1_el = soup.find("h1")
            if isinstance(h1_el, Tag):
                title_text = f"{title_text} {h1_el.get_text(strip=True)}"
            inferred = self._infer_species_from_text(title_text)
            if not inferred:
                inferred = self._infer_species_from_text(self.site_config.name)
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
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す

        本サイトの詳細ページは実 HTML が入手できていないが、自治体 CMS では
        `<th>` を持たない 2 列テーブル (左 td: ラベル, 右 td: 値) も
        頻出するため、フォールバックとして対応する
        (city_oita / city_kumamoto と同等の方針)。
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
        """テンプレート (/css/, /design_img/, /images/) の装飾画像を除外する

        岡山市 CMS は `/css/img/`, `/design_img/`, `/images/` 配下に
        ロゴ・装飾画像を置いているため、これらを除外したリストを返す。
        除外後に 0 件になった場合は元リストを返す (フェイルセーフ)。
        """
        filtered = [
            u for u in urls
            if "/css/img/" not in u
            and "/css/" not in u
            and "/design_img/" not in u
            and "/images/clearspacer" not in u
            and not u.endswith(".ico")
            and not u.endswith(".gif")
        ]
        return filtered if filtered else urls

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_text(text: str) -> str:
        """テキスト ("...保護犬..." / "保護猫..." / "岡山市（保護動物情報）" 等)
        から動物種別を推定する

        - "犬" を含み "猫" を含まない → "犬"
        - "猫" を含み "犬" を含まない → "猫"
        - 両方含む / どちらも含まない → ""
        """
        if not text:
            return ""
        has_dog = bool(re.search(r"犬", text))
        has_cat = bool(re.search(r"猫", text))
        if has_dog and not has_cat:
            return "犬"
        if has_cat and not has_dog:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# `sites.yaml` の `name` フィールドと完全一致するサイト名で登録する。
for _site_name in ("岡山市（保護動物情報）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityOkayamaAdapter)
