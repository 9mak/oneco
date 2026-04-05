"""NotificationManagerClient のテスト"""

from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import HttpUrl

from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.notification_manager_client import (
    NotificationManagerClient,
    NotificationManagerConfig,
)


class TestNotificationManagerConfig:
    """NotificationManagerConfig のテスト"""

    def test_config_with_all_values(self):
        """全ての値を指定した場合の設定"""
        config = NotificationManagerConfig(
            url="https://notification.example.com",
            api_key="test-api-key",
            timeout=30.0,
            enabled=True,
        )
        assert config.url == "https://notification.example.com"
        assert config.api_key == "test-api-key"
        assert config.timeout == 30.0
        assert config.enabled is True

    def test_config_with_defaults(self):
        """デフォルト値のテスト"""
        config = NotificationManagerConfig(
            url="https://notification.example.com",
            api_key="test-api-key",
        )
        assert config.timeout == 10.0
        assert config.enabled is True

    def test_config_disabled(self):
        """無効化された設定"""
        config = NotificationManagerConfig(
            url="",
            api_key="",
            enabled=False,
        )
        assert config.enabled is False


class TestNotificationManagerClient:
    """NotificationManagerClient のテスト"""

    @pytest.fixture
    def sample_animals(self) -> list[AnimalData]:
        """テスト用動物データ"""
        return [
            AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                color="茶色",
                size="中型",
                shelter_date=date(2026, 1, 15),
                location="高知県動物愛護センター",
                phone="088-123-4567",
                image_urls=[],
                source_url=HttpUrl("https://example.com/animals/1"),
                category="adoption",
            ),
            AnimalData(
                species="猫",
                sex="女の子",
                age_months=12,
                color="白黒",
                size="小型",
                shelter_date=date(2026, 1, 16),
                location="高知県動物愛護センター",
                phone="088-123-4567",
                image_urls=[],
                source_url=HttpUrl("https://example.com/animals/2"),
                category="adoption",
            ),
        ]

    @pytest.fixture
    def config(self) -> NotificationManagerConfig:
        """テスト用設定"""
        return NotificationManagerConfig(
            url="https://notification.example.com",
            api_key="test-api-key",
            timeout=10.0,
            enabled=True,
        )

    @pytest.fixture
    def disabled_config(self) -> NotificationManagerConfig:
        """無効化された設定"""
        return NotificationManagerConfig(
            url="",
            api_key="",
            enabled=False,
        )

    def test_client_creation(self, config):
        """クライアント作成"""
        client = NotificationManagerClient(config)
        assert client.config == config

    @pytest.mark.asyncio
    async def test_notify_new_animals_success(self, config, sample_animals):
        """正常な新着動物通知"""
        client = NotificationManagerClient(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 202
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await client.notify_new_animals(sample_animals)

            assert result is True
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "/api/v1/notifications/webhook" in call_args[0][0]
            assert call_args[1]["headers"]["X-API-Key"] == "test-api-key"

    @pytest.mark.asyncio
    async def test_notify_new_animals_empty_list(self, config):
        """空リストの場合は送信しない"""
        client = NotificationManagerClient(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await client.notify_new_animals([])

            assert result is True
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_new_animals_disabled(self, disabled_config, sample_animals):
        """無効化時は送信しない"""
        client = NotificationManagerClient(disabled_config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await client.notify_new_animals(sample_animals)

            assert result is True
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_notify_new_animals_http_error(self, config, sample_animals):
        """HTTPエラー時の処理（best-effort）"""
        client = NotificationManagerClient(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.raise_for_status = Mock(side_effect=Exception("Internal Server Error"))
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # best-effort: エラー時も False を返すが例外はスローしない
            result = await client.notify_new_animals(sample_animals)

            assert result is False

    @pytest.mark.asyncio
    async def test_notify_new_animals_connection_error(self, config, sample_animals):
        """接続エラー時の処理（best-effort）"""
        client = NotificationManagerClient(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # best-effort: エラー時も False を返すが例外はスローしない
            result = await client.notify_new_animals(sample_animals)

            assert result is False

    @pytest.mark.asyncio
    async def test_request_payload_format(self, config, sample_animals):
        """リクエストペイロードのフォーマット検証"""
        client = NotificationManagerClient(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 202
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            await client.notify_new_animals(sample_animals)

            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            assert "animals" in payload
            assert "source" in payload
            assert "timestamp" in payload
            assert payload["source"] == "data-collector"
            assert len(payload["animals"]) == 2

    def test_sync_notify_new_animals(self, config, sample_animals):
        """同期メソッドのテスト"""
        client = NotificationManagerClient(config)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 202
            mock_response.raise_for_status = Mock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # 同期メソッドを呼び出し
            result = client.notify_new_animals_sync(sample_animals)

            assert result is True
