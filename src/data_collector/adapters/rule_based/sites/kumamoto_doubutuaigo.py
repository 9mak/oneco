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

    # 詳細ページ `<dl class="animal-detail"><dt>項目</dt><dd>値</dd>` の実見出し
    # ラベル (2026-05 ブラウザ実査)。譲渡/迷子いずれも同一ラベル。
    #   - species: 「種類」値は "雑種(ミックス)" 等で犬/猫を判別できず その他化
    #     するため、ここでは抽出せず URL の animal_id / サイト名から犬/猫を推定
    #     する (extract_animal_details の補完ロジックに委ねる)。
    #   - location: 迷子犬は「捕獲場所」、譲渡犬は「捕獲場所」を持たず
    #     保健所の「所在地」のみで住所情報を提供する。tuple OR で
    #     捕獲場所 → 所在地 の順に探し、両方無いケースのみ部分一致
    #     "場所" にフォールバック。
    #     (旧実装は "場所" 部分一致のみで「所在地」を拾えず、譲渡カテゴリ
    #     27 件が全件 '不明' になっていた)
    #   - shelter_date: 「保護した日」(旧 "収容日" は実在しない)
    #   - phone: 「連絡先」は施設名なので「電話番号」を優先
    #   - size: 実サイトは「体重」のみで体格欄が無い ("大きさ" は温存=空→None)
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="大きさ"),
        # 「体重: 15kg」を後段で normalizer 語彙 (小/中/大) に変換するため、
        # 一時フィールドとして取り出しておく。size が空のときの推定ソース。
        "weight": FieldSpec(label="体重"),
        "shelter_date": FieldSpec(label=("保護した日", "収容日")),
        "location": FieldSpec(label=("捕獲場所", "保護場所", "所在地", "場所")),
        "phone": FieldSpec(label=("電話番号", "連絡先")),
        # 個体識別: 個体管理ナンバー (例 DC00744)。全カードの dl に存在するが
        # 未登録で全件ドロップしていた (2026-06-16)。
        "management_number": FieldSpec(label="個体管理ナンバー"),
    }

    # 体重 → size 推定の境界 (kg)。oita_aigo._weight_to_size と同基準。
    _SIZE_BOUNDARY_SMALL_KG: ClassVar[float] = 5.0
    _SIZE_BOUNDARY_LARGE_KG: ClassVar[float] = 15.0

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

        # size: 「大きさ」欄が無い熊本サイト用に「体重: 15kg」を
        # normalizer 語彙 (小/中/大) に変換するフォールバック。
        # 既に大きさ欄が取れている場合はそちらを優先する。
        size = fields.get("size", "") or self._weight_to_size(fields.get("weight", ""))

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=size,
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                management_number=fields.get("management_number", ""),
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    @classmethod
    def _weight_to_size(cls, weight_text: str) -> str:
        """「15kg」「13kg前後」のような体重テキストを「小/中/大」に変換

        - 5kg 未満: 小
        - 5kg 以上 15kg 未満: 中
        - 15kg 以上: 大
        - 数値が拾えない場合 ("不明" 等): 空文字
        """
        if not weight_text:
            return ""
        m = re.search(r"(\d+(?:\.\d+)?)", weight_text)
        if not m:
            return ""
        try:
            kg = float(m.group(1))
        except ValueError:
            return ""
        if kg < cls._SIZE_BOUNDARY_SMALL_KG:
            return "小"
        if kg < cls._SIZE_BOUNDARY_LARGE_KG:
            return "中"
        return "大"

    # ─────────────────── 抽出ヘルパー拡張 ───────────────────

    def _extract_by_label(self, soup: BeautifulSoup, label: str | tuple[str, ...]) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す。

        label は str / tuple のどちらも受け付ける (tuple は OR 検索)。
        """
        # まず基底の dl / th-td パターンを試す (tuple も基底側で対応)
        value = super()._extract_by_label(soup, label)
        if value:
            return value

        # フォールバック: <td>label</td><td>value</td> の 2 列テーブル
        labels = (label,) if isinstance(label, str) else tuple(label)
        for lbl in labels:
            for td in soup.find_all("td"):
                if not isinstance(td, Tag):
                    continue
                cell_text = td.get_text(strip=True)
                if not cell_text or lbl not in cell_text:
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
