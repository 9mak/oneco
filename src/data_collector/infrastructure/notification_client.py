"""運用者通知クライアント"""

import logging
from enum import StrEnum
from typing import Any

try:
    import requests
except ImportError:
    requests = None

from ..domain.models import AnimalData

# webhook 送信のタイムアウト（秒）。無限ハング防止（Bandit B113）。
_WEBHOOK_TIMEOUT_SEC = 10
# Discord メッセージ content の最大長（API 仕様 2000 文字）。
_DISCORD_CONTENT_LIMIT = 2000


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
            # 設定済みチャネルすべてに送信（Slack / Discord は併用可）
            sent = False
            if "slack_webhook_url" in self.config:
                self._send_slack_alert(level, message, details)
                sent = True
            if "discord_webhook_url" in self.config:
                self._send_discord_alert(level, message, details)
                sent = True
            if not sent:
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
            # 設定済みチャネルすべてに送信（Slack / Discord は併用可）
            sent = False
            if "slack_webhook_url" in self.config:
                self._send_new_animals_slack(new_animals)
                sent = True
            if "discord_webhook_url" in self.config:
                self._send_new_animals_discord(new_animals)
                sent = True
            if not sent:
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

        response = requests.post(webhook_url, json=payload, timeout=_WEBHOOK_TIMEOUT_SEC)
        response.raise_for_status()

        self.logger.info(f"Alert sent to Slack: {level} - {message}")

    def _build_alert_text(
        self, level: NotificationLevel, message: str, details: dict[str, Any]
    ) -> str:
        """アラート本文を組み立てる（Slack / Discord 共通）"""
        text = f"[{level.upper()}] {message}\n"
        for key, value in details.items():
            text += f"- {key}: {value}\n"
        return text

    def _send_discord_alert(
        self, level: NotificationLevel, message: str, details: dict[str, Any]
    ) -> None:
        """Discord にアラートを送信（content フィールド・2000 文字上限）"""
        if requests is None:
            self.logger.error("requests library not available")
            return

        webhook_url = self.config["discord_webhook_url"]
        content = self._build_alert_text(level, message, details)[:_DISCORD_CONTENT_LIMIT]

        response = requests.post(
            webhook_url, json={"content": content}, timeout=_WEBHOOK_TIMEOUT_SEC
        )
        response.raise_for_status()

        self.logger.info(f"Alert sent to Discord: {level} - {message}")

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

        response = requests.post(webhook_url, json=payload, timeout=_WEBHOOK_TIMEOUT_SEC)
        response.raise_for_status()

        self.logger.info(f"New animals notification sent to Slack: {len(new_animals)} animals")

    def _build_new_animals_text(self, new_animals: list[AnimalData]) -> str:
        """新規収容動物の本文を組み立てる（Slack / Discord 共通）"""
        text = f"🐾 新規収容動物: {len(new_animals)}件\n"
        for animal in new_animals[:5]:  # 最大5件まで詳細表示
            text += f"- {animal.species} ({animal.sex})"
            if animal.location:
                text += f" - {animal.location}"
            text += f" - {animal.source_url}\n"
        if len(new_animals) > 5:
            text += f"... 他 {len(new_animals) - 5}件\n"
        return text

    def _send_new_animals_discord(self, new_animals: list[AnimalData]) -> None:
        """Discord に新規収容動物を通知（content フィールド・2000 文字上限）"""
        if requests is None:
            self.logger.error("requests library not available")
            return

        webhook_url = self.config["discord_webhook_url"]
        content = self._build_new_animals_text(new_animals)[:_DISCORD_CONTENT_LIMIT]

        response = requests.post(
            webhook_url, json={"content": content}, timeout=_WEBHOOK_TIMEOUT_SEC
        )
        response.raise_for_status()

        self.logger.info(f"New animals notification sent to Discord: {len(new_animals)} animals")
