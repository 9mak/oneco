"""notification-manager 連携クライアント

data-collector から notification-manager への新着動物通知を担当します。
notification-manager は LINE Messaging API を使用してユーザーに通知を送信します。

Requirements: 2.1, 2.2 (notification-manager との連携)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass

try:
    import httpx
except ImportError:
    httpx = None

from ..domain.models import AnimalData


@dataclass
class NotificationManagerConfig:
    """
    notification-manager 連携設定

    Attributes:
        url: notification-manager の API URL
        api_key: 認証用 API キー
        timeout: リクエストタイムアウト（秒）
        enabled: 連携有効フラグ
    """

    url: str
    api_key: str
    timeout: float = 10.0
    enabled: bool = True


class NotificationManagerClient:
    """
    notification-manager API クライアント

    data-collector の新着動物データを notification-manager に送信し、
    条件にマッチするユーザーへの LINE 通知をトリガーします。

    Responsibilities:
    - 新着動物データの notification-manager への送信
    - best-effort 配信（送信失敗時もログ記録のみで処理継続）

    Requirements: 2.1, 2.2 (notification-manager との連携)
    """

    WEBHOOK_ENDPOINT = "/api/v1/notifications/webhook"

    def __init__(self, config: NotificationManagerConfig):
        """
        NotificationManagerClient を初期化

        Args:
            config: notification-manager 連携設定
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def notify_new_animals(self, new_animals: List[AnimalData]) -> bool:
        """
        新着動物を notification-manager に通知（非同期）

        Args:
            new_animals: 新規個体リスト

        Returns:
            bool: 送信成功時は True、失敗時は False

        Note:
            - best-effort: 通知失敗時はログ記録のみで例外をスローしない
            - 空リストの場合は送信をスキップ
            - enabled=False の場合は送信をスキップ
        """
        if not new_animals:
            self.logger.debug("No new animals to notify, skipping")
            return True

        if not self.config.enabled:
            self.logger.debug("Notification manager integration disabled, skipping")
            return True

        if httpx is None:
            self.logger.error("httpx library not available")
            return False

        try:
            # リクエストペイロードを構築
            payload = self._build_payload(new_animals)

            # notification-manager に送信
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                url = f"{self.config.url.rstrip('/')}{self.WEBHOOK_ENDPOINT}"
                headers = {
                    "X-API-Key": self.config.api_key,
                    "Content-Type": "application/json",
                }

                self.logger.info(
                    f"Sending {len(new_animals)} new animals to notification-manager",
                    extra={"url": url},
                )

                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                self.logger.info(
                    f"Successfully notified notification-manager: {len(new_animals)} animals",
                    extra={"status_code": response.status_code},
                )
                return True

        except Exception as e:
            # best-effort: 通知失敗時はログ記録のみで処理継続
            self.logger.error(
                f"Failed to notify notification-manager: {str(e)}",
                exc_info=True,
            )
            return False

    def notify_new_animals_sync(self, new_animals: List[AnimalData]) -> bool:
        """
        新着動物を notification-manager に通知（同期ラッパー）

        CollectorService のような同期コンテキストから呼び出す場合に使用。

        Args:
            new_animals: 新規個体リスト

        Returns:
            bool: 送信成功時は True、失敗時は False
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # イベントループが既に実行中の場合は新しいループで実行
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run, self.notify_new_animals(new_animals)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(self.notify_new_animals(new_animals))
        except Exception as e:
            self.logger.error(
                f"Failed to notify notification-manager (sync): {str(e)}",
                exc_info=True,
            )
            return False

    def _build_payload(self, animals: List[AnimalData]) -> dict:
        """
        notification-manager Webhook リクエストペイロードを構築

        Args:
            animals: 動物データリスト

        Returns:
            dict: Webhook リクエストペイロード
        """
        return {
            "animals": [self._serialize_animal(animal) for animal in animals],
            "source": "data-collector",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _serialize_animal(self, animal: AnimalData) -> dict:
        """
        AnimalData を JSON シリアライズ可能な形式に変換

        Args:
            animal: 動物データ

        Returns:
            dict: シリアライズされた動物データ
        """
        return {
            "species": animal.species,
            "sex": animal.sex,
            "age_months": animal.age_months,
            "color": animal.color,
            "size": animal.size,
            "shelter_date": animal.shelter_date.isoformat(),
            "location": animal.location,
            "phone": animal.phone,
            "image_urls": [str(url) for url in animal.image_urls],
            "source_url": str(animal.source_url),
            "category": animal.category,
        }


def create_notification_manager_client_from_env() -> Optional[NotificationManagerClient]:
    """
    環境変数から NotificationManagerClient を作成

    環境変数:
        NOTIFICATION_MANAGER_URL: notification-manager の URL
        NOTIFICATION_MANAGER_API_KEY: 認証用 API キー
        NOTIFICATION_MANAGER_TIMEOUT: タイムアウト（秒、デフォルト: 10.0）
        NOTIFICATION_MANAGER_ENABLED: 有効フラグ（デフォルト: true）

    Returns:
        Optional[NotificationManagerClient]: 設定が有効な場合はクライアント、
                                              無効な場合は None
    """
    import os

    url = os.environ.get("NOTIFICATION_MANAGER_URL", "")
    api_key = os.environ.get("NOTIFICATION_MANAGER_API_KEY", "")
    timeout = float(os.environ.get("NOTIFICATION_MANAGER_TIMEOUT", "10.0"))
    enabled = os.environ.get("NOTIFICATION_MANAGER_ENABLED", "true").lower() == "true"

    if not enabled:
        logging.getLogger(__name__).info(
            "Notification manager integration disabled via environment"
        )
        return None

    if not url or not api_key:
        logging.getLogger(__name__).warning(
            "Notification manager URL or API key not configured, integration disabled"
        )
        return None

    config = NotificationManagerConfig(
        url=url,
        api_key=api_key,
        timeout=timeout,
        enabled=enabled,
    )

    return NotificationManagerClient(config)
