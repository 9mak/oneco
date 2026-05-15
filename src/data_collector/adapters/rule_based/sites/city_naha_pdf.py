"""那覇市保護犬猫情報 PDF 系 rule-based adapter

対象ドメイン: https://www.city.naha.okinawa.jp/

那覇市は保護犬猫情報を PDF ファイルで公開しており、
1 PDF に複数頭の収容動物が表または箇条書き形式で記載されている。

実装方針:
- 一覧 HTML から `a[href$='.pdf']` セレクタで PDF リンクを抽出
- 各 PDF を `_download_pdf` でダウンロードし pdfplumber でテキスト抽出
- `_parse_pdf_text` でテキストを行ごとに走査し、動物 1 頭分の情報が
  揃ったブロックを dict として収集する
"""

from __future__ import annotations

import re
from typing import ClassVar

from ....domain.models import RawAnimalData  # noqa: F401  (型参照用)
from ...municipality_adapter import ParsingError  # noqa: F401  (例外参照用)
from ..pdf_table import PdfTableAdapter
from ..registry import SiteAdapterRegistry


# ─────────────────── パース用パターン ───────────────────

# 「収容日: 2026年5月12日」「収容日 2026/5/12」など
_SHELTER_DATE_RE = re.compile(
    r"収容日\s*[:：]?\s*"
    r"(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?"
)
# 「種類: 犬」「種別 猫」など
_SPECIES_RE = re.compile(r"(?:種類|種別)\s*[:：]?\s*(犬|猫|その他|[^\s]+)")
# 「性別: オス」
_SEX_RE = re.compile(r"性別\s*[:：]?\s*([^\s　]+)")
# 「年齢: 推定3歳」「年齢 成犬」など
_AGE_RE = re.compile(r"年齢\s*[:：]?\s*([^\s　]+)")
# 「毛色: 白黒」
_COLOR_RE = re.compile(r"毛色\s*[:：]?\s*([^\s　]+)")
# 「体格: 中」「大きさ: 中型」
_SIZE_RE = re.compile(r"(?:体格|大きさ)\s*[:：]?\s*([^\s　]+)")
# 「収容場所: 那覇市〇〇」
_LOCATION_RE = re.compile(r"収容場所\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")


class CityNahaPdfAdapter(PdfTableAdapter):
    """那覇市（保護犬猫情報）PDF 用 rule-based adapter"""

    # 一覧ページから PDF リンクを抽出するセレクタ
    PDF_LINK_SELECTOR: ClassVar[str] = "a[href$='.pdf']"

    # ─────────────────── _parse_pdf_text 実装 ───────────────────

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """PDF テキストから動物 dict のリストを抽出する

        ・収容日が現れた行を新しい動物ブロックの開始とみなす
        ・以降の行から ラベル付きフィールド (種類/性別/年齢/毛色/体格/収容場所)
          を正規表現で取り出す
        ・次の収容日が現れた時点で前のブロックを確定して dict 化する
        """
        if not pdf_text:
            return []

        records: list[dict] = []
        current: dict | None = None

        # PDF の連続改行を整理して 1 行ずつ処理
        lines = [ln.strip() for ln in pdf_text.splitlines() if ln.strip()]

        for line in lines:
            shelter_match = _SHELTER_DATE_RE.search(line)
            if shelter_match:
                # 新しい動物ブロックの開始 → 直前ブロックを確定
                if current is not None and self._is_record_valid(current):
                    records.append(current)
                y, mo, d = (
                    shelter_match.group(1),
                    shelter_match.group(2),
                    shelter_match.group(3),
                )
                current = {
                    "species": "",
                    "sex": "",
                    "age": "",
                    "color": "",
                    "size": "",
                    "shelter_date": f"{int(y):04d}-{int(mo):02d}-{int(d):02d}",
                    "location": "",
                }
                # 同一行に他フィールドがある場合のため後続マッチへフォールスルー

            if current is None:
                # 収容日より前の見出し行などはスキップ
                continue

            self._extract_field(line, current)

        # ループ後に残った最後のブロックを確定
        if current is not None and self._is_record_valid(current):
            records.append(current)

        return records

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _extract_field(line: str, record: dict) -> None:
        """1 行から各属性を抽出し record を埋める (空欄のみ上書き)"""
        for key, pattern in (
            ("species", _SPECIES_RE),
            ("sex", _SEX_RE),
            ("age", _AGE_RE),
            ("color", _COLOR_RE),
            ("size", _SIZE_RE),
            ("location", _LOCATION_RE),
        ):
            if record.get(key):
                continue
            m = pattern.search(line)
            if m:
                record[key] = m.group(1).strip()

    @staticmethod
    def _is_record_valid(record: dict) -> bool:
        """少なくとも収容日と他 1 つ以上のフィールドが埋まっていれば有効"""
        if not record.get("shelter_date"):
            return False
        return any(
            record.get(k)
            for k in ("species", "sex", "age", "color", "size", "location")
        )


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("那覇市（保護犬猫情報）", CityNahaPdfAdapter)
