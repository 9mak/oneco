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

    def test_returns_empty_when_no_pdf_links(self):
        # PDF_LINK_SELECTOR にヒットしない場合は「現在公開中の収容情報 PDF がない」
        # 真ゼロとして空リストを返し、ParsingError を投げない。
        adapter = _SamplePdfAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_identity_fields_passthrough_via_records(self):
        """サブクラスの records に個体識別キーがあれば RawAnimalData に転写される

        kochi 同型のサイレントドロップ予防の回帰防止テスト。
        基底経路が breed/description/name/management_number の4キーを
        構築子に渡していることを直接検証する。
        """

        class _IdentityPdfAdapter(PdfTableAdapter):
            PDF_LINK_SELECTOR = "a[href$='.pdf']"

            def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
                # 派生は records に該当キーを生成すれば開通する
                return [
                    {
                        "species": "犬",
                        "name": "ポチ",
                        "breed": "柴犬",
                        "management_number": "2026-001",
                        "description": "人懐っこい",
                        "shelter_date": "2026-05-01",
                    }
                ]

        adapter = _IdentityPdfAdapter(_site())
        with (
            patch.object(adapter, "_http_get", return_value=LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"fake-pdf"),
            patch.object(adapter, "_extract_pdf_text", return_value="dummy"),
        ):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(
                "https://example.com/files/animals_2026_05.pdf#row=0",
                category="lost",
            )
        assert raw.name == "ポチ"
        assert raw.breed == "柴犬"
        assert raw.management_number == "2026-001"
        assert raw.description == "人懐っこい"


class TestPdfTableAdapterDownloadSizeLimit:
    """`_download_pdf` のサイズ上限ガード (OOM / DoS 防止)"""

    def _mock_response(self, content_bytes: bytes, content_length: str | None = None):
        """`requests.get(..., stream=True)` の戻り値を模した context manager"""
        from unittest.mock import MagicMock

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.headers = {}
        if content_length is not None:
            response.headers["Content-Length"] = content_length

        def iter_content(chunk_size: int = 64 * 1024):
            i = 0
            while i < len(content_bytes):
                yield content_bytes[i : i + chunk_size]
                i += chunk_size

        response.iter_content = iter_content
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response

    def test_small_pdf_downloads_normally(self):
        """上限以下の PDF は通常通り bytes が返る"""
        from unittest.mock import patch

        adapter = _SamplePdfAdapter(_site())
        small_pdf = b"PDF-1.4 small content"

        with patch(
            "data_collector.adapters.rule_based.pdf_table.requests.get",
            return_value=self._mock_response(small_pdf, content_length=str(len(small_pdf))),
        ):
            result = adapter._download_pdf("https://example.com/small.pdf")
        assert result == small_pdf

    def test_content_length_over_limit_rejected_early(self):
        """Content-Length が上限超なら本体ダウンロード前に NetworkError"""
        from unittest.mock import patch

        from data_collector.adapters.municipality_adapter import NetworkError

        adapter = _SamplePdfAdapter(_site())
        adapter.PDF_MAX_BYTES = 1000  # テスト用に小さく
        huge_declared = str(adapter.PDF_MAX_BYTES + 1)

        with patch(
            "data_collector.adapters.rule_based.pdf_table.requests.get",
            return_value=self._mock_response(b"", content_length=huge_declared),
        ):
            with pytest.raises(NetworkError, match="上限"):
                adapter._download_pdf("https://example.com/huge.pdf")

    def test_streaming_size_exceeded_raises(self):
        """Content-Length 未宣言でもストリーム読み込み中に上限超で NetworkError"""
        from unittest.mock import patch

        from data_collector.adapters.municipality_adapter import NetworkError

        adapter = _SamplePdfAdapter(_site())
        adapter.PDF_MAX_BYTES = 1000  # テスト用に小さく
        oversize_pdf = b"x" * (adapter.PDF_MAX_BYTES + 100)

        with patch(
            "data_collector.adapters.rule_based.pdf_table.requests.get",
            return_value=self._mock_response(oversize_pdf, content_length=None),
        ):
            with pytest.raises(NetworkError, match="上限"):
                adapter._download_pdf("https://example.com/no-clength.pdf")
