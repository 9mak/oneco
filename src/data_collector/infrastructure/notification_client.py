"""運用者通知クライアント"""

import logging
from enum import StrEnum
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from ..domain.models import AnimalData


class NotificationLevel(StrEnum):
    """通知レベル"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationClient:
    """
    ページ構造変更・新規データ検知時に運用者へ通知

    Responsibilities:
    - エラーアラートの送信（ページ構造変更時）
    - 新規データ通知（オプション、notification-manager への委譲も検討）
    - 通知先の設定管理（環境変数）

    Requirements: 1.5
    """

    def __init__(self, notification_config: dict[str, Any]):
        """
        NotificationClient を初期化

        Args:
            notification_config: 通知先設定（email, slack_webhook_url など）
        """
        self.config = notification_config
        self.logger = logging.getLogger(__name__)

    def send_alert(self, level: NotificationLevel, message: str, details: dict[str, Any]) -> None:
        """
        運用者にアラートを送信

        Args:
            level: 通知レベル
            message: 通知メッセージ
            details: 詳細情報（URL, エラー内容等）

        Preconditions: config に有効な通知先が設定されている
        Postconditions: 通知が送信される（best-effort）

        Note: 通知失敗時はログ記録のみで処理継続（例外をスローしない）
        """
        try:
            # Slack webhook URL が設定されている場合、Slack に送信
            if "slack_webhook_url" in self.config:
                self._send_slack_alert(level, message, details)
            else:
                self.logger.warning(
                    f"No notification channel configured. Alert: {level} - {message}"
                )
        except Exception as e:
            # best-effort: 通知失敗時はログ記録のみ（収集処理自体は継続）
            self.logger.error(f"Failed to send alert: {e!s}", exc_info=True)

    def notify_new_animals(self, new_animals: list[AnimalData]) -> None:
        """
        新規収容動物を通知（オプション機能）

        Args:
            new_animals: 新規個体リスト

        Note: Phase 2 では notification-manager に委譲予定
              空リストの場合は通知しない
        """
        if not new_animals:
            return

        try:
            # Slack webhook URL が設定されている場合、Slack に送信
            if "slack_webhook_url" in self.config:
                self._send_new_animals_slack(new_animals)
            else:
                self.logger.info(
                    f"No notification channel configured. {len(new_animals)} new animals found."
                )
        except Exception as e:
            # best-effort: 通知失敗時はログ記録のみ
            self.logger.error(f"Failed to notify new animals: {e!s}", exc_info=True)

    def _send_slack_alert(
        self, level: NotificationLevel, message: str, details: dict[str, Any]
    ) -> None:
        """
        Slack にアラートを送信

        Args:
            level: 通知レベル
            message: 通知メッセージ
            details: 詳細情報
        """
        if requests is None:
            self.logger.error("requests library not available")
            return

        webhook_url = self.config["slack_webhook_url"]

        # Slack メッセージフォーマット
        text = f"[{level.upper()}] {message}\n"
        for key, value in details.items():
            text += f"- {key}: {value}\n"

        payload = {"text": text}

        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()

        self.logger.info(f"Alert sent to Slack: {level} - {message}")

    def _send_new_animals_slack(self, new_animals: list[AnimalData]) -> None:
        """
        Slack に新規収容動物を通知

        Args:
            new_animals: 新規個体リスト
        """
        if requests is None:
            self.logger.error("requests library not available")
            return

        webhook_url = self.config["slack_webhook_url"]

        # Slack メッセージフォーマット
        text = f"🐾 新規収容動物: {len(new_animals)}件\n"

        for animal in new_animals[:5]:  # 最大5件まで詳細表示
            text += f"- {animal.species} ({animal.sex})"
            if animal.location:
                text += f" - {animal.location}"
            text += f" - {animal.source_url}\n"

        if len(new_animals) > 5:
            text += f"... 他 {len(new_animals) - 5}件\n"

        payload = {"text": text}

        response = requests.post(webhook_url, json=payload)
        response.raise_for_status()

        self.logger.info(f"New animals notification sent to Slack: {len(new_animals)} animals")
