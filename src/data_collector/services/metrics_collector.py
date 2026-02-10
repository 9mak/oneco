"""
AnimalMetricsCollector - 動物データのメトリクス収集

動物データのステータス別件数、ストレージ使用量、失敗率などの
メトリクスを収集するサービスを提供します。
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from src.data_collector.infrastructure.database.repository import AnimalRepository

logger = logging.getLogger(__name__)


@dataclass
class AnimalMetrics:
    """
    動物メトリクス

    動物データのメトリクス情報を保持するデータクラス。
    """

    total_count: int
    status_counts: Dict[str, int]
    category_counts: Dict[str, int]
    archivable_count: int
    image_download_failure_rate: float
    storage_usage_bytes: int


class AnimalMetricsCollector:
    """
    動物メトリクスコレクター

    動物データのメトリクスを収集し、監視システムに提供します。
    """

    def __init__(
        self,
        animal_repository: AnimalRepository,
        archive_service: Optional["ArchiveService"] = None,
        image_storage_service: Optional["ImageStorageService"] = None,
    ):
        """
        AnimalMetricsCollector を初期化

        Args:
            animal_repository: 動物リポジトリ
            archive_service: アーカイブサービス（オプション）
            image_storage_service: 画像ストレージサービス（オプション）
        """
        self.animal_repository = animal_repository
        self.archive_service = archive_service
        self.image_storage_service = image_storage_service

    async def collect(self) -> AnimalMetrics:
        """
        全メトリクスを収集

        Returns:
            AnimalMetrics: 収集したメトリクス
        """
        # ステータス別件数を取得
        status_counts = await self.get_status_counts()

        # 総件数を計算
        total_count = sum(status_counts.values())

        # カテゴリ別件数を取得
        category_counts = await self.get_category_counts()

        # アーカイブ対象件数を取得
        archivable_count = 0
        if self.archive_service:
            archivable_count = await self.archive_service.get_archivable_count()

        # 画像ダウンロード失敗率を取得
        failure_rate = 0.0
        storage_usage = 0
        if self.image_storage_service:
            failure_rate = self.image_storage_service.get_failure_rate()
            storage_usage = self.image_storage_service.get_storage_usage_bytes()

        return AnimalMetrics(
            total_count=total_count,
            status_counts=status_counts,
            category_counts=category_counts,
            archivable_count=archivable_count,
            image_download_failure_rate=failure_rate,
            storage_usage_bytes=storage_usage,
        )

    async def get_status_counts(self) -> Dict[str, int]:
        """
        ステータス別件数を取得

        Returns:
            Dict[str, int]: {status: count} 形式のステータス別件数
        """
        return await self.animal_repository.get_status_counts()

    async def get_category_counts(self) -> Dict[str, int]:
        """
        カテゴリ別件数を取得

        Returns:
            Dict[str, int]: {category: count} 形式のカテゴリ別件数
        """
        # list_animals を使用してカテゴリ別件数を取得
        adoption_animals, adoption_count = await self.animal_repository.list_animals(
            category="adoption", limit=0
        )
        lost_animals, lost_count = await self.animal_repository.list_animals(
            category="lost", limit=0
        )

        return {
            "adoption": adoption_count,
            "lost": lost_count,
        }


class AlertManager:
    """
    アラートマネージャー

    メトリクスに基づいてアラートを発生させるサービス。
    """

    DEFAULT_FAILURE_RATE_THRESHOLD = 0.1  # 10%
    DEFAULT_STORAGE_THRESHOLD_BYTES = 10 * 1024 * 1024 * 1024  # 10GB

    def __init__(
        self,
        notification_client: Optional["NotificationClient"] = None,
        failure_rate_threshold: Optional[float] = None,
        storage_threshold_bytes: Optional[int] = None,
    ):
        """
        AlertManager を初期化

        Args:
            notification_client: 通知クライアント（オプション）
            failure_rate_threshold: 失敗率閾値（デフォルト: 0.1 = 10%）
            storage_threshold_bytes: ストレージ使用量閾値（バイト、デフォルト: 10GB）
        """
        self.notification_client = notification_client
        self.failure_rate_threshold = (
            failure_rate_threshold
            if failure_rate_threshold is not None
            else self.DEFAULT_FAILURE_RATE_THRESHOLD
        )
        self.storage_threshold_bytes = (
            storage_threshold_bytes
            if storage_threshold_bytes is not None
            else self.DEFAULT_STORAGE_THRESHOLD_BYTES
        )

    async def check_and_alert(self, metrics: AnimalMetrics) -> list:
        """
        メトリクスをチェックしてアラートを発生

        Args:
            metrics: 動物メトリクス

        Returns:
            list: 発生したアラートのリスト
        """
        alerts = []

        # 画像ダウンロード失敗率チェック
        if metrics.image_download_failure_rate > self.failure_rate_threshold:
            alert = {
                "type": "image_download_failure_rate",
                "level": "warning",
                "message": (
                    f"画像ダウンロード失敗率が閾値を超えました: "
                    f"{metrics.image_download_failure_rate:.1%} > {self.failure_rate_threshold:.1%}"
                ),
                "value": metrics.image_download_failure_rate,
                "threshold": self.failure_rate_threshold,
            }
            alerts.append(alert)
            logger.warning(alert["message"])

        # ストレージ使用量チェック
        if metrics.storage_usage_bytes > self.storage_threshold_bytes:
            storage_gb = metrics.storage_usage_bytes / (1024 * 1024 * 1024)
            threshold_gb = self.storage_threshold_bytes / (1024 * 1024 * 1024)
            alert = {
                "type": "storage_usage",
                "level": "warning",
                "message": (
                    f"ストレージ使用量が閾値を超えました: "
                    f"{storage_gb:.1f}GB > {threshold_gb:.1f}GB"
                ),
                "value": metrics.storage_usage_bytes,
                "threshold": self.storage_threshold_bytes,
            }
            alerts.append(alert)
            logger.warning(alert["message"])

        # 通知クライアントが設定されている場合は通知を送信
        if alerts and self.notification_client:
            await self._send_alerts(alerts)

        return alerts

    async def _send_alerts(self, alerts: list) -> None:
        """
        アラートを送信

        Args:
            alerts: 送信するアラートのリスト
        """
        try:
            message = "アラート発生:\n"
            for alert in alerts:
                message += f"- [{alert['level'].upper()}] {alert['message']}\n"
            await self.notification_client.send_alert(message, level="warning")
        except Exception as e:
            logger.error(f"アラート送信に失敗: {str(e)}")


class AuditLogger:
    """
    監査ログ

    ステータス変更操作などを監査ログとして記録します。
    """

    def __init__(self):
        """AuditLogger を初期化"""
        self.logger = logging.getLogger("audit")

    def log_status_change(
        self,
        animal_id: int,
        old_status: str,
        new_status: str,
        changed_by: Optional[str] = None,
    ) -> None:
        """
        ステータス変更を監査ログに記録

        Args:
            animal_id: 動物ID
            old_status: 変更前のステータス
            new_status: 変更後のステータス
            changed_by: 変更者（オプション）
        """
        self.logger.info(
            f"STATUS_CHANGE: animal_id={animal_id}, "
            f"old_status={old_status}, new_status={new_status}, "
            f"changed_by={changed_by or 'system'}"
        )

    def log_archive(self, animal_id: int, original_id: int) -> None:
        """
        アーカイブ操作を監査ログに記録

        Args:
            animal_id: アーカイブID
            original_id: 元の動物ID
        """
        self.logger.info(
            f"ARCHIVE: animal_id={animal_id}, original_id={original_id}"
        )

    def log_image_download(
        self,
        animal_id: int,
        url: str,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """
        画像ダウンロード操作を監査ログに記録

        Args:
            animal_id: 動物ID
            url: 画像URL
            success: 成功/失敗
            error: エラーメッセージ（失敗時）
        """
        if success:
            self.logger.info(f"IMAGE_DOWNLOAD: animal_id={animal_id}, url={url}, success=True")
        else:
            self.logger.warning(
                f"IMAGE_DOWNLOAD: animal_id={animal_id}, url={url}, "
                f"success=False, error={error}"
            )
