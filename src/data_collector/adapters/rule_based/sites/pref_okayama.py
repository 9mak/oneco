"""岡山県動物愛護センター rule-based adapter

対象ドメイン:
- https://www.pref.okayama.jp/page/859555.html

特徴:
- `<div id="main_body">` 配下に「保護収容情報（犬）」「保護収容情報（猫）」
  「保護収容情報（その他）」の 3 つの `<table>` が並ぶ single_page 形式。
- 各 `<table>` の最初の `<tr>` はヘッダ行（`<th>` 多数）でデータではない。
- 列構成は犬/猫共通で固定:
    0:収容日 | 1:管理番号 | 2:種類 | 3:年齢 | 4:毛色 | 5:性別 |
    6:体格 | 7:特徴 | 8:場所 | 9:写真(<img>)
- 種別 (犬/猫) はテーブルの `<caption>` に書かれた「保護収容情報（犬）」等から
  判定する。`その他` テーブルもあるが、内容はラベル不明 (犬猫以外/負傷動物)
  のため `<caption>` から推定できなければ空文字 (上流 normalizer に委譲)。
- `その他` テーブルは構成上ほぼ常に「全セル空 (`&nbsp;` のみ)」のプレースホルダ
  行を持つため、データ行が空 (収容日も管理番号も無い) の場合はスキップする。
- フィクスチャは Shift_JIS のバイト列を一旦 UTF-8 として誤デコードしてから
  保存された二重 mojibake 状態 (例: "åç©" 等) のため、
  `_load_rows` で `latin-1 → utf-8` の逆変換を試みる。
- 在庫 0 件 (テーブルが存在するが全行プレースホルダ) でも `ParsingError` を
  出さず、`fetch_animal_list` は空リストを返す。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class PrefOkayamaAdapter(SinglePageTableAdapter):
    """岡山県動物愛護センターの保護収容情報用 rule-based adapter

    `<div id="main_body">` 配下の犬/猫/その他の 3 テーブルを横断して
    各データ行を 1 動物として束ねる single_page 形式。
    `_load_rows` と `extract_animal_details` をオーバーライドし、
    テーブル単位の `<caption>` から species を確定させる。
    """

    # SinglePageTableAdapter の契約 (空文字禁止) を満たすための宣言。
    # 実際の行抽出は `_load_rows` のオーバーライドで行うため未使用。
    ROW_SELECTOR: ClassVar[str] = "div#main_body table tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 列構成は犬/猫共通で固定。`extract_animal_details` のオーバーライドで
    # 直接参照するため、基底側からは使われない。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",
        1: "management_number",
        2: "breed",
        3: "age",
        4: "color",
        5: "sex",
        6: "size",
        7: "feature",
        8: "location",
    }
    LOCATION_COLUMN: ClassVar[int | None] = 8
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        # 各データ行の species (犬/猫/その他/"") を別キャッシュに保持する。
        # `_rows_cache` (基底) は Tag のリストとして使う必要があるため、
        # 並びを揃えた species リストを並列に持つ。
        self._row_species_cache: list[str] | None = None

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、犬/猫/その他テーブルのデータ行を集める

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - `<div id="main_body">` 配下の `<table>` を順に処理
        - 各 `<table>` のヘッダ行 (`<th>` のみで構成される最初の `<tr>`) を除外
        - 空プレースホルダ行 (収容日と管理番号がいずれも空) もスキップ
        - 同時に `_row_species_cache` に行ごとの species 文字列を格納する
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: 復元後にしか出てこない「岡山」が無ければ逆変換を試みる
        if "岡山" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        # 動物テーブルは `div#main_body` 配下に置かれる。
        # フォールバックとして body 全体からも探索する。
        scope = soup.select_one("div#main_body") or soup.body or soup

        data_rows: list[Tag] = []
        species_list: list[str] = []
        for table in scope.find_all("table"):
            if not isinstance(table, Tag):
                continue
            species = self._infer_species_from_caption(table)
            for row in table.find_all("tr"):
                if not isinstance(row, Tag):
                    continue
                cells = row.find_all(["td", "th"])
                # ヘッダ行 (td が無く th のみ) は除外
                if not row.find("td"):
                    continue
                if not cells:
                    continue
                # 空プレースホルダ行 (収容日 + 管理番号がいずれも空) は除外
                shelter = cells[0].get_text(strip=True) if len(cells) > 0 else ""
                mgmt = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                if not shelter and not mgmt:
                    continue
                data_rows.append(row)
                species_list.append(species)

        self._rows_cache = data_rows
        self._row_species_cache = species_list
        return data_rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、岡山県のページは
        収容ゼロの状態が正常運用としてあり得るため、空リストを許容する。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """テーブル行 (10 列固定) から RawAnimalData を構築する

        species はテーブルの `<caption>` から確定済みの値を使う
        (`<td>` 内の "種類" 列は「雑種」「成犬」等の補足情報なので
        species ではなく breed として扱い、データには直接埋め込まない)。
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

        def _cell_text(i: int) -> str:
            return cells[i].get_text(strip=True) if i < len(cells) else ""

        shelter_date = _cell_text(0)
        # _cell_text(1) は管理番号 (現時点では RawAnimalData に保存先が無い)
        # _cell_text(2) は種類 (breed) — RawAnimalData の species とは別概念
        age = _cell_text(3)
        color = _cell_text(4)
        sex = self._normalize_sex_token(_cell_text(5))
        size = _cell_text(6)
        # _cell_text(7) は特徴 (首輪等) — 現状の RawAnimalData には保存先が無い
        location = _cell_text(8)

        assert self._row_species_cache is not None  # _load_rows で必ずセット
        species = self._row_species_cache[idx]

        image_urls = self._extract_row_images(row, virtual_url)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
                color=color,
                size=size,
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_caption(table: Tag) -> str:
        """`<caption>` の文言からテーブルの species を判定する

        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - "その他" を含むなど判定不能 → "" (空文字: 上流 normalizer に委譲)
        """
        caption = table.find("caption")
        text = caption.get_text(separator="", strip=True) if caption else ""
        if "犬" in text:
            return "犬"
        if "猫" in text:
            return "猫"
        return ""

    @staticmethod
    def _normalize_sex_token(token: str) -> str:
        """「雄/雌」表記を「オス/メス」に統一する (上流 normalizer の入力候補)"""
        if not token:
            return ""
        if token in ("雄", "オス", "おす", "♂"):
            return "オス"
        if token in ("雌", "メス", "めす", "♀"):
            return "メス"
        return token


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `pref.okayama.jp` ドメイン (保護動物 1 件) を登録する。
# 岡山市 (`city.okayama.jp`) と倉敷市 (`city.kurashiki.okayama.jp`) は
# 別テンプレートのため対象外 (それぞれ別 adapter で対応するか、
# 既存の汎用 wordpress_list 系 adapter で処理する)。
for _site_name in ("岡山県動物愛護センター（保護動物）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, PrefOkayamaAdapter)
