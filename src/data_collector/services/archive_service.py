"""
ArchiveService - アーカイブ処理オーケストレーションサービス

保持期間を経過した動物データをアクティブテーブルからアーカイブテーブルに
移動する処理を担当します。
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Protocol

from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.data_collector.infrastructure.database.archive_repository import ArchiveRepository


logger = logging.getLogger(__name__)


class NotificationClient(Protocol):
    """通知クライアントプロトコル"""

    async def send_alert(self, message: str, level: str = "warning") -> bool:
        """アラートを送信"""
        ...


@dataclass
class ArchiveJobResult:
    """
    アーカイブジョブ結果

    アーカイブ処理の実行結果を表現します。
    """

    started_at: datetime
    completed_at: datetime
    processed_count: int
    success_count: int
    error_count: int
    errors: List[str] = field(default_factory=list)


class ArchiveService:
    """
    アーカイブサービス

    保持期間を経過した動物データをアーカイブに移動するオーケストレーションを提供します。
    """

    DEFAULT_RETENTION_DAYS: int = 180
    DEFAULT_BATCH_SIZE: int = 1000

    def __init__(
        self,
        animal_repository: AnimalRepository,
        archive_repository: ArchiveRepository,
        image_storage_service: Optional["ImageStorageService"] = None,
        notification_client: Optional[NotificationClient] = None,
        retention_days: Optional[int] = None,
        batch_size: Optional[int] = None,
    ):
        """
        ArchiveService を初期化

        Args:
            animal_repository: 動物リポジトリ
            archive_repository: アーカイブリポジトリ
            image_storage_service: 画像ストレージサービス（オプション）
            notification_client: 通知クライアント（オプション、エラー通知用）
            retention_days: 保持期間（日数、デフォルト180、環境変数 RETENTION_DAYS で上書き可）
            batch_size: バッチサイズ（デフォルト1000）
        """
        self.animal_repository = animal_repository
        self.archive_repository = archive_repository
        self.image_storage_service = image_storage_service
        self.notification_client = notification_client

        # 保持期間: 引数 > 環境変数 > デフォルト
        if retention_days is not None:
            self.retention_days = retention_days
        else:
            env_retention = os.environ.get("RETENTION_DAYS")
            self.retention_days = int(env_retention) if env_retention else self.DEFAULT_RETENTION_DAYS

        self.batch_size = batch_size if batch_size is not None else self.DEFAULT_BATCH_SIZE

    async def run_archive_job(self) -> ArchiveJobResult:
        """
        アーカイブジョブを実行

        保持期間を経過した動物データをアーカイブテーブルに移動し、
        関連する画像ファイルもアーカイブストレージに移動します。

        Returns:
            ArchiveJobResult: ジョブ実行結果
        """
        started_at = datetime.now(timezone.utc)
        processed_count = 0
        success_count = 0
        error_count = 0
        errors: List[str] = []
        failed_ids: set = set()  # エラーが発生した動物IDを追跡

        try:
            # アーカイブ対象を全て処理するまでループ
            while True:
                # アーカイブ対象の動物を取得
                animals = await self.animal_repository.find_archivable_animals(
                    retention_days=self.retention_days,
                    limit=self.batch_size,
                )

                if not animals:
                    break

                # すべての動物が失敗済みの場合は終了（無限ループ防止）
                remaining_animals = [a for a in animals if a.id not in failed_ids]
                if not remaining_animals:
                    break

                # バッチ処理
                for animal in remaining_animals:
                    processed_count += 1
                    try:
                        await self._archive_single_animal(animal)
                        success_count += 1
                        logger.info(f"アーカイブ完了: animal_id={animal.id}")
                    except Exception as e:
                        error_count += 1
                        error_msg = f"animal_id={animal.id}: {str(e)}"
                        errors.append(error_msg)
                        failed_ids.add(animal.id)  # 失敗した動物を追跡
                        logger.error(f"アーカイブエラー: {error_msg}")

        except Exception as e:
            logger.exception("アーカイブジョブ中に予期しないエラー発生")
            errors.append(f"Job error: {str(e)}")

        completed_at = datetime.now(timezone.utc)

        result = ArchiveJobResult(
            started_at=started_at,
            completed_at=completed_at,
            processed_count=processed_count,
            success_count=success_count,
            error_count=error_count,
            errors=errors,
        )

        self._log_archive_result(result)

        # エラーがあった場合は通知
        if result.error_count > 0 and self.notification_client:
            await self._notify_errors(result)

        return result

    async def _notify_errors(self, result: ArchiveJobResult) -> None:
        """
        エラー発生時に運用者に通知

        Args:
            result: アーカイブジョブ結果
        """
        try:
            message = (
                f"アーカイブジョブでエラーが発生しました。\n"
                f"処理件数: {result.processed_count}\n"
                f"成功: {result.success_count}\n"
                f"エラー: {result.error_count}\n"
                f"エラー詳細: {result.errors[:5]}"  # 最初の5件のみ
            )
            await self.notification_client.send_alert(message, level="error")
        except Exception as e:
            logger.error(f"エラー通知の送信に失敗: {str(e)}")

    async def _archive_single_animal(self, animal) -> None:
        """
        単一の動物をアーカイブ

        Args:
            animal: アーカイブ対象の動物 ORM モデル
        """
        # 画像ファイルをアーカイブストレージに移動（設定されている場合）
        if self.image_storage_service and animal.local_image_paths:
            await self.image_storage_service.move_to_archive(animal.local_image_paths)

        # アーカイブテーブルに挿入
        await self.archive_repository.insert_archive(animal)

        # 元のテーブルから削除
        await self.animal_repository.delete_animal(animal.id)

    async def get_archivable_count(self) -> int:
        """
        アーカイブ対象件数を取得

        Returns:
            int: アーカイブ対象の動物件数
        """
        animals = await self.animal_repository.find_archivable_animals(
            retention_days=self.retention_days,
            limit=1000000,  # 件数取得のため大きな値
        )
        return len(animals)

    async def generate_daily_report(self) -> dict:
        """
        日次レポートを生成

        Returns:
            dict: レポートデータ
        """
        archivable_count = await self.get_archivable_count()
        status_counts = await self.animal_repository.get_status_counts()

        report = {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "archivable_count": archivable_count,
            "status_counts": status_counts,
        }

        # 画像ストレージサービスが設定されている場合はストレージ使用量を追加
        if self.image_storage_service:
            report["storage_usage_bytes"] = self.image_storage_service.get_storage_usage_bytes()
            report["image_download_failure_rate"] = self.image_storage_service.get_failure_rate()

        logger.info(f"日次レポート生成: {report}")

        return report

    def _log_archive_result(self, result: ArchiveJobResult) -> None:
        """
        アーカイブ結果をログに記録

        Args:
            result: アーカイブジョブ結果
        """
        duration = (result.completed_at - result.started_at).total_seconds()
        logger.info(
            f"アーカイブジョブ完了: "
            f"処理件数={result.processed_count}, "
            f"成功={result.success_count}, "
            f"エラー={result.error_count}, "
            f"処理時間={duration:.2f}秒"
        )

        if result.errors:
            logger.warning(f"アーカイブエラー詳細: {result.errors}")
