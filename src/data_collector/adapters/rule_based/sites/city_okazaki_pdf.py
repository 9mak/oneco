"""岡崎市 PDF 系 rule-based adapter

対象ドメイン: https://www.city.okazaki.lg.jp/

岡崎市は保護動物情報を PDF で公開しており、1 つの PDF に複数頭分の
情報が記載される。

実装方針:
- 一覧 HTML から `a[href$='.pdf']` で PDF リンクを抽出
- 各 PDF をダウンロードし pdfplumber でテキスト抽出
- `_parse_pdf_text` で「保護日」「収容日」を区切りに動物 1 頭分を dict 化
"""

from __future__ import annotations

import io
import re
from typing import ClassVar

try:  # pragma: no cover - 実行環境では常に import できる
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore[assignment]

from ....domain.models import RawAnimalData  # noqa: F401  (型参照用)
from ...municipality_adapter import ParsingError  # noqa: F401  (型参照用)
from ..pdf_table import PdfTableAdapter
from ..registry import SiteAdapterRegistry

# ─────────────────── パース用パターン ───────────────────

_SHELTER_DATE_RE = re.compile(
    r"(?:保護日|収容日|発見日)\s*[:：]?\s*"
    r"(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?"
)
_SPECIES_RE = re.compile(r"(?:種類|種別|動物種)\s*[:：]?\s*(犬|猫|その他|[^\s　]+)")
_SEX_RE = re.compile(r"性別\s*[:：]?\s*([^\s　]+)")
_AGE_RE = re.compile(r"年齢\s*[:：]?\s*([^\s　]+)")
_COLOR_RE = re.compile(r"(?:毛色|色)\s*[:：]?\s*([^\s　]+)")
_SIZE_RE = re.compile(r"(?:体格|大きさ|体重)\s*[:：]?\s*([^\s　]+)")
_LOCATION_RE = re.compile(r"(?:保護場所|収容場所|発見場所)\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")
# 表由来の構造化テキストで使う追加ラベル。
# 「種類」列は品種名 (推定ピットブル / 雑種) なので species とは別に持つ。
_BREED_RE = re.compile(r"品種\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")
_MGMT_NUMBER_RE = re.compile(r"管理番号\s*[:：]?\s*([^\s　]+)")
_FEATURE_RE = re.compile(r"特徴\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")

# 見出し行「保護動物情報 犬 2026年4月5日 現在」から species と基準年を取る。
# 表の「保護月日」列は年を持たない (4月3日) ため、年はここからしか得られない。
_HEADING_RE = re.compile(
    r"保護動物情報\s*(犬|猫|その他)?\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
# 「4月3日」形式の月日
_MONTH_DAY_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 表ヘッダ列名 → 構造化テキストのラベル。
# 「種類」は品種なので species ラベル (種別) には割り当てない。
_TABLE_HEADER_TO_LABEL: dict[str, str] = {
    "管理番号": "管理番号",
    "保護場所": "保護場所",
    "収容場所": "保護場所",
    "種類": "品種",
    "品種": "品種",
    "毛色": "毛色",
    "性別": "性別",
    "体格": "体格",
    "年齢": "年齢",
    "その他特徴": "特徴",
    "備考": "特徴",
}


class CityOkazakiPdfAdapter(PdfTableAdapter):
    """岡崎市保護動物 PDF 用 rule-based adapter"""

    PDF_LINK_SELECTOR: ClassVar[str] = "a[href$='.pdf']"

    # ─────────────────── PDF テキスト抽出 (表対応) ───────────────────

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """表として読めれば構造化テキストへ、駄目なら既定のテキスト抽出

        岡崎市の PDF は「1 頭 = 1 行」のきれいな表なので `extract_tables()`
        で読む。`extract_text()` はセル内改行が前後の行へ割れてしまい
        (猫 PDF の「白黒 / （はちわれ）」)、毛色が正しく取れない。
        """
        text = super()._extract_pdf_text(pdf_bytes)
        try:
            tables = self._extract_pdf_tables(pdf_bytes)
        except Exception:
            return text
        if not tables:
            return text
        labeled = self._tables_to_labeled_text(tables, text)
        # 表からデータ行を得られなかった場合は素のテキストにフォールバック
        return labeled or text

    def _extract_pdf_tables(self, pdf_bytes: bytes) -> list[list[list[str]]]:
        """全ページの表を取り出す"""
        if pdfplumber is None:  # pragma: no cover
            return []
        tables: list[list[list[str]]] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    tables.append([[(c or "") for c in row] for row in table])
        return tables

    @staticmethod
    def _tables_to_labeled_text(tables: list[list[list[str]]], page_text: str) -> str:
        """表を「ラベル: 値」形式の構造化テキストへ変換する

        見出し「保護動物情報 犬 2026年4月5日 現在」から species と基準年を取り、
        年を持たない「保護月日 4月3日」に補って保護日を組み立てる。
        月日が基準日より後になる場合は年跨ぎとみなして前年に倒す。
        """
        heading = _HEADING_RE.search(page_text or "")
        species = (heading.group(1) if heading else "") or ""
        base_year = int(heading.group(2)) if heading else 0
        base_month = int(heading.group(3)) if heading else 0
        base_day = int(heading.group(4)) if heading else 0

        blocks: list[str] = []
        for table in tables:
            if len(table) < 2:
                continue
            headers = [str(h).replace("\n", "").strip() for h in table[0]]
            if "管理番号" not in headers:
                continue
            for row in table[1:]:
                lines: list[str] = []
                shelter_date = ""
                has_value = False
                for i, cell in enumerate(row):
                    if i >= len(headers):
                        break
                    value = str(cell).replace("\n", "").strip()
                    if not value:
                        continue
                    header = headers[i]
                    if header in ("保護月日", "収容月日", "保護日", "収容日"):
                        shelter_date = CityOkazakiPdfAdapter._resolve_shelter_date(
                            value, base_year, base_month, base_day
                        )
                        continue
                    label = _TABLE_HEADER_TO_LABEL.get(header)
                    if not label:
                        continue
                    lines.append(f"{label}: {value}")
                    if label != "管理番号":
                        has_value = True
                if not has_value:
                    continue
                # 保護日はブロック先頭に置く (_parse_pdf_text がここで行を切る)
                header_lines = [f"保護日: {shelter_date}"] if shelter_date else []
                if species:
                    header_lines.append(f"種別: {species}")
                blocks.append("\n".join(header_lines + lines))

        return "\n\n".join(blocks)

    @staticmethod
    def _resolve_shelter_date(value: str, base_year: int, base_month: int, base_day: int) -> str:
        """「4月3日」に見出しの年を補って ISO 形式にする

        年を持つ表記 (2026年4月3日) がそのまま入っている場合はそれを使う。
        """
        full = _SHELTER_DATE_RE.search(f"保護日 {value}")
        if full:
            y, mo, d = (int(g) for g in full.groups())
            return f"{y:04d}-{mo:02d}-{d:02d}"

        md = _MONTH_DAY_RE.search(value)
        if not md or not base_year:
            return ""
        mo, d = int(md.group(1)), int(md.group(2))
        year = base_year
        # 掲載基準日より後の月日は前年の保護分とみなす (年跨ぎ)
        if (mo, d) > (base_month, base_day):
            year -= 1
        return f"{year:04d}-{mo:02d}-{d:02d}"

    # ─────────────────── _parse_pdf_text 実装 ───────────────────

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """PDF テキストから動物 dict のリストを抽出する"""
        if not pdf_text:
            return []

        records: list[dict] = []
        current: dict | None = None

        lines = [ln.strip() for ln in pdf_text.splitlines() if ln.strip()]

        for line in lines:
            shelter_match = _SHELTER_DATE_RE.search(line)
            if shelter_match:
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
                    "breed": "",
                    "management_number": "",
                    "description": "",
                }

            if current is None:
                continue

            self._extract_field(line, current)

        if current is not None and self._is_record_valid(current):
            records.append(current)

        return records

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _extract_field(line: str, record: dict) -> None:
        for key, pattern in (
            ("species", _SPECIES_RE),
            ("breed", _BREED_RE),
            ("management_number", _MGMT_NUMBER_RE),
            ("sex", _SEX_RE),
            ("age", _AGE_RE),
            ("color", _COLOR_RE),
            ("size", _SIZE_RE),
            ("location", _LOCATION_RE),
            ("description", _FEATURE_RE),
        ):
            if record.get(key):
                continue
            m = pattern.search(line)
            if m:
                record[key] = m.group(1).strip()

    @staticmethod
    def _is_record_valid(record: dict) -> bool:
        """収容日 + 他 1 つ以上のフィールドが埋まっていれば有効

        有効と判定した時点で species の既定値を埋める。species は致命 8
        フィールドの 1 つで、空のまま通すと下流で「欠損」として扱われる。
        判別不能時は "その他" に寄せる (愛媛/名古屋 adapter と同じ扱い)。
        """
        if not record.get("shelter_date"):
            return False
        valid = any(record.get(k) for k in ("species", "sex", "age", "color", "size", "location"))
        if valid and not record.get("species"):
            record["species"] = "その他"
        return valid


# ─────────────────── サイト登録 ───────────────────

SiteAdapterRegistry.register("岡崎市（保護動物）", CityOkazakiPdfAdapter)
