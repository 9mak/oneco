"""三重県動物愛護管理センター rule-based adapter

対象ドメイン: http://mie-dakc.server-shared.com/maigoinujyouhou.html

特徴:
- 1 ページに迷い犬 (公示) 情報を 1 件ずつのテーブルとして並べる
  single_page 形式のサイト。個別 detail ページは存在しない。
- 各動物は `<table id="HPB_TABLE_XLS_*">` 単位で表現され、ページ内に
  動物が増えれば同形式のテーブルが追加される構造。
- テーブル構造 (1 動物 = 1 テーブル) は固定で次の通り:
    row 0: 管理番号 (例: "5-13-1") を colspan=3 のセル 1 つで表示
    row 1: [動物画像 (rowspan=9)] | "保護年月日" | "保護場所"   (header)
    row 2:                          | 値          | 値
    row 3:                          | "種類"      | "毛色"        (header)
    row 4:                          | 値          | 値
    row 5:                          | "性別"      | "公示期間"    (header)
    row 6:                          | 値          | 値
    row 7:                          | "その他特徴"| "問い合わせ先"(header)
    row 8:                          | 値          | 値
    row 9:                          | (空)        | 電話番号
- ページの HTML は Shift_JIS でホストされ、レスポンス側で
  `Content-Type: text/html; charset=Shift_JIS` を宣言する。requests は
  charset を尊重するため `_http_get` の戻り値は UTF-8 文字列として正しく
  デコードされる前提だが、リポジトリに保存されたフィクスチャは
  「UTF-8 として読み出し → latin-1 に再エンコード → Shift_JIS としてデコード」
  という二重エンコーディング状態になっているため、`_load_rows` で
  本文に「保護」(本サイト特有の漢字) が含まれていなければ逆変換を試みる。
- 動物種別はサイト名 (「迷い犬情報」) から犬で固定。HTML 上に犬種は
  「種類」(雑種/柴犬等) として記載されるが species ではなく breed 相当のため
  RawAnimalData.species は「犬」を入れる。
- 在庫 0 件の場合: 「保護年月日」を含むテーブルが存在しない HTML となるため
  `fetch_animal_list` は空リストを返す (`ParsingError` は投げない)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 「保護年月日」「種類」「性別」「その他特徴」等のラベル → 値の取り出しに
# 使うラベル集合 (ヘッダ行判定 / ラベルセルスキップ用)
_HEADER_LABELS: frozenset[str] = frozenset(
    {
        "保護年月日",
        "保護場所",
        "種類",
        "毛色",
        "性別",
        "公示期間",
        "その他特徴",
        "問い合わせ先",
    }
)


class MieDakcAdapter(SinglePageTableAdapter):
    """三重県動物愛護管理センター用 rule-based adapter

    1 ページに 1 動物 = 1 テーブルが並ぶ single_page 形式。
    `<table id="HPB_TABLE_XLS_*">` のうち「保護年月日」を含むものを
    動物テーブルとして抽出する。
    """

    # 1 動物 = 1 テーブル。`_load_rows` 側で「保護年月日」を含むものに
    # 絞り込むため、ここでは XLS_1_ プレフィックスのテーブル全体を候補とする。
    ROW_SELECTOR: ClassVar[str] = 'table[id^="HPB_TABLE_XLS_1_"]'
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (ヘッダ/値が交互行構造のため)
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物テーブル群をキャッシュ

        - フィクスチャ由来の二重エンコーディング (utf-8 → latin-1 → shift_jis)
          を補正する。実運用 (`_http_get`) では requests が charset を解釈する
          ため通常は補正不要。
        - 「保護年月日」を含まないテーブル (案内表など) は除外する。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # 二重 UTF-8 mojibake 補正: 「保護」が含まれない場合のみ逆変換
        # 一部バイトに不正な shift_jis シーケンスが混じり得るため
        # `errors="replace"` で部分回復を許容する。
        if "保護" not in html:
            try:
                html = html.encode("latin-1", errors="replace").decode(
                    "shift_jis", errors="replace"
                )
                self._html_cache = html
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for table in soup.select(self.ROW_SELECTOR):
            if not isinstance(table, Tag):
                continue
            # 「保護年月日」を含むテーブルのみが動物テーブル
            if "保護年月日" not in table.get_text():
                continue
            rows.append(table)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物テーブルを列挙して仮想 URL を返す

        在庫 0 件のページでも `ParsingError` を出さず空リストを返す
        (公示情報が無い時期がある)。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """1 動物テーブルから RawAnimalData を構築する

        ヘッダ行 (「保護年月日 / 保護場所」「種類 / 毛色」等) と値行が
        交互に並ぶ構造のため、ラベル → 値のマッピングをテキストから
        順次組み立てる。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]

        fields = self._extract_label_value_pairs(table)

        location = fields.get("保護場所", "")
        shelter_date = fields.get("保護年月日", "")
        color = fields.get("毛色", "")
        sex = self._normalize_sex(fields.get("性別", ""))
        # 「その他特徴」セルから体格 (「体格：中」等) を抽出 → size に格納
        size = self._extract_size(fields.get("その他特徴", ""))
        # 「問い合わせ先」と電話番号セルの両方から電話番号を探す
        phone_text = fields.get("問い合わせ先", "") + " " + fields.get("電話番号", "")
        phone = self._normalize_phone(phone_text)
        # 動物種別はサイト名から推定 (HTML の「種類」は犬種名のため)
        species = self._infer_species_from_site_name(self.site_config.name)

        # 画像はテーブル内の <img> から取得 (絶対 URL 化)
        image_urls = self._extract_row_images(table, virtual_url)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color=color,
                size=size,
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone=phone,
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _extract_label_value_pairs(table: Tag) -> dict[str, str]:
        """テーブルからラベル→値の辞書を組み立てる

        本サイトはヘッダ行 (青背景, `<b>` 装飾, `_HEADER_LABELS` のいずれか)
        と値行が交互に並ぶ構造。各ヘッダ行の i 番目の列ラベルに対し、
        次の値行の同じ位置にあるセルを値として対応付ける。

        rowspan=9 の画像セル (row 1 の 1 列目) は値・ラベルどちらでもない
        ため除外する。

        最後の電話番号行 (ヘッダ無し) は特別扱いし、`電話番号` キーで格納。
        """
        result: dict[str, str] = {}
        rows = table.find_all("tr")

        # 各 tr の cells を「画像セルを除いたテキストセル列」に正規化
        normalized: list[list[str]] = []
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            texts: list[str] = []
            for c in cells:
                if c.find("img") is not None:
                    # 画像セルは label/value ペアの対象外
                    continue
                texts.append(c.get_text(separator=" ", strip=True))
            normalized.append(texts)

        # ヘッダ行を発見したら、次の非空行を値行として対応付け
        i = 0
        while i < len(normalized):
            cells = normalized[i]
            if any(t in _HEADER_LABELS for t in cells):
                # 値行を探索 (連続する空行はスキップ)
                j = i + 1
                while j < len(normalized) and not any(normalized[j]):
                    j += 1
                if j < len(normalized):
                    values = normalized[j]
                    for col_idx, label in enumerate(cells):
                        if not label or label not in _HEADER_LABELS:
                            continue
                        if col_idx < len(values):
                            result[label] = values[col_idx]
                i = j + 1
            else:
                i += 1

        # 末尾の電話番号行 (ヘッダ「問い合わせ先」の値行の更に下に出る) を救出
        # 数字のみで構成された値が `問い合わせ先` の後ろに残っていれば電話番号扱い
        for cells in reversed(normalized):
            for txt in cells:
                if txt and re.search(r"\d{2,4}-\d{2,4}-\d{3,4}|\b0\d{9,10}\b", txt):
                    result.setdefault("電話番号", txt)
                    break
            if "電話番号" in result:
                break

        return result

    @staticmethod
    def _normalize_sex(text: str) -> str:
        """性別表記を正規化 ("オス"/"メス"/"不明" 等はそのまま返す)"""
        # サイトの表記は基本「オス / メス」(「♂ / ♀」表記は本サイトでは未確認)
        return text.strip()

    @staticmethod
    def _extract_size(text: str) -> str:
        """「その他特徴」セルから「体格：X」の X (大/中/小 等) を抜き出す

        該当箇所がなければ元のテキスト (空文字含む) をそのまま返す。
        """
        if not text:
            return ""
        m = re.search(r"体格\s*[:：]\s*([^\s,、　]+)", text)
        if m:
            return m.group(1)
        return text.strip()

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register(
    "三重県動物愛護管理センター（迷い犬情報）", MieDakcAdapter
)
