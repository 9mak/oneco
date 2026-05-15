"""札幌市迷子動物 (city.sapporo.jp) rule-based adapter

single_page 形式。在庫があるときは「収容年月日：」「保護場所：」「種類：」等の
ラベル形式で動物情報が並ぶ。在庫 0 件時はテンプレート構造のみ。

カバーサイト (2):
- 札幌市（迷子犬）
- 札幌市（迷子猫）
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

_LABEL_VALUE_RE = re.compile(r"([^：:\n]{2,8})\s*[：:]\s*([^：:\n]*)")

# 日付らしいパターン (YYYY-MM-DD / YYYY/MM/DD / 令和〇年〇月〇日 など)
_DATE_LIKE_RE = re.compile(
    r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|令和\s*\d+\s*年|平成\s*\d+\s*年|\d{1,2}月\d{1,2}日"
)


class CitySapporoAdapter(SinglePageTableAdapter):
    """札幌市迷子動物 adapter"""

    ROW_SELECTOR = "table tr"
    SHELTER_DATE_DEFAULT = ""

    def _try_decode(self, html: str) -> str:
        """二重 UTF-8 mojibake を補正"""
        if "札幌" not in html and "犬" not in html:
            try:
                return html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return html

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        try:
            html = self._http_get(self.site_config.list_url)
        except Exception:
            return []
        html = self._try_decode(html)
        records = self._parse_records(html)
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(records))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        list_url = virtual_url.split("#row=")[0]
        idx = int(virtual_url.split("#row=")[1])
        try:
            html = self._http_get(list_url)
        except Exception as e:
            raise ParsingError(f"fetch 失敗: {e}", url=virtual_url) from e
        html = self._try_decode(html)
        records = self._parse_records(html)
        if idx >= len(records):
            raise ParsingError(
                f"row index {idx} out of range (total {len(records)})",
                url=virtual_url,
            )
        record = records[idx]
        species = record.get("種類", "")
        if not species:
            species = "犬" if "犬" in self.site_config.name else (
                "猫" if "猫" in self.site_config.name else ""
            )
        return RawAnimalData(
            species=species,
            sex=record.get("性別", ""),
            age=record.get("年齢", ""),
            color=record.get("毛色", ""),
            size=record.get("体格", ""),
            shelter_date=record.get("収容年月日", "") or record.get("収容日", ""),
            location=record.get("保護場所", "") or record.get("収容場所", ""),
            phone="",
            image_urls=[],
            source_url=virtual_url,
            category=category,
        )

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────── helpers ───────

    def _parse_records(self, html: str) -> list[dict[str, str]]:
        """各動物 record (label→value dict) を抽出"""
        soup = BeautifulSoup(html, "html.parser")
        records: list[dict[str, str]] = []

        # 戦略 1: 各 table 行の中に「ラベル：値\nラベル：値\n...」が連結されている
        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                for cell in cells:
                    text = cell.get_text(separator="\n", strip=True)
                    if not text or "：" not in text and ":" not in text:
                        continue
                    record: dict[str, str] = {}
                    for line in text.split("\n"):
                        m = _LABEL_VALUE_RE.match(line.strip())
                        if m:
                            label = m.group(1).strip()
                            value = m.group(2).strip()
                            if value:
                                record[label] = value
                    if record:
                        date_val = record.get("収容年月日", "") or record.get("収容日", "")
                        if date_val and _DATE_LIKE_RE.search(date_val):
                            records.append(record)

        # 戦略 2: 全文走査 (table が空の場合)
        if not records:
            body_text = soup.get_text(separator="\n", strip=True)
            current: dict[str, str] = {}

            def _flush(rec: dict[str, str]) -> None:
                date_val = rec.get("収容年月日", "") or rec.get("収容日", "")
                if date_val and _DATE_LIKE_RE.search(date_val):
                    records.append(rec)

            for line in body_text.split("\n"):
                m = _LABEL_VALUE_RE.match(line.strip())
                if not m:
                    continue
                label = m.group(1).strip()
                value = m.group(2).strip()
                if not value:
                    continue
                if label in ("収容年月日", "収容日") and current:
                    _flush(current)
                    current = {}
                current[label] = value
            if current:
                _flush(current)

        return records


SiteAdapterRegistry.register("札幌市（迷子犬）", CitySapporoAdapter)
SiteAdapterRegistry.register("札幌市（迷子猫）", CitySapporoAdapter)
