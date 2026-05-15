"""あかし動物センター rule-based adapter

対象ドメイン: https://www.city.akashi.lg.jp/kankyou/dobutsu/info/maigo/

特徴:
- 同一テンプレート (akashippo CMS) 上で 2 サイト (迷子犬 / 迷子猫) を運用しており、
  URL パターンのみが異なる:
    - .../maigo/dog.html  (迷子犬)
    - .../maigo/cat.html  (迷子猫)
- 1 ページに動物情報が並ぶ single_page サイト。個別 detail ページは存在しない。
- 本文は `#tmp_contents` 配下に配置される。動物情報が掲載される場合は
  `<table>` 形式 (1 行 = 1 頭) で並ぶのが本テンプレートの典型構造。
- 在庫 0 件のときは説明文のみで `<table>` 自体が存在しない (もしくはテーブル
  ヘッダのみ) 状態になる。本 adapter はこれを検出し、`fetch_animal_list` から
  空リストを返す (ParsingError は出さない)。
- 動物種別 (犬/猫) はサイト名から推定する。HTML の「種類」列は犬種等の具体名
  となる想定なので species への直接利用は不適切。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityAkashiAdapter(SinglePageTableAdapter):
    """あかし動物センター用 rule-based adapter

    迷子犬 / 迷子猫 の 2 サイトで共通テンプレートを使用する。
    `#tmp_contents` 配下のテーブル (ヘッダ行 + データ行 N 件) を抽出する
    single_page 形式。
    """

    # `#tmp_contents` 配下のテーブル行のみを対象とする。
    # テンプレート上では本文以外 (グローバルメニュー等) にテーブルは無いが、
    # 念のためスコープを限定する。
    ROW_SELECTOR: ClassVar[str] = "#tmp_contents table tr"
    # 1 行目はヘッダ (`<th>`) を想定 — 除外する
    SKIP_FIRST_ROW: ClassVar[bool] = True
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 想定列構成: [収容日 / 写真 / 種類(犬種等) / 性別 / 毛色 / 体格 / その他]
    # - 列 0: 収容日 (shelter_date)
    # - 列 1: 写真 (img) → セルベース既定実装ではテキスト抽出されないが、
    #   `_extract_row_images` が行全体から拾うので問題ない
    # - 列 2: 種類 (犬種名等。species はサイト名から推定するため未マップ)
    # - 列 3: 性別
    # - 列 4: 毛色
    # - 列 5: 体格
    # - 列 6: その他 (場所が含まれる場合あり) → location として扱う
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",
        3: "sex",
        4: "color",
        5: "size",
    }
    # 場所列 (実テンプレート未確定だが、慣例として列 6 (その他) に
    # 収容場所が記載されることが多い)
    LOCATION_COLUMN: ClassVar[int | None] = 6
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """データ行が見つからない (在庫 0 件) ときは空リストを返す

        あかし動物センターは保護動物が居ない期間も平常運用される (現に
        本 adapter 作成時点では 2 サイトとも 0 件状態)。テーブル不在 /
        ヘッダ行のみ / そもそも `#tmp_contents` が存在しない、いずれの
        場合も ParsingError ではなく空リストとする。
        """
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        # 本文コンテナが無い = テンプレートが完全に変わっている異常状態のみ例外
        if soup.select_one("#tmp_contents") is None:
            raise ParsingError(
                "本文コンテナ (#tmp_contents) が見つかりません",
                selector="#tmp_contents",
                url=self.site_config.list_url,
            )

        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        基底のセルベース既定実装に対し、species のサイト名推定を加える。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]
        cells = row.find_all(["td", "th"])

        fields: dict[str, str] = {}
        for col_idx, field_name in self.COLUMN_FIELDS.items():
            if col_idx < len(cells):
                fields[field_name] = cells[col_idx].get_text(separator=" ", strip=True)

        location = ""
        if self.LOCATION_COLUMN is not None and self.LOCATION_COLUMN < len(cells):
            location = cells[self.LOCATION_COLUMN].get_text(separator=" ", strip=True)

        # 動物種別 (犬/猫) はサイト名から推定 (HTML の「種類」は犬種名等)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=location,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

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
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "あかし動物センター（迷子犬）",
    "あかし動物センター（迷子猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityAkashiAdapter)
