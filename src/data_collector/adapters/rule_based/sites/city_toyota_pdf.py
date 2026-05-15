"""豊田市動物愛護センター PDF 系 rule-based adapter

対象ドメイン: https://www.city.toyota.aichi.jp/

豊田市は迷子動物情報を PDF で公開しており、1 つの PDF に複数頭分の
情報が表形式または箇条書きで掲載される。

実装方針:
- 一覧 HTML から `a[href$='.pdf']` で PDF リンクを抽出
- 各 PDF をダウンロードし pdfplumber でテキスト抽出
- `_parse_pdf_text` で「収容日」を区切りに動物 1 頭分を dict 化
"""

from __future__ import annotations

import re
from typing import ClassVar

from ....domain.models import RawAnimalData  # noqa: F401  (型参照用)
from ...municipality_adapter import ParsingError  # noqa: F401  (型参照用)
from ..pdf_table import PdfTableAdapter
from ..registry import SiteAdapterRegistry

# ─────────────────── パース用パターン ───────────────────

_SHELTER_DATE_RE = re.compile(
    r"(?:収容日|保護日|発見日)\s*[:：]?\s*"
    r"(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?"
)
_SPECIES_RE = re.compile(r"(?:種類|種別|動物種)\s*[:：]?\s*(犬|猫|その他|[^\s　]+)")
_SEX_RE = re.compile(r"性別\s*[:：]?\s*([^\s　]+)")
_AGE_RE = re.compile(r"年齢\s*[:：]?\s*([^\s　]+)")
_COLOR_RE = re.compile(r"(?:毛色|色)\s*[:：]?\s*([^\s　]+)")
_SIZE_RE = re.compile(r"(?:体格|大きさ|体重)\s*[:：]?\s*([^\s　]+)")
_LOCATION_RE = re.compile(r"(?:収容場所|発見場所|保護場所)\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")


class CityToyotaPdfAdapter(PdfTableAdapter):
    """豊田市動物愛護センター PDF 用 rule-based adapter"""

    PDF_LINK_SELECTOR: ClassVar[str] = "a[href$='.pdf']"

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
        if not record.get("shelter_date"):
            return False
        return any(record.get(k) for k in ("species", "sex", "age", "color", "size", "location"))


# ─────────────────── サイト登録 ───────────────────

SiteAdapterRegistry.register("豊田市動物愛護センター（迷子動物）", CityToyotaPdfAdapter)
