"""LlmAdapter の統合テスト（モックLlmProvider使用）"""

import pytest
from unittest.mock import MagicMock, patch

from src.data_collector.llm.adapter import LlmAdapter, CollectionStats, validate_extraction
from src.data_collector.llm.config import SiteConfig
from src.data_collector.llm.providers.base import ExtractionResult, LlmProvider
from src.data_collector.domain.models import RawAnimalData


class MockProvider(LlmProvider):
    """テスト用モックプロバイダー"""

    def __init__(self):
        self.extract_calls = 0
        self.link_calls = 0

    def extract_animal_data(self, html_content, source_url, category):
        self.extract_calls += 1
        return ExtractionResult(
            fields={
                "species": "犬",
                "sex": "オス",
                "age": "約2歳",
                "color": "茶色",
                "size": "中型",
                "shelter_date": "2026-01-15",
                "location": "テスト県テスト市",
                "phone": "088-123-4567",
                "image_urls": ["https://example.com/dog.jpg"],
            },
            input_tokens=1000,
            output_tokens=200,
        )

    def extract_detail_links(self, html_content, base_url):
        self.link_calls += 1
        return [
            "https://example.com/detail/1",
            "https://example.com/detail/2",
        ]


@pytest.fixture
def site_config():
    return SiteConfig(
        name="テストサイト",
        prefecture="テスト県",
        prefecture_code="99",
        list_url="https://example.com/list",
        list_link_pattern="a.detail-link",
        category="adoption",
        request_interval=1.0,
    )


@pytest.fixture
def site_config_no_selector():
    return SiteConfig(
        name="テストサイト（セレクターなし）",
        prefecture="テスト県",
        prefecture_code="99",
        list_url="https://example.com/list",
        category="adoption",
        request_interval=1.0,
    )


@pytest.fixture
def mock_provider():
    return MockProvider()


class TestLlmAdapterInit:
    def test_inherits_municipality_adapter(self, site_config, mock_provider):
        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        assert adapter.prefecture_code == "99"
        assert adapter.municipality_name == "テストサイト"


class TestFetchAnimalList:
    @patch("src.data_collector.llm.adapter.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_with_css_selector(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = """
        <html><body>
        <a class="detail-link" href="/detail/1">Dog 1</a>
        <a class="detail-link" href="/detail/2">Dog 2</a>
        <a href="/about">About</a>
        </body></html>
        """
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        result = adapter.fetch_animal_list()

        assert len(result) == 2
        assert result[0] == ("https://example.com/detail/1", "adoption")
        assert result[1] == ("https://example.com/detail/2", "adoption")
        assert mock_provider.link_calls == 0  # LLMは使わない

    @patch("src.data_collector.llm.adapter.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_without_selector_uses_llm(
        self, mock_sleep, mock_get, site_config_no_selector, mock_provider
    ):
        mock_response = MagicMock()
        mock_response.text = "<html><body><a href='/detail/1'>Dog</a></body></html>"
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(
            site_config=site_config_no_selector, provider=mock_provider
        )
        result = adapter.fetch_animal_list()

        assert len(result) == 2
        assert mock_provider.link_calls == 1

    @patch("src.data_collector.llm.adapter.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_deduplicates_urls(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = """
        <html><body>
        <a class="detail-link" href="/detail/1">Dog 1</a>
        <a class="detail-link" href="/detail/1">Dog 1 again</a>
        </body></html>
        """
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        result = adapter.fetch_animal_list()

        assert len(result) == 1

    @patch("src.data_collector.llm.adapter.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_max_pages_limit(self, mock_sleep, mock_get, mock_provider):
        config = SiteConfig(
            name="テスト",
            prefecture="テスト県",
            prefecture_code="99",
            list_url="https://example.com/list",
            list_link_pattern="a.link",
            max_pages=1,
        )
        mock_response = MagicMock()
        mock_response.text = """<html><body>
        <a class="link" href="/detail/1">Dog</a>
        <a href="/list?page=2">次へ</a>
        </body></html>"""
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=config, provider=mock_provider)
        result = adapter.fetch_animal_list()

        assert mock_get.call_count == 1  # 1ページのみ


class TestExtractAnimalDetails:
    @patch("src.data_collector.llm.adapter.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_extracts_and_returns_raw_data(
        self, mock_sleep, mock_get, site_config, mock_provider
    ):
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Dog info</p></body></html>"
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        result = adapter.extract_animal_details(
            "https://example.com/detail/1", "adoption"
        )

        assert isinstance(result, RawAnimalData)
        assert result.species == "犬"
        assert result.source_url == "https://example.com/detail/1"
        assert result.category == "adoption"
        assert mock_provider.extract_calls == 1

    @patch("src.data_collector.llm.adapter.requests.get")
    @patch("src.data_collector.llm.adapter.time.sleep")
    def test_tracks_stats(self, mock_sleep, mock_get, site_config, mock_provider):
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Dog</p></body></html>"
        mock_response.apparent_encoding = "utf-8"
        mock_get.return_value = mock_response

        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        adapter.extract_animal_details("https://example.com/detail/1", "adoption")

        assert adapter.stats.api_calls == 1
        assert adapter.stats.total_input_tokens == 1000
        assert adapter.stats.total_output_tokens == 200


class TestNormalize:
    def test_delegates_to_data_normalizer(self, site_config, mock_provider):
        adapter = LlmAdapter(site_config=site_config, provider=mock_provider)
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="2歳",
            color="茶色",
            size="中型",
            shelter_date="2026-01-15",
            location="テスト県テスト市",
            phone="0881234567",
            image_urls=[],
            source_url="https://example.com/detail/1",
            category="adoption",
        )
        result = adapter.normalize(raw)
        assert result.species == "犬"
        assert result.sex == "男の子"


class TestCollectionStats:
    def test_initial_values(self):
        stats = CollectionStats()
        assert stats.api_calls == 0
        assert stats.estimated_cost_usd == 0.0

    def test_record_extraction(self):
        stats = CollectionStats()
        result = ExtractionResult(fields={}, input_tokens=1000, output_tokens=500)
        stats.record_extraction(result)
        assert stats.api_calls == 1
        assert stats.total_input_tokens == 1000
        assert stats.total_output_tokens == 500
        assert stats.estimated_cost_usd > 0

    def test_cost_calculation(self):
        stats = CollectionStats()
        stats.total_input_tokens = 1_000_000
        stats.total_output_tokens = 1_000_000
        # Haiku: $0.25/MTok in + $1.25/MTok out = $1.50
        assert abs(stats.estimated_cost_usd - 1.50) < 0.01


class TestValidateExtraction:
    def test_valid_fields(self):
        fields = {"species": "犬", "shelter_date": "2026-01-15"}
        errors = validate_extraction(fields)
        assert errors == []

    def test_missing_species(self):
        fields = {"species": "", "shelter_date": "2026-01-15"}
        errors = validate_extraction(fields)
        assert "species" in errors[0]

    def test_missing_shelter_date(self):
        fields = {"species": "犬", "shelter_date": ""}
        errors = validate_extraction(fields)
        assert "shelter_date" in errors[0]

    def test_missing_both(self):
        fields = {}
        errors = validate_extraction(fields)
        assert len(errors) == 2
