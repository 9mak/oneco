"""NotificationClient のユニットテスト"""

from unittest.mock import patch

import pytest

from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.notification_client import (
    NotificationClient,
    NotificationLevel,
)


class TestNotificationClient:
    """NotificationClient のテストケース"""

    @pytest.fixture
    def notification_config(self):
        """テスト用通知設定"""
        return {
            "email": "test@example.com",
            "slack_webhook_url": "https://hooks.slack.com/services/TEST/WEBHOOK/URL",
        }

    @pytest.fixture
    def client(self, notification_config):
        """NotificationClient インスタンスを作成"""
        return NotificationClient(notification_config)

    @pytest.fixture
    def sample_animal_data(self):
        """サンプル AnimalData を作成"""
        return [
            AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                color="茶色",
                size="中型",
                shelter_date="2026-01-05",
                location="高知県動物愛護センター",
                phone="088-123-4567",
                image_urls=["https://example.com/image1.jpg"],
                source_url="https://example-kochi.jp/animals/123",
                category="adoption",
            )
        ]

    def test_initialization_with_config(self, notification_config):
        """設定を渡してインスタンス化できることを確認"""
        client = NotificationClient(notification_config)
        assert client.config == notification_config

    def test_notification_level_enum(self):
        """NotificationLevel 列挙型が正しく定義されていることを確認"""
        assert NotificationLevel.INFO == "info"
        assert NotificationLevel.WARNING == "warning"
        assert NotificationLevel.ERROR == "error"
        assert NotificationLevel.CRITICAL == "critical"

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_send_alert_slack_success(self, mock_post, client):
        """Slack アラート送信が成功することを確認"""
        mock_post.return_value.status_code = 200

        client.send_alert(
            level=NotificationLevel.CRITICAL,
            message="Page structure changed",
            details={"prefecture": "高知県"},
        )

        # Slack webhook が呼ばれたことを確認
        assert mock_post.called
        assert mock_post.call_count == 1

        # 呼び出し引数の確認
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://hooks.slack.com/services/TEST/WEBHOOK/URL"

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_send_alert_handles_failure_gracefully(self, mock_post, client):
        """通知失敗時も例外を投げず、ログ記録のみで処理継続することを確認"""
        mock_post.side_effect = Exception("Network error")

        # 例外が発生しないことを確認（best-effort）
        try:
            client.send_alert(
                level=NotificationLevel.ERROR, message="Test error", details={"error": "test"}
            )
        except Exception:
            pytest.fail("send_alert should not raise exceptions")

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_send_alert_includes_details(self, mock_post, client):
        """アラートに詳細情報が含まれることを確認"""
        mock_post.return_value.status_code = 200

        details = {
            "prefecture": "高知県",
            "url": "https://example.com",
            "error_type": "ParsingError",
        }

        client.send_alert(
            level=NotificationLevel.CRITICAL, message="Page structure changed", details=details
        )

        # POST リクエストの JSON ボディに details が含まれることを確認
        call_args = mock_post.call_args
        json_data = call_args[1]["json"]

        assert "Page structure changed" in json_data["text"]
        assert "高知県" in json_data["text"]

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_notify_new_animals_slack(self, mock_post, client, sample_animal_data):
        """新規収容動物の通知が送信されることを確認"""
        mock_post.return_value.status_code = 200

        client.notify_new_animals(sample_animal_data)

        # Slack webhook が呼ばれたことを確認
        assert mock_post.called

        # メッセージに動物情報が含まれることを確認
        call_args = mock_post.call_args
        json_data = call_args[1]["json"]

        assert "新規収容動物" in json_data["text"] or "1件" in json_data["text"]

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_notify_new_animals_empty_list(self, mock_post, client):
        """新規動物が0件の場合、通知が送信されないことを確認"""
        client.notify_new_animals([])

        # 空リストの場合は通知しない
        assert not mock_post.called

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_notify_new_animals_handles_failure_gracefully(
        self, mock_post, client, sample_animal_data
    ):
        """新規動物通知の失敗時も例外を投げないことを確認"""
        mock_post.side_effect = Exception("Network error")

        # 例外が発生しないことを確認
        try:
            client.notify_new_animals(sample_animal_data)
        except Exception:
            pytest.fail("notify_new_animals should not raise exceptions")

    def test_client_without_slack_config(self):
        """Slack 設定なしでもインスタンス化できることを確認"""
        config = {"email": "test@example.com"}
        client = NotificationClient(config)
        assert client.config == config

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_send_alert_different_levels(self, mock_post, client):
        """異なる通知レベルで送信できることを確認"""
        mock_post.return_value.status_code = 200

        levels = [
            NotificationLevel.INFO,
            NotificationLevel.WARNING,
            NotificationLevel.ERROR,
            NotificationLevel.CRITICAL,
        ]

        for level in levels:
            client.send_alert(
                level=level, message=f"Test {level} message", details={"test": "data"}
            )

        # 4回呼ばれたことを確認
        assert mock_post.call_count == 4

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_send_alert_has_timeout(self, mock_post, client):
        """requests.post に timeout が渡される（無限ハング防止 / Bandit B113）"""
        mock_post.return_value.status_code = 200
        client.send_alert(NotificationLevel.INFO, "msg", {"k": "v"})
        assert mock_post.call_args[1].get("timeout") is not None


class TestDiscordNotification:
    """Discord webhook 通知のテスト"""

    @pytest.fixture
    def discord_client(self):
        return NotificationClient(
            {"discord_webhook_url": "https://discord.com/api/webhooks/123/abc"}
        )

    @pytest.fixture
    def sample_animal_data(self):
        return [
            AnimalData(
                species="猫",
                sex="女の子",
                shelter_date="2026-06-19",
                location="高知県",
                source_url="https://example.jp/a/1",
                category="adoption",
            )
        ]

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_discord_alert_uses_content_field(self, mock_post, discord_client):
        """Discord は Slack の text ではなく content フィールドを使う"""
        mock_post.return_value.status_code = 204
        discord_client.send_alert(
            NotificationLevel.CRITICAL, "Page structure changed", {"prefecture": "高知県"}
        )
        assert mock_post.called
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://discord.com/api/webhooks/123/abc"
        json_data = call_args[1]["json"]
        assert "content" in json_data
        assert "text" not in json_data
        assert "Page structure changed" in json_data["content"]
        assert "高知県" in json_data["content"]

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_discord_content_truncated_to_limit(self, mock_post, discord_client):
        """Discord の 2000 文字上限を超えないよう content を切り詰める"""
        mock_post.return_value.status_code = 204
        big_details = {f"key{i}": "値" * 200 for i in range(50)}
        discord_client.send_alert(NotificationLevel.WARNING, "big", big_details)
        json_data = mock_post.call_args[1]["json"]
        assert len(json_data["content"]) <= 2000

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_discord_new_animals(self, mock_post, discord_client, sample_animal_data):
        mock_post.return_value.status_code = 204
        discord_client.notify_new_animals(sample_animal_data)
        assert mock_post.called
        json_data = mock_post.call_args[1]["json"]
        assert "content" in json_data
        assert "新規収容動物" in json_data["content"] or "1件" in json_data["content"]

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_both_channels_send_to_both(self, mock_post):
        """Slack と Discord 両方設定すると両方に送信される"""
        mock_post.return_value.status_code = 200
        client = NotificationClient(
            {
                "slack_webhook_url": "https://hooks.slack.com/services/X/Y/Z",
                "discord_webhook_url": "https://discord.com/api/webhooks/1/a",
            }
        )
        client.send_alert(NotificationLevel.WARNING, "msg", {"k": "v"})
        assert mock_post.call_count == 2
        urls = {c[0][0] for c in mock_post.call_args_list}
        assert "https://hooks.slack.com/services/X/Y/Z" in urls
        assert "https://discord.com/api/webhooks/1/a" in urls

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_discord_failure_is_graceful(self, mock_post, discord_client):
        mock_post.side_effect = Exception("Network error")
        try:
            discord_client.send_alert(NotificationLevel.ERROR, "x", {"e": "y"})
        except Exception:
            pytest.fail("send_alert should not raise")

    @patch("src.data_collector.infrastructure.notification_client.requests.post")
    def test_no_channel_no_send(self, mock_post):
        """チャネル未設定なら送信しない（no-op）"""
        client = NotificationClient({"email": "a@b.c"})
        client.send_alert(NotificationLevel.INFO, "x", {})
        assert not mock_post.called
