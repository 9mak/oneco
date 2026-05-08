"""FallbackProvider のユニットテスト"""

from unittest.mock import MagicMock

import pytest

from src.data_collector.llm.providers.base import ExtractionResult, MultiExtractionResult
from src.data_collector.llm.providers.fallback_provider import FallbackProvider


def _mock_provider(extract_result=None, links_result=None, multi_result=None):
    provider = MagicMock()
    provider.extract_animal_data.return_value = extract_result or ExtractionResult(
        fields={"species": "犬"}, input_tokens=100, output_tokens=50
    )
    provider.extract_detail_links.return_value = links_result or ["https://example.com/1"]
    provider.extract_multiple_animals.return_value = multi_result or MultiExtractionResult(
        animals=[{"species": "犬"}], input_tokens=100, output_tokens=50
    )
    return provider


class TestFallbackOnQuotaError:
    def test_falls_back_extract_animal_data_on_quota_error(self):
        primary = MagicMock()
        primary.extract_animal_data.side_effect = Exception("RESOURCE_EXHAUSTED quota exceeded")
        fallback = _mock_provider(
            ExtractionResult(fields={"species": "猫"}, input_tokens=50, output_tokens=20)
        )

        provider = FallbackProvider(primary=primary, fallback=fallback)
        result = provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        assert result.fields["species"] == "猫"
        fallback.extract_animal_data.assert_called_once()

    def test_falls_back_extract_detail_links_on_rate_limit(self):
        primary = MagicMock()
        primary.extract_detail_links.side_effect = Exception("429 rate limit")
        fallback = _mock_provider(links_result=["https://example.com/fallback"])

        provider = FallbackProvider(primary=primary, fallback=fallback)
        result = provider.extract_detail_links("<p>html</p>", "https://example.com")

        assert result == ["https://example.com/fallback"]

    def test_falls_back_extract_multiple_animals_on_quota_error(self):
        primary = MagicMock()
        primary.extract_multiple_animals.side_effect = Exception("quota exceeded")
        fallback_result = MultiExtractionResult(
            animals=[{"species": "犬"}, {"species": "猫"}],
            input_tokens=200,
            output_tokens=100,
        )
        fallback = _mock_provider(multi_result=fallback_result)

        provider = FallbackProvider(primary=primary, fallback=fallback)
        result = provider.extract_multiple_animals(
            "PDF text", "https://example.com/list.pdf", "adoption"
        )

        assert len(result.animals) == 2


class TestFallbackOnGroqToolUseFailed:
    def test_falls_back_on_tool_use_failed(self):
        """Groq の tool_use_failed エラーでフォールバックする"""
        primary = MagicMock()
        primary.extract_animal_data.side_effect = Exception(
            "Error code: 400 - {'error': {'code': 'tool_use_failed'}}"
        )
        fallback = _mock_provider(
            ExtractionResult(fields={"species": "猫"}, input_tokens=50, output_tokens=20)
        )

        provider = FallbackProvider(primary=primary, fallback=fallback)
        result = provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        assert result.fields["species"] == "猫"
        fallback.extract_animal_data.assert_called_once()

    def test_falls_back_on_500_error(self):
        primary = MagicMock()
        primary.extract_animal_data.side_effect = Exception("500 internal server error")
        fallback = _mock_provider(
            ExtractionResult(fields={"species": "猫"}, input_tokens=50, output_tokens=20)
        )

        provider = FallbackProvider(primary=primary, fallback=fallback)
        result = provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        assert result.fields["species"] == "猫"


class TestNoPrimaryWhenSuccess:
    def test_uses_primary_when_no_error(self):
        primary = _mock_provider(
            ExtractionResult(fields={"species": "犬"}, input_tokens=100, output_tokens=50)
        )
        fallback = _mock_provider()

        provider = FallbackProvider(primary=primary, fallback=fallback)
        result = provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        assert result.fields["species"] == "犬"
        fallback.extract_animal_data.assert_not_called()


class TestNoFallbackOnNonQuotaError:
    def test_raises_non_quota_error_without_fallback(self):
        primary = MagicMock()
        primary.extract_animal_data.side_effect = ValueError("parsing error")
        fallback = _mock_provider()

        provider = FallbackProvider(primary=primary, fallback=fallback)

        with pytest.raises(ValueError, match="parsing error"):
            provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        fallback.extract_animal_data.assert_not_called()
