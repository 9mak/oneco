"""熊本市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.kumamoto.jp/doubutuaigo/

特徴:
- ASP.NET 製の自治体公式 CMS で構築された静的 list + detail 構造。
- 同一テンプレートで 2 サイト (迷子犬一覧 / 迷子猫一覧) が運用されており、
  URL のパス末尾 (`list03612.html` = 迷子犬, `list03615.html` = 迷子猫)
  だけが異なるため 1 つのアダプタで両方を扱う。
- 一覧ページは `<ul class="kijilist">` 配下の
  `<li class="loadbox"><div class="title"><a href=".../doubutuaigo/kijiNNNNNNNN/index.html">`
  形式で個別記事 (詳細ページ) へのリンクを並べる。サイドメニューや関連
  リンクが同ページ内に多数あるため、`a[href*='/doubutuaigo/kiji']` の
  href 部分一致で詳細リンクのみを抽出する。
- 詳細ページの実 HTML は本リポジトリ内に fixture として入手できていない
  ため、自治体 CMS 共通で多用される `<th>項目名</th><td>値</td>` の
  テーブル、または `<dt>項目名</dt><dd>値</dd>` の定義リストいずれかで
  各フィールドが並ぶ前提で `WordPressListAdapter` の既定実装に乗せる。
  さらに `<th>` を持たない 2 カラムテーブル
  (`<td>label</td><td>value</td>`) にもフォールバックする。
- 動物種別 (species) はラベル抽出を優先し、空のときは
  list URL のパス (`list03612` = 犬, `list03615` = 猫) または
  サイト名 ("迷子犬一覧" / "迷子猫一覧") から推定する。
- 在庫 0 件の状態が定常的に発生し得るため、一覧ページから 1 件も
  詳細リンクが拾えなかった場合は ParsingError ではなく空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class CityKumamotoAdapter(WordPressListAdapter):
    """熊本市動物愛護センター 共通 rule-based adapter

    迷子犬一覧 / 迷子猫一覧 の 2 サイトで共通テンプレートを使用する。
    list URL パス (`list03612` / `list03615`) で動物種別を判定する。
    """

    # 一覧ページの記事リンク (`/doubutuaigo/kijiNNNNNNNN/index.html`) を抽出。
    # ヘッダ・サイドメニュー・フッタの `/doubutuaigo/listNNNNN.html` 等の
    # カテゴリ遷移リンクは href が `/kiji` を含まないため自然に除外される。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href*='/doubutuaigo/kiji']"

    # detail ページの想定ラベル。実 HTML が入手できていないため、
    # 自治体 CMS 共通で見られる一般的な見出し ("品種"/"性別"/"毛色"/
    # "収容日"/"収容場所"/"連絡先") を採用する。
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
    # (common/images/, doubutuaigo/common/images/) を除外する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、本サイトは
        在庫 0 件の状態が日常的に発生し得る (テンプレートだけが残り
        記事リンクが 0 件)。link が 0 件の場合は空リストを返す。
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
        self, detail_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の熊本市固有処理を行う:
        - species (動物種別) はラベル抽出を優先し、空のときは
          detail URL → site_config.list_url → site_config.name の順で
          パス・名称ベースに「犬」「猫」を推定する。
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

        # species 補完: 空の場合は URL パス → list URL → site name の順で推定
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
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す

        本サイトの詳細ページは実 HTML が入手できていないが、自治体 CMS では
        `<th>` を持たない 2 列テーブル (左 td: ラベル, 右 td: 値) も
        頻出するため、フォールバックとして対応する
        (yokosuka_doubutu / city_takamatsu_kagawa と同等の方針)。
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
        """テンプレート (common/images/) の装飾画像を除外する

        熊本市 CMS は `/dynamic/doubutuaigo/common/images/` や
        `/doubutuaigo/common/upload/common/` 配下にロゴ・装飾画像を
        置いているため、これらを除外したリストを返す。除外後に 0 件に
        なった場合は元リストを返す (フェイルセーフ)。
        """
        filtered = [
            u for u in urls
            if "/common/images/" not in u
            and "/common/upload/common/" not in u
            and "loading.gif" not in u
            and "newwin.gif" not in u
        ]
        return filtered if filtered else urls

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_url(url: str) -> str:
        """URL パスの `list03612` / `list03615` から動物種別を推定する

        - `list03612` を含む → "犬"
        - `list03615` を含む → "猫"
        - それ以外 → ""

        detail URL (`/doubutuaigo/kijiNNN/index.html`) には animal type の
        ヒントが含まれないため、本ヘルパーは主に site_config.list_url から
        推定する用途で利用される。
        """
        if not url:
            return ""
        if "list03612" in url:
            return "犬"
        if "list03615" in url:
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("迷子犬一覧" / "迷子猫一覧") から動物種別を推定する

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
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 熊本県` かつ `city.kumamoto.jp` ドメインのもの。
for _site_name in (
    "熊本市（迷子犬一覧）",
    "熊本市（迷子猫一覧）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityKumamotoAdapter)
