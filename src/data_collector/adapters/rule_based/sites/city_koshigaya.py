"""越谷市保健所 rule-based adapter

対象ドメイン: https://www.city.koshigaya.saitama.jp/
                kurashi_shisei/fukushi/hokenjo/pet/hogo/

特徴:
- 同一テンプレート上で 3 サイト (保護犬 / 保護猫 / 個人保護犬猫)
  を運用する single_page 形式。URL パスのみ異なる:
    .../hogo/koshigaya_contents_dog.html (保護犬)
    .../hogo/koshigaya_contents_cat.html (保護猫)
    .../hogo/hogo_kojin.html             (個人保護犬猫)
- 越谷市の CMS テンプレートでは本文が `div#tmp_honbun` 配下に出力される。
  動物データは「種類 / 性別 / 年齢 / 毛色 / 体格 / 備考」の 6 カラム
  `<table>` で表現され、収容場所/収容日/収容期限は別の 3 カラム `<table>`
  に並列で並ぶ。動物 1 件 = (動物テーブル N 行目, 場所テーブル N 行目)
  というペア構造。
- 在庫 0 件の場合 (本フィクスチャがこのケース): 両テーブルは存在するが
  すべてのセルが空 (`&nbsp;` のみ)。さらに本文上部に
  「★現在、情報はありません。」という告知 `<p>` が入る。
  この状態は ParsingError ではなく "0 件" として扱い、
  `fetch_animal_list` は空リストを返す。
- 動物種別 (犬/猫/その他) はサイト名から推定する
  ("個人保護犬猫" は犬猫いずれもありうるため "その他" 扱い)。
- 越谷市ページは fixture 化される際に二重 UTF-8 mojibake
  (本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
  保存) になるケースがあるため、HTML キャッシュ取得時に逆変換を試みる。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「★現在、情報はありません。」「現在、保護・収容中の犬はおりません。」
# 等の 0 件告知パターン。表記揺れ (です/ません/おりません/いません/ありません)
# を緩く吸収する。
_EMPTY_STATE_PATTERN = re.compile(
    r"(?:現在|現時点)[^。]*?(?:ありません|いません|おりません)"
)

# 6 カラム動物テーブルのヘッダ判定用ラベル (種類は他テーブルに含まれない)
_ANIMAL_TABLE_HEADER_KEYWORDS = ("種類", "性別", "年齢", "毛色", "体格")

# 場所テーブルのヘッダ判定用ラベル
_LOCATION_TABLE_HEADER_KEYWORDS = ("収容場所", "収容日")


class CityKoshigayaAdapter(SinglePageTableAdapter):
    """越谷市保健所用 rule-based adapter

    保護犬 / 保護猫 / 個人保護犬猫 の 3 サイトで共通テンプレートを使用する
    single_page 形式。動物データテーブル (6 列) の各 `<tbody><tr>` を
    1 動物として扱い、場所テーブル (3 列) の同じインデックスの `<tr>` を
    並列で読んで location / shelter_date を補う。
    """

    # 本文 (`div#tmp_honbun`) 配下のテーブル `<tbody>` 内 `<tr>` を候補とする。
    # 動物テーブルかどうかの絞り込みは `_load_rows` 側で行う。
    ROW_SELECTOR: ClassVar[str] = "div#tmp_honbun table tbody tr"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 動物テーブルの列インデックス → RawAnimalData フィールド名。
    # 値の取り出しは `extract_animal_details` のオーバーライドが行うが、
    # 契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species_detail",  # 種類 (柴犬等の具体名 / 在庫 0 件では空)
        1: "sex",             # 性別
        2: "age",             # 年齢
        3: "color",           # 毛色
        4: "size",            # 体格
        5: "features",        # 備考
    }
    # 動物テーブル自体には「場所」列はない (別テーブル)
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物テーブルの `<tr>` のみ抽出してキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 本文 `div#tmp_honbun` 配下の `<table>` のうち、ヘッダに「種類」
          を含む 6 列テーブルだけを動物テーブルとして採用
        - その動物テーブルの `<tbody><tr>` のうち、全セルが実質空のものを
          除外したものを返す (在庫 0 件のときは空配列になる)
        - 場所テーブルの `<tr>` も同時に `_location_rows_cache` に保存し、
          `extract_animal_details` から並列参照できるようにする
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「越谷」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "越谷" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        honbun = soup.select_one("div#tmp_honbun")
        if honbun is None:
            self._rows_cache = []
            self._location_rows_cache: list[Tag] = []
            return self._rows_cache

        animal_rows: list[Tag] = []
        location_rows: list[Tag] = []

        for table in honbun.find_all("table"):
            if not isinstance(table, Tag):
                continue
            header_text = self._collect_header_text(table)
            data_rows = self._collect_data_rows(table)
            if self._is_animal_table(header_text):
                animal_rows.extend(data_rows)
            elif self._is_location_table(header_text):
                location_rows.extend(data_rows)

        self._location_rows_cache = location_rows
        self._rows_cache = animal_rows
        return self._rows_cache

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、越谷市のサイトは
        通常運用が「現在、情報はありません。」という告知ページのため、
        在庫 0 件が正常状態として頻出する。
        - 動物テーブルがそもそも見当たらない → ParsingError
        - 動物テーブルはあるが全行が空 → 空リストを返す
        """
        rows = self._load_rows()
        category = self.site_config.category

        if not rows:
            # 「現在、情報はありません」等の正常な 0 件状態は許容
            if self._html_cache and (
                _EMPTY_STATE_PATTERN.search(self._html_cache)
                or "情報はありません" in self._html_cache
            ):
                return []
            # 動物テーブル自体が見つからない (テンプレート崩壊) ときは ParsingError
            raise ParsingError(
                "動物テーブルが見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )

        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """動物テーブル `<tr>` から RawAnimalData を構築する

        並列に並ぶ場所テーブル (収容場所/収容日/収容期限) の同インデックス
        `<tr>` を参照し、location と shelter_date を補完する。
        動物種別はサイト名から推定する (HTML の「種類」列は柴犬等の具体名)。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        tr = rows[idx]
        cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]

        def _cell_text(i: int) -> str:
            if i >= len(cells):
                return ""
            text = cells[i].get_text(separator=" ", strip=True)
            # `&nbsp;` ( ) や全半角スペースのみは空扱い
            if not text.replace(" ", "").strip():
                return ""
            return re.sub(r"[  　]+", " ", text).strip()

        sex = _cell_text(1)
        age = _cell_text(2)
        color = _cell_text(3)
        size = _cell_text(4)

        # 場所テーブルの並列参照 (3 列: 収容場所 / 収容日 / 収容期限)
        location = ""
        shelter_date = self.SHELTER_DATE_DEFAULT
        loc_rows = getattr(self, "_location_rows_cache", [])
        if idx < len(loc_rows):
            loc_cells = [
                c for c in loc_rows[idx].find_all(["td", "th"])
                if isinstance(c, Tag)
            ]
            if len(loc_cells) >= 1:
                t = loc_cells[0].get_text(separator=" ", strip=True)
                if t.replace(" ", "").strip():
                    location = re.sub(r"[  　]+", " ", t).strip()
            if len(loc_cells) >= 2:
                t = loc_cells[1].get_text(separator=" ", strip=True)
                if t.replace(" ", "").strip():
                    shelter_date = re.sub(r"[  　]+", " ", t).strip()

        # 動物種別: HTML の「種類」(柴犬/雑種等) は具体名のためサイト名から推定
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
                color=color,
                size=size,
                shelter_date=shelter_date,
                location=location,
                phone="",
                image_urls=self._extract_row_images(tr, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _collect_header_text(table: Tag) -> str:
        """テーブルのヘッダ (`<thead>` 優先、無ければ最初の行) のテキストを連結"""
        thead = table.find("thead")
        if isinstance(thead, Tag):
            return thead.get_text(separator=" ", strip=True)
        # `<thead>` が無い場合は最初の `<tr>` を見出し相当として扱う
        first_tr = table.find("tr")
        if isinstance(first_tr, Tag):
            ths = first_tr.find_all("th")
            if ths:
                return " ".join(
                    th.get_text(separator=" ", strip=True) for th in ths
                )
        return ""

    @staticmethod
    def _collect_data_rows(table: Tag) -> list[Tag]:
        """`<tbody>` 内の `<tr>` のうち、全セルが実質空でないものを返す"""
        tbody = table.find("tbody")
        if isinstance(tbody, Tag):
            trs = tbody.find_all("tr")
        else:
            # `<tbody>` 省略時は `<tr>` 全件から `<th>` のみの行を除外
            trs = [
                tr for tr in table.find_all("tr")
                if isinstance(tr, Tag) and tr.find("td") is not None
            ]
        result: list[Tag] = []
        for tr in trs:
            if not isinstance(tr, Tag):
                continue
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            # 全セルが空白 (`&nbsp;` ` ` `<br>` 含む) なら在庫無し行として除外
            non_empty = False
            for c in cells:
                txt = c.get_text(separator="", strip=True).replace(" ", "")
                if txt.strip():
                    non_empty = True
                    break
            if non_empty:
                result.append(tr)
        return result

    @staticmethod
    def _is_animal_table(header_text: str) -> bool:
        """ヘッダ文字列が動物テーブル (種類/性別/年齢/毛色/体格 を含む) か判定"""
        # 主要 5 ラベルのうち 3 つ以上含まれていれば動物テーブルとみなす
        # (テンプレートの細かい揺れに対する保険)
        hits = sum(
            1 for kw in _ANIMAL_TABLE_HEADER_KEYWORDS if kw in header_text
        )
        return hits >= 3

    @staticmethod
    def _is_location_table(header_text: str) -> bool:
        """ヘッダ文字列が場所テーブル (収容場所/収容日 を含む) か判定"""
        return all(kw in header_text for kw in _LOCATION_TABLE_HEADER_KEYWORDS)

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        - "犬猫" / "個人保護犬猫" を含む → "その他" (犬猫いずれもありうる)
        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - いずれにも該当しない → "" (空文字)
        """
        if "犬猫" in name:
            return "その他"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 埼玉県` かつ `city.koshigaya.saitama.jp`
# ドメインのもの。
for _site_name in (
    "越谷市（保護犬）",
    "越谷市（保護猫）",
    "越谷市（個人保護犬猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityKoshigayaAdapter)
