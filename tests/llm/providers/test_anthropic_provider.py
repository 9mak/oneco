"""AnthropicProvider のユニットテスト（モック使用）"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.data_collector.llm.providers.anthropic_provider import (
    ANIMAL_EXTRACTION_TOOL,
    LINK_EXTRACTION_TOOL,
    AnthropicProvider,
)
from src.data_collector.llm.providers.base import ExtractionResult


def _make_tool_use_response(tool_input: dict, input_tokens=100, output_tokens=50):
    """モックレスポンスを作成"""
    block = SimpleNamespace(type="tool_use", input=tool_input)
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(content=[block], usage=usage)


class TestExtractAnimalData:
    @patch("src.data_collector.llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_extracts_fields_from_tool_use_response(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        expected_fields = {
            "species": "犬",
            "sex": "オス",
            "age": "約2歳",
            "color": "茶色",
            "size": "中型",
            "shelter_date": "2026-01-15",
            "location": "徳島県動物愛護管理センター",
            "phone": "088-123-4567",
            "image_urls": ["https://example.com/dog.jpg"],
        }
        mock_client.messages.create.return_value = _make_tool_use_response(
            expected_fields, input_tokens=500, output_tokens=200
        )

        provider = AnthropicProvider(api_key="test-key")
        result = provider.extract_animal_data(
            html_content="<p>Dog info</p>",
            source_url="https://example.com/detail/1",
            category="adoption",
        )

        assert isinstance(result, ExtractionResult)
        assert result.fields == expected_fields
        assert result.input_tokens == 500
        assert result.output_tokens == 200

        # API呼び出し引数を検証
        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
        assert call_kwargs["tools"] == [ANIMAL_EXTRACTION_TOOL]
        assert call_kwargs["tool_choice"] == {
            "type": "tool",
            "name": "extract_animal_data",
        }

    @patch("src.data_collector.llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_uses_custom_model(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_tool_use_response({})

        provider = AnthropicProvider(model="claude-sonnet-4-20250514", api_key="test-key")
        provider.extract_animal_data("<p>test</p>", "https://example.com", "adoption")

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"


class TestExtractDetailLinks:
    @patch("src.data_collector.llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_extracts_links(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        expected_links = [
            "https://example.com/detail/1",
            "https://example.com/detail/2",
        ]
        mock_client.messages.create.return_value = _make_tool_use_response(
            {"links": expected_links}
        )

        provider = AnthropicProvider(api_key="test-key")
        links = provider.extract_detail_links(
            html_content="<a href='detail/1'>Dog</a>",
            base_url="https://example.com/",
        )

        assert links == expected_links

        call_kwargs = mock_client.messages.create.call_args[1]
        assert call_kwargs["tools"] == [LINK_EXTRACTION_TOOL]
        assert call_kwargs["tool_choice"] == {
            "type": "tool",
            "name": "extract_detail_links",
        }

    @patch("src.data_collector.llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_returns_empty_list_on_no_tool_use(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # レスポンスにtool_useブロックがない場合
        text_block = SimpleNamespace(type="text", text="No links found")
        usage = SimpleNamespace(input_tokens=100, output_tokens=50)
        mock_client.messages.create.return_value = SimpleNamespace(
            content=[text_block], usage=usage
        )

        provider = AnthropicProvider(api_key="test-key")
        links = provider.extract_detail_links("<p>empty</p>", "https://example.com/")
        assert links == []


class TestRetryLogic:
    @patch("src.data_collector.llm.providers.anthropic_provider.time.sleep")
    @patch("src.data_collector.llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_retries_on_rate_limit(self, mock_anthropic_cls, mock_sleep):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        # 2回失敗、3回目に成功
        type("RateLimitError", (Exception,), {})

        # anthropic.RateLimitError をモック
        import src.data_collector.llm.providers.anthropic_provider as mod

        original_rate_limit = mod.anthropic.RateLimitError

        mock_client.messages.create.side_effect = [
            original_rate_limit("rate limited", response=MagicMock(), body=None),
            original_rate_limit("rate limited", response=MagicMock(), body=None),
            _make_tool_use_response({"species": "犬"}),
        ]

        provider = AnthropicProvider(api_key="test-key", max_retries=3)
        result = provider.extract_animal_data("<p>test</p>", "https://example.com", "adoption")

        assert result.fields == {"species": "犬"}
        assert mock_client.messages.create.call_count == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2^0
        mock_sleep.assert_any_call(2)  # 2^1

    @patch("src.data_collector.llm.providers.anthropic_provider.time.sleep")
    @patch("src.data_collector.llm.providers.anthropic_provider.anthropic.Anthropic")
    def test_raises_after_max_retries(self, mock_anthropic_cls, mock_sleep):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        import src.data_collector.llm.providers.anthropic_provider as mod

        error = mod.anthropic.RateLimitError("rate limited", response=MagicMock(), body=None)
        mock_client.messages.create.side_effect = error

        provider = AnthropicProvider(api_key="test-key", max_retries=3)

        with pytest.raises(type(error)):
            provider.extract_animal_data("<p>test</p>", "https://example.com", "adoption")

        assert mock_client.messages.create.call_count == 3
