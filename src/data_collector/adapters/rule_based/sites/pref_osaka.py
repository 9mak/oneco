"""大阪府動物愛護管理センター rule-based adapter

対象ドメイン: https://www.pref.osaka.lg.jp/o120200/doaicenter/doaicenter/maigoken.html

特徴:
- 1 ページに犬・猫の情報が `<h4>` セクション + `<table>` のセットで並ぶ
  single_page 形式。テーブル 1 つが動物 1 件に対応する。
- 構造例 (犬の例):
    <h4><span class="txt_big"><strong>犬</strong></span></h4>
    <table>
      <tbody>
        <tr><td rowspan="9"><img src=".../26-00034.jpg" /></td>
            <th>受付番号</th><td>26-00034</td></tr>
        <tr><th>収容日</th><td>令和8年5月11日</td></tr>
        <tr><th>収容場所</th><td>泉南郡熊取町山の手台</td></tr>
        <tr><th>犬の特徴</th><td>
            <p>種類：雑種</p><p>性別：雌</p><p>毛色：白黒</p>
            <p>体格：小</p><p>首輪：水色</p><p>引綱：なし</p>
        </td></tr>
        <tr><th>連絡先</th><td>
            <p>施設名:大阪府動物愛護管理センター…</p>
            <p>電話番号：072-464-9777</p>…</td></tr>
      </tbody>
    </table>
- 在庫 0 件の場合は同じ構造のテーブルが残るが、各 td は `&nbsp;` 等で空。
  受付番号が空のテーブルは除外する。
- 同じページ内に「政令市・中核市の連絡先テーブル」(`class="datatable"`)
  も存在するが受付番号 th を含まないので動物テーブルとは区別できる。
- 種別 (犬/猫) はテーブル直前の `<h4>` 見出しテキストから推定する。
- 収容日は和暦 (令和N年M月D日) で記載されるため ISO 形式 (YYYY-MM-DD) に変換。
- mojibake (二重 UTF-8) 対応: `_load_rows` で「大阪」が含まれない場合のみ
  latin-1 → utf-8 の逆変換を試みる。
- テーブル形式だが th/td が縦並びかつ「犬の特徴」セルに複数 `<p>` が入る
  特殊な形なので、基底 `SinglePageTableAdapter` の cells ベース既定実装は
  使わず `extract_animal_details` をオーバーライドする。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「令和N年M月D日」を ISO 形式に変換するための正規表現
_REIWA_DATE_RE = re.compile(r"令和\s*(\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
# 「YYYY年MM月DD日」(西暦) も念のため受け付ける
_AD_DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


class PrefOsakaAdapter(SinglePageTableAdapter):
    """大阪府動物愛護管理センター用 rule-based adapter

    1 ページ 1 サイトの single_page 形式。各動物は受付番号 th を
    持つ `<table>` 1 つで表現される。
    """

    # 動物テーブル (受付番号 th を持つもの) のみを対象にしたいので、
    # 一旦すべての `<table>` を取って _load_rows でフィルタする。
    ROW_SELECTOR: ClassVar[str] = "table"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (`<th>ラベル<td>値` の縦並び)。
    # 契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 行内ラベル (「犬の特徴」セル内の <p>種類：雑種</p> など)
    _DETAIL_LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "種類": "breed",
        "性別": "sex",
        "毛色": "color",
        "体格": "size",
    }

    # 行外ラベル (テーブルの第 1 列 th)
    _ROW_LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "受付番号": "management_number",
        "収容日": "shelter_date",
        "収容場所": "location",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物テーブルだけをキャッシュする

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 受付番号 th を含まないテーブル (政令市連絡先など) を除外
        - 受付番号の値が空のテーブル (在庫 0 件プレースホルダ) を除外
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページ本文に「大阪」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "大阪" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            if not self._is_animal_table(table):
                continue
            if self._is_empty_animal_table(table):
                continue
            rows.append(table)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        基底実装は rows が空のとき例外を出すが、大阪府のサイトは
        収容動物が居ない期間でも空テーブルが残るだけでページ自体は
        存在し続けるため、空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """1 つの `<table>` から RawAnimalData を構築する

        - 第 1 列 th から「受付番号 / 収容日 / 収容場所」を取得
        - 「犬の特徴 / 猫の特徴」セルの <p> 列から種類/性別/毛色/体格を取得
        - 「連絡先」セルから電話番号を取得
        - 種別 (犬/猫) はテーブル直前の <h4> 見出しから推定
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]

        fields: dict[str, str] = {}
        phone = ""

        for tr in table.find_all("tr"):
            if not isinstance(tr, Tag):
                continue
            th = tr.find("th")
            if not isinstance(th, Tag):
                continue
            label = th.get_text(strip=True)
            # 値 td は tr 内の最後の td (画像 td は rowspan で別位置にあるため)
            tds = [c for c in tr.find_all("td") if isinstance(c, Tag)]
            if not tds:
                continue
            value_td = tds[-1]

            # 「犬の特徴」「猫の特徴」セルは <p>種類：雑種</p> 等の並び
            if label.endswith("の特徴"):
                self._extract_detail_fields(value_td, fields)
                continue

            # 「連絡先」セルから電話番号を抽出
            if label == "連絡先":
                phone = self._extract_phone(value_td)
                continue

            # その他: 行外ラベル (受付番号/収容日/収容場所)
            field = self._ROW_LABEL_TO_FIELD.get(label)
            if not field:
                continue
            value = value_td.get_text(separator=" ", strip=True)
            if not value or value in ("\xa0", " "):
                continue
            if field == "shelter_date":
                fields[field] = self._parse_date(value) or value
            else:
                fields[field] = value

        # 種別はテーブル直前の <h4> 見出しから推定
        species = self._infer_species_from_table(table)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone=self._normalize_phone(phone),
                image_urls=self._extract_table_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _is_animal_table(table: Tag) -> bool:
        """受付番号 th を持つ場合のみ動物テーブルと判定する"""
        for th in table.find_all("th"):
            if not isinstance(th, Tag):
                continue
            if "受付番号" in th.get_text(strip=True):
                return True
        return False

    @staticmethod
    def _is_empty_animal_table(table: Tag) -> bool:
        """受付番号 td が空 (=在庫 0 件プレースホルダ) なら True を返す

        判定: 受付番号 th と同じ tr の値 td が空白/`&nbsp;` のみ。
        """
        for tr in table.find_all("tr"):
            if not isinstance(tr, Tag):
                continue
            th = tr.find("th")
            if not isinstance(th, Tag):
                continue
            if "受付番号" not in th.get_text(strip=True):
                continue
            tds = [c for c in tr.find_all("td") if isinstance(c, Tag)]
            if not tds:
                return True
            value = tds[-1].get_text(strip=True).replace("\xa0", "")
            return value == ""
        # 受付番号 行が見つからなかった = 動物テーブルではない (上で除外済み)
        return True

    def _extract_detail_fields(self, td: Tag, fields: dict[str, str]) -> None:
        """「犬の特徴 / 猫の特徴」セル内の <p> 群からフィールドを抽出"""
        for p in td.find_all("p"):
            if not isinstance(p, Tag):
                continue
            text = p.get_text(separator=" ", strip=True)
            if not text:
                continue
            label, value = self._split_label_value(text)
            if label is None or not value:
                continue
            field = self._DETAIL_LABEL_TO_FIELD.get(label)
            if field and field not in fields:
                fields[field] = value

    @staticmethod
    def _extract_phone(td: Tag) -> str:
        """連絡先セルから電話番号文字列を抽出 (正規化前の生文字列を返す)"""
        for p in td.find_all("p"):
            if not isinstance(p, Tag):
                continue
            text = p.get_text(separator=" ", strip=True)
            if "電話" in text:
                return text
        # <p> 区切りでない場合に備えてセル全体も見る
        return td.get_text(separator=" ", strip=True)

    def _extract_table_images(self, table: Tag, base_url: str) -> list[str]:
        """テーブル内の img タグから src を絶対 URL で取得"""
        urls: list[str] = []
        for img in table.find_all("img"):
            if not isinstance(img, Tag):
                continue
            src = img.get("src")
            if not src or not isinstance(src, str):
                continue
            urls.append(self._absolute_url(src, base=base_url))
        return urls

    @staticmethod
    def _split_label_value(line: str) -> tuple[str | None, str]:
        """「ラベル：値」/「ラベル:値」/「ラベル／値」/「ラベル/値」を分割"""
        for sep in ("：", ":", "／", "/"):
            if sep in line:
                label, _, value = line.partition(sep)
                return label.strip(), value.strip()
        return None, ""

    @staticmethod
    def _parse_date(text: str) -> str:
        """「令和N年M月D日」または「YYYY年M月D日」を ISO 形式に変換

        変換できなければ空文字を返す。令和元年 (令和1年) = 2019 年。
        """
        m = _REIWA_DATE_RE.search(text)
        if m:
            reiwa_y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            year = 2018 + reiwa_y  # 令和1 = 2019
            return f"{year:04d}-{mo:02d}-{d:02d}"
        m = _AD_DATE_RE.search(text)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""

    @staticmethod
    def _infer_species_from_table(table: Tag) -> str:
        """テーブル直前の `<h4>` 見出しから動物種別を推定する

        テンプレート上は <h4>犬</h4><table>...</table><h4>猫</h4><table>...
        の並び。テーブルからさかのぼって最も近い h4 を採用する。
        該当 h4 が「犬の特徴」/「猫の特徴」の th から推定するフォールバックも持つ。
        """
        # 1. 直前の sibling/ancestor を辿って h4 を探す
        node = table.find_previous("h4")
        if isinstance(node, Tag):
            text = node.get_text(strip=True)
            if "犬" in text:
                return "犬"
            if "猫" in text:
                return "猫"

        # 2. フォールバック: 「犬の特徴 / 猫の特徴」th から推定
        for th in table.find_all("th"):
            if not isinstance(th, Tag):
                continue
            t = th.get_text(strip=True)
            if "犬の特徴" in t:
                return "犬"
            if "猫の特徴" in t:
                return "猫"

        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml では 1 サイトのみ登録されている。
SiteAdapterRegistry.register(
    "大阪府動物愛護管理センター（迷い犬猫）", PrefOsakaAdapter
)
