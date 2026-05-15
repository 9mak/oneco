"""尼崎市動物愛護センター（収容動物） rule-based adapter

対象ドメイン:
    https://www.city.amagasaki.hyogo.jp/kurashi/iryou/pet/051syuuyoudoubutu.html

特徴:
- 尼崎市公式 CMS (FreshIdent 系) の `<main id="page">` 配下に
  本文が配置される単一ページ。個別 detail ページは存在しない single_page。
- ページには複数の `<table class="w100">` が並んでいるが、その大半は
  「収容施設の連絡先」「自治体管轄一覧」など動物リストとは無関係な情報。
  動物リストの起点は `<h2>返還対象動物一覧</h2>` の見出し。
- 動物が 0 件のときは `<div class="boxnotice">現在、返還対象動物はいません。</div>`
  が表示され、テーブルや動物カードは出力されない。本 adapter ではこれを
  `ParsingError` ではなく「在庫 0 件」として扱う。
- 動物が居るときの正確な markup は将来の運用次第だが、本サイトは同一 CMS の
  他ページで `<table class="w100">` をデータ提示に使う実績があるため、
  「返還対象動物一覧」見出し以降に現れる最初の `<table>` を動物データ表として
  扱い、その `<tbody><tr>` を 1 頭分の行として抽出する設計とする。
- カラム配置はサイトの実データが無いため `_LABEL_TO_FIELD` によるラベル駆動の
  ヘッダ解析を用いる。`<thead>` の `<th>` テキスト (例: 「種類」「性別」
  「毛色」「収容日」「収容場所」) を読み取り、列インデックスとフィールド名を
  動的にマッピングする。
- species は犬/猫の明示が無い列タイトルでも、行内テキストに「犬」「猫」が
  あれば優先的に判定する。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityAmagasakiAdapter(SinglePageTableAdapter):
    """尼崎市動物愛護センター（収容動物）用 rule-based adapter

    `<h2>返還対象動物一覧</h2>` 以降に現れる最初の `<table>` の `<tbody><tr>`
    を 1 頭分のカードとして抽出する single_page 形式。
    """

    # 「返還対象動物一覧」直後のデータテーブルの行を抽出する。
    # 実際のフィルタリングは `_load_rows` のオーバーライド側で行うため
    # ここでは契約充足のためのプレースホルダ値を入れる。
    ROW_SELECTOR: ClassVar[str] = "tbody tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 列マッピングはヘッダから動的構築するため空指定
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # データ表の起点見出し (本文中で一意)
    _ANIMAL_HEADING_TEXT: ClassVar[str] = "返還対象動物一覧"

    # 0 件告知テキスト (`<div class="boxnotice">` 等に格納される)
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:返還対象|収容|保護)(?:動物|犬|猫)[^。]*?"
        r"(?:いません|ありません|おりません)"
    )

    # ヘッダ列名 → RawAnimalData フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "種類": "species",
        "種別": "species",
        "性別": "sex",
        "毛色": "color",
        "色": "color",
        "体格": "size",
        "大きさ": "size",
        "推定年齢": "age",
        "年齢": "age",
        "収容日": "shelter_date",
        "収容年月日": "shelter_date",
        "保護日": "shelter_date",
        "発見日": "shelter_date",
        "収容場所": "location",
        "発見場所": "location",
        "場所": "location",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """`返還対象動物一覧` 見出し以降の最初のデータ表の `<tr>` を返す

        基底実装は ROW_SELECTOR をページ全体に適用するため、本サイトの
        ように本文以外にも複数の `<table>` が並ぶページでは無関係な行まで
        拾ってしまう。本オーバーライドでは見出しを起点にデータ表を限定し、
        `<tbody>` 配下の `<tr>` のみを返す (見つからなければ空リスト)。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        table = self._find_animal_table(soup)
        if table is None:
            self._rows_cache = []
            return self._rows_cache

        body = table.find("tbody")
        body_tag = body if isinstance(body, Tag) else table
        rows = [tr for tr in body_tag.find_all("tr") if isinstance(tr, Tag)]
        # `<thead><tr>` が `find_all("tr")` に含まれる場合は除外
        rows = [tr for tr in rows if not self._is_header_row(tr)]
        self._rows_cache = rows
        return self._rows_cache

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物の仮想 URL リストを返す (0 件時は空リスト)

        基底は行 0 件で `ParsingError` を投げるが、本サイトは「現在、返還対象
        動物はいません。」が常時運用される正常状態のため、empty-state 告知を
        検出した場合は空リストを返す。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and self._EMPTY_STATE_PATTERN.search(self._html_cache):
                return []
            # 見出し自体が無い → テンプレート崩壊として例外化
            soup = BeautifulSoup(self._html_cache or "", "html.parser")
            if self._find_animal_heading(soup) is None:
                raise ParsingError(
                    f"見出し『{self._ANIMAL_HEADING_TEXT}』が見つかりません",
                    selector="h2",
                    url=self.site_config.list_url,
                )
            # 見出しはあるが表も告知も無い → 念のため空リスト扱い
            return []

        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 行から RawAnimalData を構築する

        ヘッダ `<th>` を読み取り `_LABEL_TO_FIELD` で列インデックスと
        RawAnimalData フィールドを動的にマッピングする。species は行内
        テキストに「犬」「猫」が含まれる場合を最優先で判定する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]

        # ヘッダ → 列マップ
        col_to_field = self._build_column_field_map()

        cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]
        fields: dict[str, str] = {}
        for col_idx, field_name in col_to_field.items():
            if col_idx < len(cells):
                value = cells[col_idx].get_text(strip=True)
                if value and field_name not in fields:
                    fields[field_name] = value

        # species 推定: 行全体テキスト → 「種類」値 → サイト名 → "その他"
        row_text = row.get_text(separator=" ", strip=True)
        species = self._infer_species(row_text, fields.get("species", ""))

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
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
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @classmethod
    def _find_animal_heading(cls, soup: BeautifulSoup) -> Tag | None:
        """`返還対象動物一覧` を含む見出しタグを返す"""
        for h in soup.find_all(["h2", "h3"]):
            if isinstance(h, Tag) and cls._ANIMAL_HEADING_TEXT in h.get_text(strip=True):
                return h
        return None

    @classmethod
    def _find_animal_table(cls, soup: BeautifulSoup) -> Tag | None:
        """『返還対象動物一覧』見出し以降に現れる最初の `<table>` を返す"""
        heading = cls._find_animal_heading(soup)
        if heading is None:
            return None
        # 見出しの後続要素を順に走査し、次の同位以上見出しに当たるまで table を探す
        for sibling in heading.find_all_next():
            if not isinstance(sibling, Tag):
                continue
            if sibling.name in ("h2",) and sibling is not heading:
                # 次セクションに入った
                return None
            if sibling.name == "table":
                return sibling
        return None

    def _build_column_field_map(self) -> dict[int, str]:
        """データ表の `<th>` を読み取って 列インデックス → フィールド名 を構築"""
        if self._html_cache is None:
            return {}
        soup = BeautifulSoup(self._html_cache, "html.parser")
        table = self._find_animal_table(soup)
        if table is None:
            return {}

        # `<thead><tr><th>...</th></tr></thead>` を優先
        header_row: Tag | None = None
        thead = table.find("thead")
        if isinstance(thead, Tag):
            tr = thead.find("tr")
            if isinstance(tr, Tag):
                header_row = tr
        if header_row is None:
            # `<thead>` が無いとき最初の `<tr>` を見出し行と仮定
            tr = table.find("tr")
            if isinstance(tr, Tag) and self._is_header_row(tr):
                header_row = tr
        if header_row is None:
            return {}

        col_map: dict[int, str] = {}
        cells = [c for c in header_row.find_all(["th", "td"]) if isinstance(c, Tag)]
        for idx, cell in enumerate(cells):
            label = cell.get_text(strip=True)
            field = self._LABEL_TO_FIELD.get(label)
            if field and idx not in col_map:
                col_map[idx] = field
        return col_map

    @staticmethod
    def _is_header_row(tr: Tag) -> bool:
        """`<th>` のみで構成されている行をヘッダ行とみなす"""
        cells = [c for c in tr.find_all(["th", "td"]) if isinstance(c, Tag)]
        if not cells:
            return False
        return all(c.name == "th" for c in cells)

    @staticmethod
    def _infer_species(row_text: str, species_value: str) -> str:
        """行テキストおよび「種類」値から動物種別を推定する"""
        for source in (species_value, row_text):
            if not source:
                continue
            if "犬" in source:
                return "犬"
            if "猫" in source:
                return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
_SITE_NAME = "尼崎市動物愛護センター（収容動物）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, CityAmagasakiAdapter)
