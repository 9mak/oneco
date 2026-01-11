"""収集オーケストレーションサービス"""

from typing import List
from pathlib import Path
import logging
import time
import uuid
from pydantic import BaseModel

from ..adapters.municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError
from ..domain.diff_detector import DiffDetector, DiffResult
from ..domain.models import AnimalData
from ..infrastructure.output_writer import OutputWriter
from ..infrastructure.notification_client import NotificationClient, NotificationLevel
from ..infrastructure.snapshot_store import SnapshotStore


class CollectionResult(BaseModel):
    """
    収集結果サマリー

    Attributes:
        success: 収集が成功したか
        total_collected: 収集した総件数
        new_count: 新規件数
        updated_count: 更新件数
        deleted_count: 削除候補件数
        errors: エラーメッセージリスト
        execution_time_seconds: 実行時間（秒）
    """
    success: bool
    total_collected: int = 0
    new_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    errors: List[str] = []
    execution_time_seconds: float = 0.0


class CollectorService:
    """
    収集プロセス全体のオーケストレーション

    Responsibilities:
    - アダプター呼び出し、差分検知、出力書き込みの調整
    - エラーハンドリング・リトライロジック
    - 構造化ログ出力
    - 重複実行防止（ロックファイル）

    Requirements: 5.1, 5.2, 5.5, 6.3, 6.4, 6.5
    """

    LOCK_FILE = Path(".collector.lock")

    def __init__(
        self,
        adapter: MunicipalityAdapter,
        diff_detector: DiffDetector,
        output_writer: OutputWriter,
        notification_client: NotificationClient,
        snapshot_store: SnapshotStore
    ):
        """
        CollectorService を初期化

        Args:
            adapter: 自治体別アダプター
            diff_detector: 差分検知サービス
            output_writer: JSON 出力サービス
            notification_client: 通知クライアント
            snapshot_store: スナップショットストア
        """
        self.adapter = adapter
        self.diff_detector = diff_detector
        self.output_writer = output_writer
        self.notification_client = notification_client
        self.snapshot_store = snapshot_store
        self.logger = logging.getLogger(__name__)
        self._structure_changed = False

    def run_collection(self) -> CollectionResult:
        """
        収集処理を実行

        Returns:
            CollectionResult: 収集結果サマリー

        Preconditions: ロックファイルが存在しない（重複実行防止）
        Postconditions: 収集完了、スナップショット更新、出力ファイル生成
        Invariants: エラー発生時もログ記録とクリーンアップは実行
        """
        # 重複実行チェック
        if self._is_running():
            self.logger.warning("Collection already running, skipping...")
            return CollectionResult(
                success=False,
                errors=["Already running"]
            )

        self._acquire_lock()
        start_time = time.time()
        errors = []

        try:
            # ログ記録: 開始
            execution_id = self._generate_execution_id()
            self.logger.info(
                f"Starting collection for {self.adapter.municipality_name}",
                extra={
                    "prefecture_code": self.adapter.prefecture_code,
                    "execution_id": execution_id
                }
            )

            # 収集実行
            collected_data = self._collect_with_retry()

            # 差分検知
            diff_result = self.diff_detector.detect_diff(collected_data)

            # ページ構造変更検知時の通知
            if self._structure_changed:
                self.notification_client.send_alert(
                    NotificationLevel.CRITICAL,
                    "Page structure changed",
                    {"prefecture": self.adapter.municipality_name}
                )

            # 新規データ通知
            if diff_result.new:
                self.notification_client.notify_new_animals(diff_result.new)

            # 出力
            output_path = self.output_writer.write_output(collected_data, diff_result)

            # スナップショット保存
            self.snapshot_store.save_snapshot(collected_data)

            # ログ記録: 完了
            execution_time = time.time() - start_time
            self.logger.info(
                "Collection completed",
                extra={
                    "total_count": len(collected_data),
                    "new_count": len(diff_result.new),
                    "updated_count": len(diff_result.updated),
                    "deleted_count": len(diff_result.deleted_candidates),
                    "errors_count": len(errors),
                    "execution_time_seconds": execution_time
                }
            )

            return CollectionResult(
                success=True,
                total_collected=len(collected_data),
                new_count=len(diff_result.new),
                updated_count=len(diff_result.updated),
                deleted_count=len(diff_result.deleted_candidates),
                errors=errors,
                execution_time_seconds=execution_time
            )

        except ParsingError as e:
            # ページ構造変更検知
            self.logger.error(f"Parsing error (structure changed): {str(e)}", exc_info=True)
            self._structure_changed = True
            self.notification_client.send_alert(
                NotificationLevel.CRITICAL,
                "Page structure changed",
                {"prefecture": self.adapter.municipality_name, "error": str(e)}
            )
            errors.append(str(e))
            execution_time = time.time() - start_time
            return CollectionResult(
                success=False,
                errors=errors,
                execution_time_seconds=execution_time
            )

        except Exception as e:
            self.logger.error(f"Collection failed: {str(e)}", exc_info=True)
            errors.append(str(e))
            execution_time = time.time() - start_time
            return CollectionResult(
                success=False,
                errors=errors,
                execution_time_seconds=execution_time
            )

        finally:
            self._release_lock()

    def _collect_with_retry(self, max_retries: int = 3) -> List[AnimalData]:
        """
        リトライ付き収集

        Args:
            max_retries: 最大リトライ回数

        Returns:
            List[AnimalData]: 収集した動物データリスト

        Raises:
            NetworkError: ネットワークエラーが最大リトライ回数後も解決しない場合
            ParsingError: ページ構造が想定と異なる場合（リトライなし）
        """
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                # 一覧ページから個体詳細 URL リストを取得
                detail_urls = self.adapter.fetch_animal_list()

                # 各個体詳細ページから情報を抽出・正規化
                collected_data = []
                for url in detail_urls:
                    try:
                        raw_data = self.adapter.extract_animal_details(url)
                        normalized_data = self.adapter.normalize(raw_data)
                        collected_data.append(normalized_data)
                    except NetworkError as e:
                        # 個別ページのネットワークエラーはスキップ
                        self.logger.warning(
                            f"Failed to fetch detail page: {url}",
                            extra={"error": str(e)}
                        )
                    except Exception as e:
                        # その他のエラーもスキップ（ベストエフォート）
                        self.logger.warning(
                            f"Failed to process detail page: {url}",
                            extra={"error": str(e)}
                        )

                return collected_data

            except ParsingError as e:
                # ParsingError の場合はリトライせず即座にスロー
                self._structure_changed = True
                raise

            except NetworkError as e:
                retry_count += 1
                last_error = e
                if retry_count < max_retries:
                    # 指数バックオフ
                    sleep_time = 2 ** retry_count
                    self.logger.warning(
                        f"Network error, retrying in {sleep_time}s (attempt {retry_count}/{max_retries})",
                        extra={"error": str(e)}
                    )
                    time.sleep(sleep_time)
                else:
                    self.logger.error(
                        f"Max retries exceeded for network error",
                        extra={"error": str(e)}
                    )

        # 最大リトライ回数を超えた場合
        if last_error:
            raise last_error
        else:
            raise NetworkError("Failed to collect data after retries")

    def _is_running(self) -> bool:
        """
        ロックファイルの存在確認

        Returns:
            bool: ロックファイルが存在すれば True
        """
        return self.LOCK_FILE.exists()

    def _acquire_lock(self) -> None:
        """ロックファイル作成"""
        self.LOCK_FILE.touch()

    def _release_lock(self) -> None:
        """ロックファイル削除"""
        if self.LOCK_FILE.exists():
            self.LOCK_FILE.unlink()

    def _generate_execution_id(self) -> str:
        """
        実行 ID 生成（UUID）

        Returns:
            str: UUID 形式の実行 ID
        """
        return str(uuid.uuid4())
