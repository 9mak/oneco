"""SinglePageTableAdapter - 1ページ複数動物（detail ページなし）の汎用基底

愛媛県動物愛護センター、福島県、千葉県等で見られる「テーブルに全動物が
リストされ、個別 detail ページが存在しない」形式のサイト用。

fetch_animal_list は仮想 URL (`<list_url>#row=N`) を返し、
extract_animal_details は仮想 URL から行 index を解析して
キャッシュ済み HTML から該当行を抽出する。
"""

from __future__ import annotations

import logging
import unicodedata
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
    - `HEADER_FIELDS`: ヘッダセル文字列 (完全一致 → 部分一致フォールバック、
      tuple は OR 検索。`_extract_by_label` と同じマッチング仕様) ->
      RawAnimalData フィールド名 の辞書 (T402)。設定するとテーブルの
      ヘッダ行 (`<thead>` の `<tr>`、無ければ `<th>` を含む最初の `<tr>`) を
      読み、実際の列インデックスへ動的に解決する。`COLUMN_FIELDS` と併用
      した場合、`HEADER_FIELDS` が解決できた列を優先し、残りは
      `COLUMN_FIELDS` で補う。列順がサイトごとに揺れる/ヘッダ行に意味が
      集約されているテーブルで `COLUMN_FIELDS` の代わりに使う。
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
    HEADER_FIELDS: ClassVar[dict[str | tuple[str, ...], str]] = {}
    SKIP_FIRST_ROW: ClassVar[bool] = False
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""
    NEXT_PAGE_SELECTOR: ClassVar[str] = ""
    MAX_LIST_PAGES: ClassVar[int] = 10

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._html_cache: str | None = None
        self._rows_cache: list[Tag] | None = None
        # table id() -> 解決済み {列インデックス: フィールド名}。
        # ページ内に複数テーブルがある場合、テーブルごとに個別解決してキャッシュする。
        self._header_field_cache: dict[int, dict[int, str]] = {}

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

        column_map: dict[int, str] = dict(self.COLUMN_FIELDS)
        if self.HEADER_FIELDS:
            table = row.find_parent("table")
            if isinstance(table, Tag):
                header_map = self._resolve_and_cache_header_fields(table)
                # HEADER_FIELDS が解決した列を優先し、COLUMN_FIELDS はその
                # 残りを補う (同じフィールドが両方にあれば HEADER_FIELDS の
                # 列が後から辞書に追加され、下の抽出ループで最後に評価される
                # ため上書きで勝つ)。
                column_map.update(header_map)

        fields: dict[str, str] = {}
        for col_idx, field_name in column_map.items():
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
            if self.HEADER_FIELDS:
                page_rows = self._filter_rows_with_resolvable_columns(page_rows)
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

    # ─────────────────── HEADER_FIELDS (T402) ───────────────────

    def _rows_or_empty_with_warning(self, table: Tag | None, rows: list[Tag]) -> list[Tag]:
        """HEADER_FIELDS/COLUMN_FIELDS どちらも解決できない対象テーブルは 0 件にする

        `table` で HEADER_FIELDS が 1 列も解決できず、かつ COLUMN_FIELDS も
        未設定 (空辞書) の場合、`rows` はフィールドが一切埋まらない無意味な
        レコードになるため空リストにして、サイト名を含む WARNING を出す。

        `_load_rows` を丸ごとオーバーライドして単一の対象テーブルから
        データ行を切り出す派生 adapter (`city_kitakyushu` / `city_maebashi`
        等、T402 reviewer 指摘 M-1) は、基底 `_load_rows` 内の
        `_filter_rows_with_resolvable_columns` を経由しないため、自前の
        `_load_rows` の末尾でこのヘルパーを明示的に呼ぶ必要がある。
        HEADER_FIELDS が未設定 / rows が既に空 / `table` が渡されない場合は
        何もせず `rows` をそのまま返す。
        """
        if not rows or not self.HEADER_FIELDS:
            return rows
        if not isinstance(table, Tag):
            return rows

        header_map = self._resolve_and_cache_header_fields(table)
        if header_map or self.COLUMN_FIELDS:
            return rows

        logger.warning(
            "[%s] HEADER_FIELDS を解決できず、COLUMN_FIELDS も未設定のため "
            "テーブルの行を 0 件として扱います",
            self.site_config.name,
        )
        return []

    def _filter_rows_with_resolvable_columns(self, candidate_rows: list[Tag]) -> list[Tag]:
        """HEADER_FIELDS 使用時、列を解決できないテーブルの行を除外する

        行が属するテーブルごとにグループ化し、テーブル単位で
        `_rows_or_empty_with_warning` を適用する (WARNING もテーブルごとに
        1 回だけ)。行がテーブルに属さない (`<table>` の外) 場合は素通しする。
        """
        if not self.HEADER_FIELDS:
            return candidate_rows

        groups: dict[int, tuple[Tag | None, list[Tag]]] = {}
        order: list[int] = []
        for row in candidate_rows:
            table = row.find_parent("table")
            key = id(table) if isinstance(table, Tag) else id(row)
            if key not in groups:
                groups[key] = (table if isinstance(table, Tag) else None, [])
                order.append(key)
            groups[key][1].append(row)

        kept: list[Tag] = []
        for key in order:
            table, rows = groups[key]
            kept.extend(self._rows_or_empty_with_warning(table, rows))
        return kept

    def _resolve_and_cache_header_fields(self, table: Tag) -> dict[int, str]:
        """`table` の HEADER_FIELDS 解決結果をテーブル単位でキャッシュして返す"""
        key = id(table)
        cached = self._header_field_cache.get(key)
        if cached is None:
            cached = self.resolve_header_fields(table)
            self._header_field_cache[key] = cached
        return cached

    def resolve_header_fields(self, container: Tag) -> dict[int, str]:
        """HEADER_FIELDS をヘッダ行の実際の列インデックスへ解決する

        `container` には対象の `<table>` 自身、もしくはその `<table>` を
        含む soup/親要素を渡せる (`<table>` でなければ内部から最初の
        `<table>` を探す)。HTTP を発生させず、既に取得済みの soup/table を
        引数として解決結果だけを返すため、`list_selector_resolution.py` や
        監査スクリプトから HTTP なしで参照可能。

        ヘッダ行は `<thead>` 内の `<tr>` 群を優先し、無ければ `<th>` を
        含む最初の `<tr>` にフォールバックする。ヘッダ行が全く見つからない
        場合は空辞書を返す (呼出側は COLUMN_FIELDS にフォールバックする)。
        """
        table = container if container.name == "table" else container.find("table")
        if not isinstance(table, Tag):
            return {}
        if not self.HEADER_FIELDS:
            return {}

        header_texts = self._header_column_texts(table)
        if not header_texts:
            return {}

        sorted_cols = sorted(header_texts.items())
        assigned_cols: set[int] = set()
        result: dict[int, str] = {}

        for label_spec, field_name in self.HEADER_FIELDS.items():
            labels = (label_spec,) if isinstance(label_spec, str) else tuple(label_spec)
            found_col: int | None = None

            # 1st pass: 完全一致優先 (_extract_by_label と同じ二段構え)
            for lbl in labels:
                for col, text in sorted_cols:
                    if col in assigned_cols:
                        continue
                    if text == lbl:
                        found_col = col
                        break
                if found_col is not None:
                    break

            # 2nd pass: 部分一致フォールバック。複数列が候補になり得るため
            # (例: label="種類" が「種類」「種類（推定）」両方にマッチ)、
            # 先頭の列を採用しつつ曖昧だったことを DEBUG ログへ残す。
            if found_col is None:
                for lbl in labels:
                    candidates = [
                        col for col, text in sorted_cols if col not in assigned_cols and lbl in text
                    ]
                    if not candidates:
                        continue
                    found_col = candidates[0]
                    if len(candidates) > 1:
                        logger.debug(
                            "[%s] HEADER_FIELDS の部分一致で複数列が候補になりました "
                            "(ラベル=%r, フィールド=%s, 採用列=%d, 候補列=%s)",
                            self.site_config.name,
                            lbl,
                            field_name,
                            found_col,
                            candidates,
                        )
                    break

            if found_col is not None:
                result[found_col] = field_name
                assigned_cols.add(found_col)

        return result

    def _header_column_texts(self, table: Tag) -> dict[int, str]:
        """テーブルのヘッダ行群から `{列インデックス: 正規化済みテキスト}` を構築する

        colspan (横方向) は同じテキストを複数列インデックスへ複製する。
        rowspan (縦方向、複数ヘッダ行にまたがる場合) は次の行までその列に
        テキストを引き継ぐ (carry)。ヘッダが複数行ある場合、各行自身の
        セルテキストが最終的な列テキストとして採用される (carry は空いた
        位置を埋めるためだけに使う)。
        """
        header_rows = self._header_row_group(table)
        if not header_rows:
            return {}

        # col -> (このヘッダ行の後さらに何行分残っているか, テキスト)。
        # 行を処理する直前に確定させた「前の行から持ち越された」carry のみを
        # 参照する (今行で新たに rowspan を宣言したセルは次回の carry へ回す)。
        # そうしないと同じセルの rowspan 残数を 1 ターンで二重に減算してしまう。
        carry: dict[int, tuple[int, str]] = {}
        final: dict[int, str] = {}

        for row in header_rows:
            incoming_carry = carry
            cells = [c for c in row.find_all(["th", "td"], recursive=False) if isinstance(c, Tag)]
            col = 0
            cell_idx = 0
            row_map: dict[int, str] = {}
            next_carry: dict[int, tuple[int, str]] = {}
            while cell_idx < len(cells) or col in incoming_carry:
                if col in incoming_carry and col not in row_map:
                    remaining, text = incoming_carry[col]
                    row_map[col] = text
                    if remaining - 1 > 0:
                        next_carry[col] = (remaining - 1, text)
                    col += 1
                    continue
                if cell_idx >= len(cells):
                    break
                cell = cells[cell_idx]
                text = self._normalize_header_text(cell.get_text())
                colspan = self._safe_positive_int(cell.get("colspan"), default=1)
                rowspan = self._safe_positive_int(cell.get("rowspan"), default=1)
                for c in range(col, col + colspan):
                    row_map[c] = text
                    if rowspan > 1:
                        next_carry[c] = (rowspan - 1, text)
                col += colspan
                cell_idx += 1
            final.update(row_map)
            carry = next_carry

        return final

    @staticmethod
    def _header_row_group(table: Tag) -> list[Tag]:
        """ヘッダ行群を返す (`<thead>` 優先、無ければ `<th>` を含む最初の行)"""
        thead = table.find("thead")
        if isinstance(thead, Tag):
            thead_rows = [r for r in thead.find_all("tr") if isinstance(r, Tag)]
            if thead_rows:
                return thead_rows
        for tr in table.find_all("tr"):
            if isinstance(tr, Tag) and tr.find("th") is not None:
                return [tr]
        return []

    @staticmethod
    def _normalize_header_text(text: str) -> str:
        """ヘッダセルの文字列を正規化する (全角空白/NFKC/前後空白除去)"""
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("　", " ")
        return " ".join(normalized.split())

    @staticmethod
    def _safe_positive_int(value: object, *, default: int) -> int:
        """`colspan`/`rowspan` 属性値を安全に int 化する (不正値は default)"""
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
