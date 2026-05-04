"""GroqProvider のユニットテスト（モック使用）"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.data_collector.llm.providers.base import ExtractionResult, MultiExtractionResult
from src.data_collector.llm.providers.groq_provider import GroqProvider


def _make_chat_response(tool_args: dict, prompt_tokens=100, completion_tokens=50):
    """Groq/OpenAI 互換のモックレスポンスを作成"""
    tool_call = SimpleNamespace(function=SimpleNamespace(arguments=json.dumps(tool_args)))
    message = SimpleNamespace(tool_calls=[tool_call])
    choice = SimpleNamespace(message=message)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage)


ANIMAL_FIELDS = {
    "species": "犬",
    "sex": "オス",
    "age": "約2歳",
    "color": "茶色",
    "size": "中型",
    "shelter_date": "2026-01-15",
    "location": "高知県動物愛護センター",
    "phone": "088-123-4567",
    "image_urls": ["https://example.com/dog.jpg"],
}


class TestExtractAnimalData:
    def test_returns_extraction_result(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_chat_response(
            ANIMAL_FIELDS, prompt_tokens=500, completion_tokens=200
        )
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        result = provider.extract_animal_data(
            html_content="<p>Dog info</p>",
            source_url="https://example.com/detail/1",
            category="adoption",
        )

        assert isinstance(result, ExtractionResult)
        assert result.fields["species"] == "犬"
        assert result.fields["shelter_date"] == "2026-01-15"
        assert result.input_tokens == 500
        assert result.output_tokens == 200

    def test_passes_correct_tool_name(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_chat_response(ANIMAL_FIELDS)
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["tool_choice"]["function"]["name"] == "extract_animal_data"


class TestExtractDetailLinks:
    def test_returns_links(self):
        mock_client = MagicMock()
        links = ["https://example.com/1", "https://example.com/2"]
        mock_client.chat.completions.create.return_value = _make_chat_response({"links": links})
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        result = provider.extract_detail_links("<ul><li>...</li></ul>", "https://example.com")

        assert result == links

    def test_returns_empty_list_when_no_tool_call(self):
        mock_client = MagicMock()
        no_tool_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=None))],
            usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )
        mock_client.chat.completions.create.return_value = no_tool_response
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        result = provider.extract_detail_links("<p>html</p>", "https://example.com")

        assert result == []


class TestExtractMultipleAnimals:
    def test_returns_multi_extraction_result(self):
        mock_client = MagicMock()
        animals = [ANIMAL_FIELDS, {**ANIMAL_FIELDS, "sex": "メス"}]
        mock_client.chat.completions.create.return_value = _make_chat_response(
            {"animals": animals}, prompt_tokens=800, completion_tokens=300
        )
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        result = provider.extract_multiple_animals(
            content="PDF text...",
            source_url="https://example.com/list.pdf",
            category="adoption",
        )

        assert isinstance(result, MultiExtractionResult)
        assert len(result.animals) == 2
        assert result.input_tokens == 800


class TestRetryOnQuotaError:
    @patch("src.data_collector.llm.providers.groq_provider.time.sleep")
    def test_retries_on_429_error(self, mock_sleep):
        mock_client = MagicMock()
        quota_error = Exception("rate limit exceeded 429")
        mock_client.chat.completions.create.side_effect = [
            quota_error,
            _make_chat_response(ANIMAL_FIELDS),
        ]
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        result = provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        assert result.fields["species"] == "犬"
        assert mock_client.chat.completions.create.call_count == 2
        mock_sleep.assert_called_once()

    @patch("src.data_collector.llm.providers.groq_provider.time.sleep")
    def test_raises_immediately_on_non_quota_error(self, mock_sleep):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = ValueError("invalid request")
        provider = GroqProvider(api_key="test-key")
        provider._client = mock_client

        with pytest.raises(ValueError, match="invalid request"):
            provider.extract_animal_data("<p>html</p>", "https://example.com", "adoption")

        mock_sleep.assert_not_called()
