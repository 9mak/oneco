"""浜松市はぴまるの丘（保護犬） rule-based adapter

対象ドメイン:
    https://www.hama-aikyou.jp/hogoinu/index.html

特徴:
- 浜松市動物愛護教育センター（通称「はぴまるの丘」）の専用ドメイン上で
  公開される保護犬一覧ページ。`<main id="main">` 配下の本文は中央区・浜名区
  ・天竜区の 3 行政区ごとに `<h2>` セクションで区切られ、各区の中に動物
  情報テーブルか「現在、X区で保護された犬はいません。」という告知が入る
  single_page 形式である。
- `<h2>保護されている犬を引き取るには</h2>` 以降は引取り手続きの説明セクション
  であり、その内部にも `<table>` が出現する（受付窓口・提出書類等）。これら
  運用テーブルは動物データではないため抽出対象から除外する必要がある。
- 0 件告知は `<span class="color-01">現在、X区で保護された犬はいません。</span>`
  という構造で記述される。adapter は ParsingError ではなく空リストを返す
  「在庫 0 件」として扱う（pref_shizuoka と同様）。
- 動物が居るときの正確な markup はサイト側で実データが確認できないため、
  amagasaki と同様にヘッダ `<th>` のラベルから列マッピングを動的に構築する
  ラベル駆動方式を採用する。同サイトのテーブル列見出しは「問合せ番号」
  「犬種」「性別」「毛色」「保護日」「保護場所」等を想定している。
- リポジトリに保存されたフィクスチャは二重 UTF-8 mojibake (latin-1 解釈
  → utf-8 再保存) になっているため、`_load_rows` で「浜松」が含まれない
  場合に逆変換を試みる。実運用 (requests) ではこの補正は no-op となる。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class HamaAikyouAdapter(SinglePageTableAdapter):
    """浜松市はぴまるの丘（保護犬）用 rule-based adapter

    本文中の各 `<h2>区名</h2>` セクション配下の `<table>` を動物データ表として
    抽出する single_page 形式。引取手続き等の非動物セクションは除外する。
    """

    # 個別行は各区テーブルの `<tr>`。行の収集自体は `_load_rows` で
    # セクション単位にフィルタするため、契約充足のためのプレースホルダ。
    ROW_SELECTOR: ClassVar[str] = "tbody tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 動物データセクションを示す区名（h2 テキストに完全一致 or 部分一致）。
    # サイト側で行政区再編が起きても拾えるよう、現行 3 区を列挙する。
    _ANIMAL_SECTION_HEADINGS: ClassVar[tuple[str, ...]] = (
        "中央区",
        "浜名区",
        "天竜区",
    )

    # 動物データ以外の運用説明セクション（除外用）。
    # 「保護されている犬を引き取るには」等の手続き説明は対象外。
    _NON_ANIMAL_HEADING_KEYWORDS: ClassVar[tuple[str, ...]] = (
        "引き取る",
        "手続き",
        "問合",
        "連絡",
    )

    # 0 件告知パターン: 「現在、◯◯区で保護された犬はいません。」など
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"現在[、,]?[^。]*?保護[^。]*?(?:犬|猫|動物)[^。]*?(?:いません|ありません|おりません)"
    )

    # ヘッダ列名 → RawAnimalData フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "犬種": "species",
        "種類": "species",
        "種別": "species",
        "性別": "sex",
        "毛色": "color",
        "色": "color",
        "体格": "size",
        "大きさ": "size",
        "推定年齢": "age",
        "年齢": "age",
        "保護日": "shelter_date",
        "収容日": "shelter_date",
        "発見日": "shelter_date",
        "保護場所": "location",
        "収容場所": "location",
        "発見場所": "location",
        "場所": "location",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """各区セクション配下の `<table>` 内 `<tr>` を全区ぶん集めて返す

        - 二重 UTF-8 mojibake を補正
        - `_ANIMAL_SECTION_HEADINGS` のいずれかにマッチする `<h2>` 配下のみ走査
        - 次の `<h2>` に到達した時点でそのセクションを終了
        - 引取手続き等の非動物セクションは無視
        - 各テーブルのヘッダ行 (`<th>` のみで構成) は除外
        - 動物が居なければ空リストを返す
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「浜松」「保護」のいずれも含まれない場合のみ
        # latin-1 → utf-8 の逆変換を試みる。
        if "浜松" not in html and "保護" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for heading in self._iter_animal_section_headings(soup):
            for table in self._iter_section_tables(heading):
                body = table.find("tbody")
                body_tag = body if isinstance(body, Tag) else table
                for tr in body_tag.find_all("tr"):
                    if not isinstance(tr, Tag):
                        continue
                    if self._is_header_row(tr):
                        continue
                    rows.append(tr)

        self._rows_cache = rows
        return self._rows_cache

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """仮想 URL リストを返す（在庫 0 件は空リストを返す）

        基底実装は行 0 件で `ParsingError` を投げるが、本サイトは
        「現在、X区で保護された犬はいません。」が常時運用される正常状態の
        ため、empty-state 告知 / 区見出しの存在が確認できれば空リストを返す。
        いずれも見つからない場合のみ ParsingError として扱う。
        """
        rows = self._load_rows()
        if not rows:
            html = self._html_cache or ""
            if self._EMPTY_STATE_PATTERN.search(html):
                return []
            soup = BeautifulSoup(html, "html.parser")
            if any(
                True for _ in self._iter_animal_section_headings(soup)
            ):
                # 区見出しはあるがテーブルも告知も無い → 念のため空扱い
                return []
            raise ParsingError(
                f"区見出し ({'/'.join(self._ANIMAL_SECTION_HEADINGS)}) が"
                f"見つかりません",
                selector="h2",
                url=self.site_config.list_url,
            )

        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """1 行から RawAnimalData を構築する

        所属区はその行が属する `<h2>区名</h2>` から復元し、location 列が
        無いテーブルでも区名で location を埋める。species は行内テキスト中の
        「犬」「猫」優先、無ければサイト名（保護犬）から「犬」既定。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]

        # 該当行のテーブルから列マップを構築（テーブルごとにヘッダが
        # 異なる可能性があるため、行が属する <table> ごとに解決する）
        table = self._find_ancestor_table(row)
        col_to_field = self._build_column_field_map(table) if table else {}

        cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]
        fields: dict[str, str] = {}
        for col_idx, field_name in col_to_field.items():
            if col_idx < len(cells):
                value = cells[col_idx].get_text(" ", strip=True)
                if value and field_name not in fields:
                    fields[field_name] = value

        # 区名（行が属する <h2> セクション）
        region = self._region_name_for(row)

        # 行テキスト全体から species 推定
        row_text = row.get_text(separator=" ", strip=True)
        species = self._infer_species(
            row_text, fields.get("species", ""), self.site_config.name
        )

        location = fields.get("location", "")
        if region and region not in location:
            location = f"{region} {location}".strip() if location else region

        # 行内に電話番号が含まれていれば抽出（実サイトでは稀だが安全策）
        phone = self._normalize_phone(row_text)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get(
                    "shelter_date", self.SHELTER_DATE_DEFAULT
                ),
                location=location,
                phone=phone,
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @classmethod
    def _iter_animal_section_headings(
        cls, soup: BeautifulSoup
    ) -> list[Tag]:
        """動物データセクションを示す `<h2>` を順に列挙する

        - `_ANIMAL_SECTION_HEADINGS` のいずれかを含むテキストを持つ `<h2>`
        - 引取手続き等を示すキーワードを含む `<h2>` は除外
        """
        result: list[Tag] = []
        for h in soup.find_all("h2"):
            if not isinstance(h, Tag):
                continue
            text = h.get_text(strip=True)
            if not text:
                continue
            if any(kw in text for kw in cls._NON_ANIMAL_HEADING_KEYWORDS):
                continue
            if any(rg in text for rg in cls._ANIMAL_SECTION_HEADINGS):
                result.append(h)
        return result

    @classmethod
    def _iter_section_tables(cls, heading: Tag) -> list[Tag]:
        """`heading` の後続から、次の `<h2>` までに現れる `<table>` を返す"""
        tables: list[Tag] = []
        for sibling in heading.find_all_next():
            if not isinstance(sibling, Tag):
                continue
            if sibling.name == "h2" and sibling is not heading:
                break
            if sibling.name == "table":
                tables.append(sibling)
        return tables

    @staticmethod
    def _find_ancestor_table(node: Tag) -> Tag | None:
        """node を内包する最も近い `<table>` を返す"""
        for parent in node.parents:
            if isinstance(parent, Tag) and parent.name == "table":
                return parent
        return None

    def _build_column_field_map(self, table: Tag) -> dict[int, str]:
        """`<th>` を読み取り、列インデックス → RawAnimalData フィールドを返す"""
        # `<thead><tr><th>...</th></tr></thead>` を優先
        header_row: Tag | None = None
        thead = table.find("thead")
        if isinstance(thead, Tag):
            tr = thead.find("tr")
            if isinstance(tr, Tag):
                header_row = tr
        if header_row is None:
            tr = table.find("tr")
            if isinstance(tr, Tag) and self._is_header_row(tr):
                header_row = tr
        if header_row is None:
            return {}

        col_map: dict[int, str] = {}
        cells = [
            c for c in header_row.find_all(["th", "td"]) if isinstance(c, Tag)
        ]
        for idx, cell in enumerate(cells):
            label = cell.get_text(strip=True)
            field = self._LABEL_TO_FIELD.get(label)
            if field and idx not in col_map:
                col_map[idx] = field
        return col_map

    @classmethod
    def _region_name_for(cls, row: Tag) -> str:
        """row が属する `<h2>区名</h2>` のテキストを返す（無ければ空文字）"""
        for prev in row.find_all_previous("h2"):
            if not isinstance(prev, Tag):
                continue
            text = prev.get_text(strip=True)
            if not text:
                continue
            if any(kw in text for kw in cls._NON_ANIMAL_HEADING_KEYWORDS):
                # 非動物セクションは飛ばしてさらに上を探す
                continue
            for rg in cls._ANIMAL_SECTION_HEADINGS:
                if rg in text:
                    return rg
        return ""

    @staticmethod
    def _is_header_row(tr: Tag) -> bool:
        """`<th>` のみで構成される行をヘッダ行とみなす"""
        cells = [c for c in tr.find_all(["th", "td"]) if isinstance(c, Tag)]
        if not cells:
            return False
        return all(c.name == "th" for c in cells)

    @staticmethod
    def _infer_species(
        row_text: str, species_value: str, site_name: str
    ) -> str:
        """species を推定する

        優先順: 「種類/犬種」列値 → 行全体テキスト → サイト名 → "犬" 既定
        本サイトは「保護犬」一覧なのでサイト名から既定値「犬」を拾う。
        """
        for source in (species_value, row_text, site_name):
            if not source:
                continue
            if "犬" in source:
                return "犬"
            if "猫" in source:
                return "猫"
        return "犬"


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name: 浜松市はぴまるの丘（保護犬）` と完全一致させる。
_SITE_NAME = "浜松市はぴまるの丘（保護犬）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, HamaAikyouAdapter)
