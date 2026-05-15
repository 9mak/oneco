"""熊本県動物愛護センター rule-based adapter

対象ドメイン: https://www.kumamoto-doubutuaigo.jp/

特徴:
- 動的 DB サイト。一覧 / 詳細ともに JavaScript で動物データを描画する
  ため、`PlaywrightFetchMixin` を多重継承して `_http_get` を Playwright
  実装に差し替える (sites.yaml で `requires_js: true`)。
- list ページの URL パスで以下の 8 種類に分かれており、いずれも同一
  テンプレート / detail 構造を共有するため 1 adapter で対応する:

  * `/animals/index/type_id:2/animal_id:1` センター譲渡犬
  * `/animals/index/type_id:2/animal_id:2` センター譲渡猫
  * `/animals/group/type_id:2/animal_id:1` 団体譲渡犬
  * `/animals/group/type_id:2/animal_id:2` 団体譲渡猫
  * `/post_animals/index/type_id:2/animal_id:1` 個人保護犬
  * `/post_animals/index/type_id:2/animal_id:2` 個人保護猫
  * `/animals/index/type_id:1/animal_id:1` 迷子犬
  * `/animals/index/type_id:1/animal_id:2` 迷子猫

  `type_id` が category と対応 (1=lost, 2=adoption/sheltered)、
  `animal_id` が species (1=犬, 2=猫) と対応する。

- detail ページは `/animals/detail/...` または `/post_animals/detail/...`
  形式。実 HTML が入手できていないため、自治体 DB 系で広く見られる
  `<dt>/<dd>` 定義リスト・`<th>/<td>` テーブルを前提に
  `WordPressListAdapter` の標準実装に乗せる。
- detail 内で species ラベルが空のときは list URL の `animal_id:N` から
  「犬」「猫」を推定する。
- 在庫 0 件の状態が日常的に発生し得るため、一覧から 1 件も detail
  リンクが拾えなかった場合は ParsingError ではなく空リストを返す。
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


class KumamotoDoubutuAigoAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """熊本県動物愛護センター (kumamoto-doubutuaigo.jp) 共通 rule-based adapter

    8 サイト (センター/団体/個人/迷子 × 犬/猫) を同一 adapter で扱う。
    Playwright で JS 描画後の HTML を取得し、`<dt>/<dd>` または
    `<th>/<td>` 形式の詳細ページから各フィールドを抽出する。
    """

    # JS 描画完了の目印。`.animal-list` 系の一覧コンテナが現れるまで待つ
    # (実サイトの確認が取れていないため、典型的なクラス名を fallback で
    # 待機させる。`PlaywrightFetcher` は selector 不在でも timeout までに
    # body が出れば返す実装のため、強い拘束にはしない)。
    WAIT_SELECTOR: ClassVar[str | None] = "body"

    # 詳細ページへのリンク (`/animals/detail/...` または
    # `/post_animals/detail/...`) を href 部分一致で抽出する。
    # sites.yaml の `list_link_pattern` と同じ意図。
    LIST_LINK_SELECTOR: ClassVar[str] = (
        "a[href*='/animals/detail/'], a[href*='/post_animals/detail/']"
    )

    # 詳細ページの想定ラベル。実 HTML が入手できていないため、自治体 DB
    # 系で広く見られる一般的な見出しを採用する。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 動物種別 (例: "犬", "猫", "雑種")
        "species": FieldSpec(label="種類"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢
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

    IMAGE_SELECTOR: ClassVar[str] = "img"

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)"""
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

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の固有処理を行う:
        - species (動物種別) はラベル抽出を優先し、空のときは
          detail URL → site_config.list_url → site_config.name の順で
          「犬」「猫」を推定する。
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

        # species 補完: 空の場合は URL パス → list URL → site name の順
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
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── 抽出ヘルパー拡張 ───────────────────

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す"""
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

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_url(url: str) -> str:
        """URL の `animal_id:N` から動物種別を推定する

        - `animal_id:1` を含む → "犬"
        - `animal_id:2` を含む → "猫"
        - それ以外 → ""

        list URL では確実にパターンが含まれるが、detail URL では含まれない
        ことがあるため、list URL → site name の順に fallback する想定。
        """
        if not url:
            return ""
        if "animal_id:1" in url:
            return "犬"
        if "animal_id:2" in url:
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("...犬", "...猫") から動物種別を推定する"""
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
# sites.yaml の `prefecture: 熊本県` かつ `kumamoto-doubutuaigo.jp` ドメイン
# の 8 サイトを同一 adapter にマップする。
for _site_name in (
    "熊本県動愛（センター譲渡犬）",
    "熊本県動愛（センター譲渡猫）",
    "熊本県動愛（団体譲渡犬）",
    "熊本県動愛（団体譲渡猫）",
    "熊本県動愛（個人保護犬）",
    "熊本県動愛（個人保護猫）",
    "熊本県動愛（迷子犬）",
    "熊本県動愛（迷子猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, KumamotoDoubutuAigoAdapter)
