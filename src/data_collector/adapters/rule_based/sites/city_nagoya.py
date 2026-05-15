"""名古屋市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.nagoya.jp/kurashi/pet/

特徴:
- 同一テンプレート (city.nagoya.jp 公式 CMS) 上で 3 サイトを運用しており、
  URL パターンのみが異なる:
    - .../1015473/1015489/1015493.html  (飼主のわからない犬猫等 / lost)
    - .../1015473/1015483/1015484.html  (譲渡犬 / adoption)
    - .../1015473/1015483/1015488.html  (譲渡猫 / adoption)
- 1 ページに複数動物が掲載される single_page サイト。
  個別 detail ページは存在しないため一覧ページから直接抽出する。
- 動物が掲載されている場合は `article#content` 配下の `<table>` 行に
  情報が並ぶテーブル形式 (テンプレート CMS の表組ブロック)。
- 0 件のとき (例: 飼主のわからない犬猫等のテキスト案内ページや、
  譲渡対象が居ないとき) はページ内に動物用の `<table>` が存在しない。
  本 adapter はその場合 `fetch_animal_list` から空リストを返す
  (ParsingError は出さない) ことで「在庫 0 件」を表現する。
- 動物種別 (犬/猫/その他) はサイト名から推定する。
  HTML の「種類」列は犬種等の具体名 (柴犬/雑種…) になることがあるため。
- 列順は実サイト調査時点で確定していないため、基底
  `SinglePageTableAdapter` の cells ベース既定実装を流用しつつ、
  ヘッダ行 (`<th>` を含む行) はラベルに基づき列名を学習して、
  各データ行から該当列を取り出す柔軟な実装とする。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# ヘッダラベル → RawAnimalData フィールド名 のマッピング。
# ラベルは部分一致で判定する (例: "収容日・収容場所" は "収容日" でヒット)。
_LABEL_TO_FIELD: dict[str, str] = {
    "収容日": "shelter_date",
    "保護日": "shelter_date",
    "収容場所": "location",
    "保護場所": "location",
    "発見場所": "location",
    "場所": "location",
    "種類": "species",
    "犬種": "species",
    "猫種": "species",
    "性別": "sex",
    "毛色": "color",
    "色": "color",
    "体格": "size",
    "大きさ": "size",
    "サイズ": "size",
    "管理番号": "_id",
    "番号": "_id",
}


class CityNagoyaAdapter(SinglePageTableAdapter):
    """名古屋市動物愛護センター用 rule-based adapter

    飼主のわからない犬猫等 / 譲渡犬 / 譲渡猫 の 3 サイトで共通テンプレート
    (city.nagoya.jp 公式 CMS) を使用する。
    動物情報は `article#content` 配下の `<table>` 各行に並ぶ single_page 形式。
    """

    # `article#content` 配下の table 行のみを対象とする。
    # ページ内のサイドナビ等に万一 table があっても拾わないよう本文に限定。
    ROW_SELECTOR: ClassVar[str] = "article#content table tr"
    # ヘッダ行 (`<th>` のみで構成) はデータ行から除外する
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 列順はサイト/時期で変動しうるため固定 index は使わない。
    # 契約として最低限のフィールドだけ宣言 (実装は extract で動的決定)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        動物テーブルが存在しない場合 (ページが純テキスト案内のみ等) は
        空リストを返す (在庫 0 件扱い、ParsingError は出さない)。
        """
        rows = self._load_data_rows()
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """テーブル行 + ヘッダラベルから RawAnimalData を構築する

        ヘッダ行 (`<th>` を含む行) があれば列ラベル → field マップを学習し、
        各データ行のセルをラベルに従って取り出す。
        ヘッダが取得できない場合は順序ベースの素朴な割当てを行う。
        """
        rows = self._load_data_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]
        cells = row.find_all(["td", "th"])

        col_to_field = self._build_column_map()

        fields: dict[str, str] = {}
        for col_idx, cell in enumerate(cells):
            field = col_to_field.get(col_idx)
            if not field:
                continue
            text = cell.get_text(separator=" ", strip=True)
            # 同じフィールドが複数列に当たった場合は最初の値を優先
            if text and field not in fields:
                fields[field] = text

        # 「収容日・収容場所」のように 1 セルに複合された表記を補正
        if "shelter_date" in fields and "location" not in fields:
            date, loc = self._split_date_and_location(fields["shelter_date"])
            if date:
                fields["shelter_date"] = date
            if loc:
                fields["location"] = loc

        # 動物種別はサイト名から推定 (HTML の「種類」は犬種名等の具体値の可能性)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    def _load_data_rows(self) -> list[Tag]:
        """ヘッダ行 (全セルが `<th>`) を除いたデータ行のみを返す

        動物用 table が存在しない場合は空リストを返す (0 件扱い)。
        """
        rows = self._load_rows()
        return [r for r in rows if not self._is_header_row(r)]

    def _build_column_map(self) -> dict[int, str]:
        """ヘッダ行からラベル → field の対応を学習する

        Returns:
            列 index → RawAnimalData field 名 の辞書。
            ヘッダ行が見つからない場合は空辞書 (= 抽出フィールド無し)。
        """
        all_rows = self._load_rows()
        header = next(
            (r for r in all_rows if self._is_header_row(r)), None
        )
        if header is None:
            return {}

        col_map: dict[int, str] = {}
        cells = header.find_all(["td", "th"])
        for col_idx, cell in enumerate(cells):
            label = cell.get_text(separator="", strip=True)
            field = self._match_label_to_field(label)
            if field and field != "_id":
                col_map[col_idx] = field
        return col_map

    @staticmethod
    def _is_header_row(row: Tag) -> bool:
        """行が「全セルが `<th>`」のヘッダ行かを判定"""
        cells = row.find_all(["td", "th"])
        if not cells:
            return False
        return all(c.name == "th" for c in cells)

    @staticmethod
    def _match_label_to_field(label: str) -> str | None:
        """ヘッダラベルから RawAnimalData フィールド名を推定する"""
        if not label:
            return None
        for keyword, field in _LABEL_TO_FIELD.items():
            if keyword in label:
                return field
        return None

    @staticmethod
    def _split_date_and_location(text: str) -> tuple[str, str]:
        """「収容日 + 収容場所」が 1 セルに混在する場合に分割する

        例: "令和8年5月7日 名古屋市中区..." → ("令和8年5月7日", "名古屋市中区...")
        日付パターン (令和/平成/和暦/yyyy/MM 形式) を検出して左右に分割。
        """
        # 令和/平成 の和暦 + 年月日
        m = re.match(
            r"\s*((?:令和|平成|昭和)\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日)\s*(.*)$",
            text,
        )
        if m:
            return m.group(1), m.group(2).strip()
        # 西暦 yyyy/M/d または yyyy-M-d
        m = re.match(
            r"\s*(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\s*(.*)$", text
        )
        if m:
            return m.group(1), m.group(2).strip()
        return text, ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
for _site_name in (
    "名古屋市（飼主不明動物）",
    "名古屋市（譲渡犬）",
    "名古屋市（譲渡猫）",
):
    SiteAdapterRegistry.register(_site_name, CityNagoyaAdapter)
