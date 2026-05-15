"""山梨県動物愛護指導センター rule-based adapter

対象ドメイン: https://www.pref.yamanashi.jp/doubutsu/

特徴:
- 同一テンプレート上で 6 サイト (探している/保護されている × 犬/猫/その他)
  を運用しており、URL パターンのみが異なる:
    - https://www.pref.yamanashi.jp/doubutsu/m_dog/index.html (探している犬)
    - https://www.pref.yamanashi.jp/doubutsu/m_cat/index.html (探している猫)
    - https://www.pref.yamanashi.jp/doubutsu/m_other/index.html (探している他)
    - https://www.pref.yamanashi.jp/doubutsu/p_dog/index.html (保護されている犬)
    - https://www.pref.yamanashi.jp/doubutsu/p_cat/index.html (保護されている猫)
    - https://www.pref.yamanashi.jp/doubutsu/p_other/index.html (保護されている他)
- 1 ページに複数動物がカード形式で並ぶ single_page サイト。
  個別 detail ページは存在するが、一覧ページに必要な情報
  (場所/性別/毛色/写真) が全て掲載されているためここでは一覧から抽出する。
- 各動物カードは `<div class="menu_item">` で表現され、内部構造は:
    <div class="menu_item">
      <div class="menu_item_img"><span class="img"><img ... /></span></div>
      <div class="menu_item_cnt">
        <div class="item_link_ttl">
          <p class="txt"><a href="...">{場所}</a></p>
          <p>{性別}</p>
          <p>{毛色}</p>
        </div>
      </div>
    </div>
- テーブル形式ではなく `<p>` の並びで構造化されているため、
  `SinglePageTableAdapter` の `td/th` ベース既定実装ではなく
  `extract_animal_details` をオーバーライドして `<p>` から値を取得する。
- 種別 (犬/猫/その他) と収容/迷子の別は site_config 名と URL から決まり、
  ページ HTML には明示されないため adapter のクラス変数とサイト名から推定する。
- 収容日もページに掲載されないため、`SHELTER_DATE_DEFAULT` を空文字としつつ
  実運用では shelter_date 不明として扱う (RawAnimalData は文字列なので空可)。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class PrefYamanashiAdapter(SinglePageTableAdapter):
    """山梨県動物愛護指導センター用 rule-based adapter

    迷子 (m_*) / 保護 (p_*) × 犬/猫/その他 の 6 サイトで共通テンプレート。
    各動物は `div.menu_item` カードで表現される single_page 形式。
    """

    # 各動物カード
    ROW_SELECTOR: ClassVar[str] = "div.menu_item"
    # ヘッダ相当の行は無いので除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `.item_link_ttl > p` の位置に対するフィールドマッピング。
    # extract_animal_details オーバーライドから参照される (基底の cells ベース
    # 既定実装は本サイトでは使わないが、契約として明示的に宣言する)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "location",  # <p class="txt"><a>{市町村名}</a></p>
        1: "sex",       # <p>{オス|メス|不明}</p>
        2: "color",     # <p>{毛色}</p>
    }
    # location 列のインデックス (上の COLUMN_FIELDS と整合)
    LOCATION_COLUMN: ClassVar[int | None] = 0
    # 山梨県のサイトには収容日表記が無いため空文字で初期化 (不明扱い)
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """`<div class="menu_item">` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、`.item_link_ttl > p` の並びを
        `COLUMN_FIELDS` のインデックスに従って取り出す。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        # `.item_link_ttl` 配下の直下 <p> を順序通りに取得
        title_block = card.select_one("div.item_link_ttl")
        paragraphs: list[Tag] = []
        if isinstance(title_block, Tag):
            paragraphs = [
                p for p in title_block.find_all("p", recursive=False)
                if isinstance(p, Tag)
            ]

        fields: dict[str, str] = {}
        for col_idx, field_name in self.COLUMN_FIELDS.items():
            if col_idx < len(paragraphs):
                # <br> を含む場合があるので separator で結合
                text = paragraphs[col_idx].get_text(separator=" ", strip=True)
                fields[field_name] = text

        location = fields.get("location", "")

        # 動物種別はサイト名から推定 (URL パスでも可だが name の方が確実)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size="",
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
for _site_name in (
    "山梨県（探している犬）",
    "山梨県（探している猫）",
    "山梨県（探している他のペット）",
    "山梨県（保護されている犬）",
    "山梨県（保護されている猫）",
    "山梨県（保護されている他のペット）",
):
    SiteAdapterRegistry.register(_site_name, PrefYamanashiAdapter)
