"""
notification-manager LINEアダプターのテスト

Task 4.1, 4.2, 4.3: LINE Messaging API連携、エラーハンドリング、メッセージフォーマットのテスト
"""

import pytest

from src.notification_manager.adapters.line_adapter import (
    LineAdapterError,
    LineNotificationAdapter,
    MockLineApiClient,
    MockSignatureValidator,
)
from src.notification_manager.domain.models import NotificationMessage


class TestLineNotificationAdapter:
    """LINE通知アダプターのテスト"""

    @pytest.fixture
    def adapter(self):
        """テスト用アダプター（モック設定）"""
        adapter = LineNotificationAdapter(
            channel_access_token="test_token",
            channel_secret="test_secret",
        )
        # テスト用にモッククライアントを直接設定
        adapter._api_client = MockLineApiClient()
        adapter._signature_validator = MockSignatureValidator()
        adapter._initialized = True
        return adapter

    def test_create_adapter(self):
        """アダプターを作成できる"""
        adapter = LineNotificationAdapter(
            channel_access_token="test_token",
            channel_secret="test_secret",
        )
        assert adapter is not None
        assert adapter._channel_access_token == "test_token"
        assert adapter._channel_secret == "test_secret"

    def test_verify_signature_with_mock_validator(self, adapter):
        """モック署名検証が動作する"""
        # モック検証は常にTrueを返す
        result = adapter.verify_signature(b"test_body", "valid_signature")
        assert result is True

    def test_format_notification_message(self, adapter):
        """通知メッセージをフォーマットできる"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            age_months=24,
            size="中型",
            location="高知県高知市",
            source_url="https://example.com/animals/123",
            category="adoption",
        )
        formatted = adapter.format_message(msg)
        assert "犬" in formatted
        assert "男の子" in formatted
        assert "高知県高知市" in formatted
        assert "https://example.com/animals/123" in formatted

    def test_format_message_with_age_years(self, adapter):
        """年齢が1歳以上の場合の表示"""
        msg = NotificationMessage(
            species="猫",
            sex="女の子",
            age_months=36,
            size="小型",
            location="東京都新宿区",
            source_url="https://example.com/animals/456",
            category="adoption",
        )
        formatted = adapter.format_message(msg)
        assert "約3歳" in formatted

    def test_format_message_lost_category(self, adapter):
        """迷子カテゴリのメッセージ"""
        msg = NotificationMessage(
            species="犬",
            sex="不明",
            location="大阪府",
            source_url="https://example.com/animals/789",
            category="lost",
        )
        formatted = adapter.format_message(msg)
        assert "迷子" in formatted

    @pytest.mark.asyncio
    async def test_send_push_message_success(self, adapter):
        """プッシュメッセージを送信できる（成功）"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

        result = await adapter.send_push_message("U1234567890", msg)

        assert result.success is True
        assert result.error_code is None

    @pytest.mark.asyncio
    async def test_send_push_message_with_error(self, adapter):
        """プッシュメッセージ送信エラー時のハンドリング"""
        msg = NotificationMessage(
            species="猫",
            sex="女の子",
            location="東京都",
            source_url="https://example.com/animals/2",
            category="lost",
        )

        # エラーを発生させる
        async def raise_error(*args, **kwargs):
            raise LineAdapterError("Rate limited", error_code="429", retry_after=60)

        adapter._api_client.push_message = raise_error

        result = await adapter.send_push_message("U1234567890", msg)

        assert result.success is False
        assert result.error_code == "429"
        assert result.retry_after == 60


class TestLineAdapterRetry:
    """リトライ機能のテスト"""

    @pytest.fixture
    def adapter(self):
        """テスト用アダプター"""
        adapter = LineNotificationAdapter(
            channel_access_token="test_token",
            channel_secret="test_secret",
        )
        adapter._api_client = MockLineApiClient()
        adapter._signature_validator = MockSignatureValidator()
        adapter._initialized = True
        return adapter

    @pytest.mark.asyncio
    async def test_send_with_retry_success_first_try(self, adapter):
        """リトライなしで成功"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

        result = await adapter.send_with_retry("U123", msg, max_retries=3)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_send_with_retry_success_after_retry(self, adapter):
        """リトライ後に成功"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

        call_count = 0

        async def flaky_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise LineAdapterError("Server error", error_code="500")
            # 3回目で成功

        adapter._api_client.push_message = flaky_send

        result = await adapter.send_with_retry("U123", msg, max_retries=3, base_delay=0.01)

        assert result.success is True
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_send_with_retry_all_failures(self, adapter):
        """リトライ上限到達後も失敗"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

        async def always_fail(*args, **kwargs):
            raise LineAdapterError("Server error", error_code="500")

        adapter._api_client.push_message = always_fail

        result = await adapter.send_with_retry("U123", msg, max_retries=3, base_delay=0.01)

        assert result.success is False
        assert result.error_code == "500"

    @pytest.mark.asyncio
    async def test_send_with_retry_no_retry_on_auth_error(self, adapter):
        """認証エラーはリトライしない"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

        call_count = 0

        async def auth_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise LineAdapterError("Unauthorized", error_code="401")

        adapter._api_client.push_message = auth_error

        result = await adapter.send_with_retry("U123", msg, max_retries=3, base_delay=0.01)

        assert result.success is False
        assert result.error_code == "401"
        # 401エラーはリトライしないので1回のみ
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_send_with_retry_respects_retry_after(self, adapter):
        """レート制限時のretry_afterを尊重"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

        call_count = 0

        async def rate_limited_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise LineAdapterError("Rate limited", error_code="429", retry_after=1)
            # 2回目で成功

        adapter._api_client.push_message = rate_limited_then_success

        # 小さい基本遅延だが、retry_afterが優先される
        result = await adapter.send_with_retry("U123", msg, max_retries=3, base_delay=0.001)

        assert result.success is True
        assert call_count == 2


class TestLineAdapterError:
    """LineAdapterErrorのテスト"""

    def test_create_error_with_code(self):
        """エラーコード付きでエラーを作成できる"""
        error = LineAdapterError("Test error", error_code="429", retry_after=60)
        assert str(error) == "Test error"
        assert error.error_code == "429"
        assert error.retry_after == 60

    def test_create_error_without_code(self):
        """エラーコードなしでエラーを作成できる"""
        error = LineAdapterError("Simple error")
        assert str(error) == "Simple error"
        assert error.error_code is None
        assert error.retry_after is None
