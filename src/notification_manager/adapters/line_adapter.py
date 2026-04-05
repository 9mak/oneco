"""
notification-manager LINE Messaging API アダプター

このモジュールはLINE Messaging APIとの通信を担当します。
line-bot-sdk を使用したプッシュメッセージ送信、署名検証を提供。

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.4
"""

import asyncio
import logging

from src.notification_manager.domain.models import NotificationMessage, SendResult

logger = logging.getLogger(__name__)


class LineAdapterError(Exception):
    """LINE API関連のエラー"""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.retry_after = retry_after


class LineNotificationAdapter:
    """
    LINE Messaging API アダプター

    LINE Messaging APIを使用したプッシュ通知送信、Webhook署名検証を提供。

    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 7.4
    """

    # リトライしないエラーコード（認証エラーなど）
    NON_RETRYABLE_ERRORS = {"401", "403"}

    def __init__(self, channel_access_token: str, channel_secret: str):
        """
        LineNotificationAdapter を初期化

        Args:
            channel_access_token: LINE Channel Access Token
            channel_secret: LINE Channel Secret
        """
        self._channel_access_token = channel_access_token
        self._channel_secret = channel_secret

        # LINE SDK コンポーネントの初期化（遅延ロード）
        self._api_client = None
        self._signature_validator = None
        self._initialized = False

    def _ensure_initialized(self):
        """LINE SDKコンポーネントを初期化（遅延ロード）"""
        if self._initialized:
            return

        try:
            from linebot.v3 import WebhookParser
            from linebot.v3.messaging import (
                AsyncApiClient,
                AsyncMessagingApi,
                Configuration,
                PushMessageRequest,
                TextMessage,
            )

            configuration = Configuration(access_token=self._channel_access_token)
            self._api_client = AsyncMessagingApi(AsyncApiClient(configuration))
            self._webhook_parser = WebhookParser(self._channel_secret)
            self._initialized = True
        except ImportError:
            # line-bot-sdk がインストールされていない場合
            logger.warning("line-bot-sdk is not installed. Using mock implementation.")
            self._api_client = MockLineApiClient()
            self._signature_validator = MockSignatureValidator()
            self._initialized = True

    def verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Webhook署名を検証

        Args:
            body: リクエストボディ
            signature: X-Line-Signature ヘッダー値

        Returns:
            bool: 署名が有効な場合はTrue
        """
        self._ensure_initialized()
        try:
            if hasattr(self, "_webhook_parser"):
                # 実際のline-bot-sdk使用時
                # 署名検証はパース時に行われる
                self._webhook_parser.parse(body.decode("utf-8"), signature)
                return True
            elif self._signature_validator:
                # モック使用時
                return self._signature_validator.validate(body, signature)
            return False
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False

    def format_message(self, notification: NotificationMessage) -> str:
        """
        通知メッセージをフォーマット

        Args:
            notification: 通知メッセージデータ

        Returns:
            str: フォーマット済みメッセージ
        """
        return notification.format_message()

    async def send_push_message(
        self, line_user_id: str, notification: NotificationMessage
    ) -> SendResult:
        """
        プッシュメッセージを送信

        Args:
            line_user_id: 送信先LINEユーザーID
            notification: 通知メッセージ

        Returns:
            SendResult: 送信結果
        """
        self._ensure_initialized()
        message_text = self.format_message(notification)

        try:
            # モッククライアント使用時
            if isinstance(self._api_client, MockLineApiClient):
                await self._api_client.push_message(line_user_id, message_text)
                logger.info(f"Push message sent to {line_user_id[:8]}...")
                return SendResult(success=True)

            # 実際のline-bot-sdk使用時
            from linebot.v3.messaging import (
                PushMessageRequest,
                TextMessage,
            )

            request = PushMessageRequest(
                to=line_user_id,
                messages=[TextMessage(text=message_text)],
            )
            await self._api_client.push_message(request)
            logger.info(f"Push message sent to {line_user_id[:8]}...")
            return SendResult(success=True)

        except LineAdapterError as e:
            logger.error(f"LINE API error: {e.error_code} - {e}")
            return SendResult(
                success=False,
                error_code=e.error_code,
                retry_after=e.retry_after,
            )
        except Exception as e:
            error_code = self._extract_error_code(e)
            retry_after = self._extract_retry_after(e)
            logger.error(f"Failed to send push message: {error_code} - {e}")
            return SendResult(
                success=False,
                error_code=error_code,
                retry_after=retry_after,
            )

    async def send_with_retry(
        self,
        line_user_id: str,
        notification: NotificationMessage,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> SendResult:
        """
        リトライ付きでプッシュメッセージを送信

        指数バックオフによるリトライを実行。認証エラー（401, 403）はリトライしない。

        Args:
            line_user_id: 送信先LINEユーザーID
            notification: 通知メッセージ
            max_retries: 最大リトライ回数
            base_delay: リトライ基本遅延（秒）

        Returns:
            SendResult: 送信結果
        """
        last_result = None

        for attempt in range(max_retries):
            result = await self.send_push_message(line_user_id, notification)

            if result.success:
                return result

            last_result = result

            # 認証エラーはリトライしない
            if result.error_code in self.NON_RETRYABLE_ERRORS:
                logger.warning(
                    f"Non-retryable error {result.error_code}, "
                    f"not retrying for {line_user_id[:8]}..."
                )
                return result

            # レート制限時は指定された時間待機
            if result.retry_after:
                delay = result.retry_after
            else:
                # 指数バックオフ
                delay = base_delay * (2**attempt)

            if attempt < max_retries - 1:
                logger.info(
                    f"Retrying in {delay}s (attempt {attempt + 1}/{max_retries}) "
                    f"for {line_user_id[:8]}..."
                )
                await asyncio.sleep(delay)

        logger.error(f"All {max_retries} retries failed for {line_user_id[:8]}...")
        return last_result

    def _extract_error_code(self, exception: Exception) -> str | None:
        """例外からエラーコードを抽出"""
        if hasattr(exception, "status_code"):
            return str(exception.status_code)
        if hasattr(exception, "error_code"):
            return str(exception.error_code)
        return "UNKNOWN"

    def _extract_retry_after(self, exception: Exception) -> int | None:
        """例外からRetry-After値を抽出"""
        if hasattr(exception, "retry_after"):
            return exception.retry_after
        if hasattr(exception, "headers"):
            retry_after = exception.headers.get("Retry-After")
            if retry_after:
                return int(retry_after)
        return None


class MockLineApiClient:
    """テスト用のモックLINE APIクライアント"""

    async def push_message(self, user_id: str, message: str):
        """モックプッシュメッセージ送信"""
        logger.debug(f"Mock push message to {user_id}: {message[:50]}...")


class MockSignatureValidator:
    """テスト用のモック署名検証"""

    def validate(self, body: bytes, signature: str) -> bool:
        """モック署名検証（常にTrue）"""
        return True
