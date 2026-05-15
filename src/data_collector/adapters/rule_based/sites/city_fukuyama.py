"""福山市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/

特徴:
- 同一 CMS テンプレート上で 2 サイトを運用しており、URL のみが異なる:
    - .../soshiki/dobutsuaigo/237722.html  (保護犬)
    - .../soshiki/dobutsuaigo/60970.html   (保護猫)
- 1 ページに `<table summary="...">` 形式で動物情報が並ぶ single_page サイト。
  個別 detail ページは存在しない (yaml 上 list_link_pattern が指定されて
  いる場合があるが、実体としてはテーブルに全頭が並ぶ構造)。
- ページ内に複数 `<table>` が存在する可能性があるため、対象テーブルを
  `<thead>` 内の見出し ("番号"/"保護日"/"保護場所" 等) で識別する。
- 対象テーブル構造 (1 行 = 1 頭, 列順):
    <thead>番号 / 保護日 / 保護場所 / 種類 / 毛色 / 性別 / 掲載期間</thead>
    <tbody><tr><td>...</td>... × 7</tr> ...</tbody>
- 在庫 0 件の状態でも `<tbody>` 内に "全セル `&nbsp;`" のプレースホルダ
  行が 1 件残っている運用がある。本 adapter ではこれを 0 件として扱う。
- 動物種別 (犬/猫) はサイト名から推定する。
- フィクスチャは UTF-8 バイト列を Latin-1 として再保存した二重
  エンコーディング状態のことがあるため、テスト側で逆変換を行う。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 対象テーブルを `<thead>` の見出し集合で識別するためのキーワード
_REQUIRED_HEADER_KEYWORDS = ("保護日", "種類")


class CityFukuyamaAdapter(SinglePageTableAdapter):
    """福山市動物愛護センター用 rule-based adapter

    保護犬 (237722) / 保護猫 (60970) の 2 サイトで共通テンプレート。
    `<table summary="...">` ヘッダ行 + データ行 N 件の single_page 形式。
    """

    # ROW_SELECTOR は基底契約上必須。`_load_rows` をオーバーライドして
    # ヘッダ集合で対象テーブルを選ぶため、直接 select には使わない
    # (フォールバック用に残す)。
    ROW_SELECTOR: ClassVar[str] = "table tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False  # tbody > tr のみ抽出するため不要
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 列 0 (番号) と列 6 (掲載期間) は使わない。
    # 列 3 (種類) は犬種詳細だが species にも一旦取得し、
    # サイト名から推定した species (犬/猫) を優先する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        1: "shelter_date",
        2: "location",
        3: "species",
        4: "color",
        5: "sex",
    }
    LOCATION_COLUMN: ClassVar[int | None] = 2
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """対象テーブル (見出しに "保護日"/"種類" を含む) のデータ行のみ返す

        ページ内に複数 `<table>` が存在し得るため見出しで対象を絞る。
        対象テーブルが見つからない場合は空リストを返す (呼出側で 0 件扱い)。
        さらに、全セルが空白/`&nbsp;` のみのプレースホルダ行は
        在庫 0 件のサインなので除外する。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        target_table = self._find_target_table(soup)
        if target_table is None:
            self._rows_cache = []
            return self._rows_cache

        # `<tbody>` 配下の `<tr>` を優先。無ければ `<thead>` 行を除く全 `<tr>`
        tbody = target_table.find("tbody")
        rows: list[Tag]
        if isinstance(tbody, Tag):
            rows = [r for r in tbody.find_all("tr") if isinstance(r, Tag)]
        else:
            all_rows = [r for r in target_table.find_all("tr") if isinstance(r, Tag)]
            thead = target_table.find("thead")
            if isinstance(thead, Tag):
                head_rows = {id(r) for r in thead.find_all("tr")}
                rows = [r for r in all_rows if id(r) not in head_rows]
            else:
                rows = all_rows[1:] if all_rows else []

        # `<th>` のみのヘッダ行が紛れた場合は除外
        rows = [r for r in rows if r.find("td") is not None]
        # 全セル空白/`&nbsp;` のみのプレースホルダ行は 0 件として扱う
        rows = [r for r in rows if not self._is_placeholder_row(r)]
        self._rows_cache = rows
        return self._rows_cache

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        対象テーブルが無い / データ行 0 件 / プレースホルダ行のみの場合は
        空リストを返す (在庫 0 件は ParsingError ではなく空リストで表現)。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        species をサイト名 (犬/猫) で上書きし、shelter_date / location は
        テーブル列から取得する。
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

        # 動物種別はサイト名から推定 (福山市は犬/猫の 2 サイト運用)。
        # HTML の「種類」列 (例: 柴, 雑) は犬種/猫種詳細のため species
        # 本体には使わず、サイト名推定を優先。
        species = self._infer_species_from_site_name(self.site_config.name)
        if not species:
            species = fields.get("species", "")

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size="",
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _find_target_table(soup: BeautifulSoup) -> Tag | None:
        """`<thead>` の見出しテキストで対象テーブルを識別する

        ページ内に複数 `<table>` が存在し得るため、ヘッダの内容で対象を絞る。
        全キーワード ("保護日", "種類") を含む `<th>` を持つ表を選ぶ。
        """
        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            header_text = " ".join(th.get_text(strip=True) for th in table.find_all("th"))
            if all(kw in header_text for kw in _REQUIRED_HEADER_KEYWORDS):
                return table
        return None

    @staticmethod
    def _is_placeholder_row(row: Tag) -> bool:
        """全セルが空白/`&nbsp;` のみのプレースホルダ行か判定する

        福山市 CMS は在庫 0 件のときでも tbody に空セルだけの行を残す
        運用があるため、これを在庫 0 件として扱う。
        """
        cells = row.find_all(["td", "th"])
        if not cells:
            return True
        for cell in cells:
            text = cell.get_text(strip=True).replace("\xa0", "").strip()
            if text:
                return False
        return True

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイト (保護犬/保護猫) を
# 同一 adapter にマップする。
for _site_name in (
    "福山市（保護犬）",
    "福山市（保護猫）",
):
    SiteAdapterRegistry.register(_site_name, CityFukuyamaAdapter)
