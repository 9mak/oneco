"""SinglePageTableAdapter - 1ページ複数動物（detail ページなし）の汎用基底

愛媛県動物愛護センター、福島県、千葉県等で見られる「テーブルに全動物が
リストされ、個別 detail ページが存在しない」形式のサイト用。

fetch_animal_list は仮想 URL (`<list_url>#row=N`) を返し、
extract_animal_details は仮想 URL から行 index を解析して
キャッシュ済み HTML から該当行を抽出する。
"""

from __future__ import annotations

import logging
from typing import ClassVar
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ...domain.models import AnimalData, RawAnimalData
from ..municipality_adapter import ParsingError
from .base import RuleBasedAdapter

logger = logging.getLogger(__name__)


class SinglePageTableAdapter(RuleBasedAdapter):
    """single_page 形式の rule-based 抽出共通基底

    派生クラスは下記クラス変数を定義する:

    - `ROW_SELECTOR`: 各動物に対応する行/カード要素の CSS セレクタ
    - `COLUMN_FIELDS`: 列インデックス -> RawAnimalData フィールド名 の辞書
    - `SKIP_FIRST_ROW`: True のときヘッダ行を除外（デフォルト False）
    - `LOCATION_COLUMN`: 場所列のインデックス（任意）
    - `SHELTER_DATE_DEFAULT`: 収容日が取得できない場合のデフォルト ISO 日付
    - `NEXT_PAGE_SELECTOR`: 一覧が複数ページに分かれる場合の「次へ」リンクの
      CSS セレクタ（省略時は 1 ページ目のみ読む従来動作。WordPressListAdapter
      と同じ機構を single_page 系にも提供する。T137）
    - `MAX_LIST_PAGES`: ページ送りの上限（暴走防止）
    """

    ROW_SELECTOR: ClassVar[str] = ""
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    SKIP_FIRST_ROW: ClassVar[bool] = False
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""
    NEXT_PAGE_SELECTOR: ClassVar[str] = ""
    MAX_LIST_PAGES: ClassVar[int] = 10

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
        # 行 0 件は「現在その種別の収容動物がいない」真ゼロとして扱う。
        # HTML 取得・パースまで通っているのに ROW_SELECTOR にヒットしない状態は、
        # 例えば京都府保健所サイトの「現在保護している動物はいません」表示や、
        # 香川県等の収容 0 件状態で正常に発生する。
        # サイト DOM 構造変化による偽陰性は zero_count_audit で別途検出する運用。
        if not rows:
            return []
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
                # 個体識別: 派生が COLUMN_FIELDS にキーを足せば開通する。
                # name/management_number は監査(2026-06-11)指摘で追加(将来の派生
                # が COLUMN_FIELDS だけで足したときの kochi 同型サイレントドロップを予防)。
                breed=fields.get("breed", ""),
                description=fields.get("description", ""),
                name=fields.get("name", ""),
                management_number=fields.get("management_number", ""),
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得して行をキャッシュ

        `NEXT_PAGE_SELECTOR` を定義した派生クラスでは「次へ」リンクを最後まで
        辿り、全ページの行を連結する。定義していない派生クラスは list_url の
        1 ページ目だけを読む従来動作のまま。

        上限到達・循環検知いずれで打ち切った場合も `self.list_truncated` を
        立てる。CollectorService はこのフラグを見て prune_disappeared
        (消滅同期削除) をスキップする (T059)。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        rows: list[Tag] = []
        visited_pages: set[str] = set()
        page_url = self.site_config.list_url
        truncated = False

        for _ in range(self.MAX_LIST_PAGES):
            if page_url in visited_pages:
                truncated = True
                logger.warning(
                    "[%s] 一覧のページ送りで循環を検知しました (既訪問ページへの"
                    "再遷移: %s)。未取得のページが残っている可能性があります",
                    self.site_config.name,
                    page_url,
                )
                break
            visited_pages.add(page_url)

            # 1 ページ目は `self._html_cache` が既に埋まっていれば再利用する。
            # 一部の派生 adapter (例: CityWakayamaAdapter.fetch_animal_list) は
            # `_load_rows` 呼び出し前に自前で `_http_get` して `_html_cache` に
            # 格納し、本文コンテナの存在チェックに使ってから `_load_rows` を
            # 呼ぶため、ここで再フェッチすると HTTP 呼び出しが二重になる。
            if page_url == self.site_config.list_url and self._html_cache is not None:
                html = self._html_cache
            else:
                html = self._http_get(page_url)
                if page_url == self.site_config.list_url:
                    self._html_cache = html
            soup = BeautifulSoup(html, "html.parser")
            page_rows = [r for r in soup.select(self.ROW_SELECTOR) if isinstance(r, Tag)]
            rows.extend(page_rows)

            if not self.NEXT_PAGE_SELECTOR:
                break
            next_link = soup.select_one(self.NEXT_PAGE_SELECTOR)
            next_href = next_link.get("href") if isinstance(next_link, Tag) else None
            if not next_href or not isinstance(next_href, str):
                break
            page_url = self._absolute_url(next_href, base=page_url)
        else:
            if self.NEXT_PAGE_SELECTOR:
                truncated = True
                logger.warning(
                    "[%s] 一覧のページ送りが上限 %d ページに達しました。"
                    "未取得のページが残っている可能性があります: %s",
                    self.site_config.name,
                    self.MAX_LIST_PAGES,
                    page_url,
                )

        self.list_truncated = truncated
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
