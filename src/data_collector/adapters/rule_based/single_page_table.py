"""SinglePageTableAdapter - 1ページ複数動物（detail ページなし）の汎用基底

愛媛県動物愛護センター、福島県、千葉県等で見られる「テーブルに全動物が
リストされ、個別 detail ページが存在しない」形式のサイト用。

fetch_animal_list は仮想 URL (`<list_url>#row=N`) を返し、
extract_animal_details は仮想 URL から行 index を解析して
キャッシュ済み HTML から該当行を抽出する。
"""

from __future__ import annotations

from typing import ClassVar
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ...domain.models import AnimalData, RawAnimalData
from ..municipality_adapter import ParsingError
from .base import RuleBasedAdapter


class SinglePageTableAdapter(RuleBasedAdapter):
    """single_page 形式の rule-based 抽出共通基底

    派生クラスは下記クラス変数を定義する:

    - `ROW_SELECTOR`: 各動物に対応する行/カード要素の CSS セレクタ
    - `COLUMN_FIELDS`: 列インデックス -> RawAnimalData フィールド名 の辞書
    - `SKIP_FIRST_ROW`: True のときヘッダ行を除外（デフォルト False）
    - `LOCATION_COLUMN`: 場所列のインデックス（任意）
    - `SHELTER_DATE_DEFAULT`: 収容日が取得できない場合のデフォルト ISO 日付
    """

    ROW_SELECTOR: ClassVar[str] = ""
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    SKIP_FIRST_ROW: ClassVar[bool] = False
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._html_cache: str | None = None
        self._rows_cache: list[Tag] | None = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        abstracts = getattr(cls, "__abstractmethods__", frozenset())
        if not abstracts and not cls.ROW_SELECTOR:
            raise TypeError(f"{cls.__name__} must define ROW_SELECTOR class variable")

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        rows = self._load_rows()
        if not rows:
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
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
                fields[field_name] = cells[col_idx].get_text(strip=True)

        location = ""
        if self.LOCATION_COLUMN is not None and self.LOCATION_COLUMN < len(cells):
            location = cells[self.LOCATION_COLUMN].get_text(strip=True)

        try:
            return RawAnimalData(
                species=fields.get("species", ""),
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=location or fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を 1 回だけ取得して行をキャッシュ"""
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        rows = soup.select(self.ROW_SELECTOR)
        rows = [r for r in rows if isinstance(r, Tag)]
        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    def _parse_row_index(self, virtual_url: str) -> int:
        """`<list_url>#row=N` から N を取り出す"""
        fragment = urlparse(virtual_url).fragment
        if not fragment.startswith("row="):
            raise ParsingError(f"無効な仮想 URL: {virtual_url} (#row=N 形式が必要)")
        return int(fragment.split("=", 1)[1])

    def _extract_row_images(self, row: Tag, base_url: str) -> list[str]:
        """行内の img タグから src を取得"""
        urls: list[str] = []
        for img in row.find_all("img"):
            src = img.get("src")
            if src and isinstance(src, str):
                urls.append(self._absolute_url(src, base=base_url))
        return self._filter_image_urls(urls, base_url)
