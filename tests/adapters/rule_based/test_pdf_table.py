"""PdfTableAdapter のテスト

PDF からテキストを抽出し、サブクラス定義のパーサで複数動物に分割する基底を検証。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.pdf_table import PdfTableAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="香川県PDFサイト",
        prefecture="香川県",
        prefecture_code="37",
        list_url="https://example.com/list/",
        category="lost",
        pdf_link_pattern="a[href$='.pdf']",
        pdf_multi_animal=True,
    )


LIST_HTML = """
<html><body>
  <a href="/files/animals_2026_05.pdf">PDF1</a>
  <a href="/files/other.pdf">PDF2</a>
</body></html>
"""

# 単純な PDF テキスト（実際のフィクスチャは Phase A3 で用意）
SAMPLE_PDF_TEXT = """\
番号 種別 性別 年齢 場所
1 犬 オス 3歳 高松
2 猫 メス 2歳 高松
"""


class _SamplePdfAdapter(PdfTableAdapter):
    PDF_LINK_SELECTOR = "a[href$='.pdf']"

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """各行をスペース区切りで解析（テスト用最小実装）"""
        records = []
        for line in pdf_text.splitlines()[1:]:  # ヘッダ行スキップ
            parts = line.split()
            if len(parts) >= 5:
                records.append(
                    {
                        "species": parts[1],
                        "sex": parts[2],
                        "age": parts[3],
                        "location": parts[4],
                        "shelter_date": "2026-05-01",
                    }
                )
        return records


class TestPdfTableAdapter:
    def test_fetch_animal_list_extracts_pdf_links(self):
        adapter = _SamplePdfAdapter(_site())
        with (
            patch.object(adapter, "_http_get", return_value=LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"fake-pdf"),
            patch.object(adapter, "_extract_pdf_text", return_value=SAMPLE_PDF_TEXT),
        ):
            result = adapter.fetch_animal_list()
        # 2 PDF × 2 動物 = 4 仮想 URL
        assert len(result) == 4
        for url, _ in result:
            assert ".pdf#row=" in url

    def test_extract_animal_details_returns_raw_data(self):
        adapter = _SamplePdfAdapter(_site())
        with (
            patch.object(adapter, "_http_get", return_value=LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"fake-pdf"),
            patch.object(adapter, "_extract_pdf_text", return_value=SAMPLE_PDF_TEXT),
        ):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(
                "https://example.com/files/animals_2026_05.pdf#row=0",
                category="lost",
            )
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.age == "3歳"
        assert raw.location == "高松"
        assert raw.shelter_date == "2026-05-01"

    def test_raises_when_no_pdf_links(self):
        adapter = _SamplePdfAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
