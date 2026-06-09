"""収集オーケストレーションサービス"""

import asyncio
import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

from ..adapters.municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError
from ..domain.diff_detector import DiffDetector
from ..domain.models import AnimalData
from ..infrastructure.notification_client import NotificationClient, NotificationLevel
from ..infrastructure.notification_manager_client import NotificationManagerClient
from ..infrastructure.output_writer import OutputWriter
from ..infrastructure.snapshot_store import SnapshotStore
from .soft_deadline import SoftDeadline

if TYPE_CHECKING:
    from ..infrastructure.database.connection import DatabaseConnection
    from ..infrastructure.database.repository import AnimalRepository


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
    errors: list[str] = []
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

    # 既定の lock file パス (後方互換: 旧テストはクラス変数を直接上書きする)。
    # 並列実行時は __init__ で adapter.municipality_name を含む path に
    # インスタンス上書きされるため、サイト間で衝突しない。
    LOCK_FILE = Path(".collector.lock")

    def __init__(
        self,
        adapter: MunicipalityAdapter,
        diff_detector: DiffDetector,
        output_writer: OutputWriter,
        notification_client: NotificationClient,
        snapshot_store: SnapshotStore,
        repository: Optional["AnimalRepository"] = None,
        db_connection: Optional["DatabaseConnection"] = None,
        notification_manager_client: NotificationManagerClient | None = None,
    ):
        self.adapter = adapter
        self.diff_detector = diff_detector
        self.output_writer = output_writer
        self.notification_client = notification_client
        self.snapshot_store = snapshot_store
        self.repository = repository
        self.db_connection = db_connection
        self.notification_manager_client = notification_manager_client
        self.logger = logging.getLogger(__name__)
        self._structure_changed = False
        # 収集が「サイト全件を失敗なく列挙できた」かどうか。soft-stop や detail 抽出
        # 失敗で部分取得になった run では prune_disappeared をスキップする
        # （部分集合で消滅判定すると、まだ実在する個体を誤って削除してしまうため）。
        self._collection_complete = True
        # 並列収集 (parallel_runner) でサイト間の lock 衝突を避けるため、
        # adapter.municipality_name のハッシュでユニーク化したインスタンス
        # lock を持つ。日本語名同士でも衝突せず、ファイル名として安全。
        # 既存テストは __init__ 後に `service.LOCK_FILE = ...` でインスタンス
        # 属性を上書きするので、そちらが優先される (後方互換)。
        site_hash = hashlib.sha1(
            str(adapter.municipality_name or "site").encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()[:12]
        self.LOCK_FILE = Path(f".collector.{site_hash}.lock")

    def run_collection(self, soft_deadline: SoftDeadline | None = None) -> CollectionResult:
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
            return CollectionResult(success=False, errors=["Already running"])

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
                    "execution_id": execution_id,
                },
            )

            # 収集実行
            collected_data = self._collect_with_retry(soft_deadline=soft_deadline)

            # 差分検知
            diff_result = self.diff_detector.detect_diff(collected_data)

            # ページ構造変更検知時の通知
            if self._structure_changed:
                self.notification_client.send_alert(
                    NotificationLevel.CRITICAL,
                    "Page structure changed",
                    {"prefecture": self.adapter.municipality_name},
                )

            # 新規データ通知（運用者向け Slack）
            if diff_result.new:
                self.notification_client.notify_new_animals(diff_result.new)

            # notification-manager への通知（ユーザー向け LINE）
            if diff_result.new and self.notification_manager_client:
                self.notification_manager_client.notify_new_animals_sync(diff_result.new)

            # データベース永続化
            if self.db_connection or self.repository:
                self._save_to_database(collected_data)

            # 出力
            self.output_writer.write_output(collected_data, diff_result)

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
                    "execution_time_seconds": execution_time,
                },
            )

            return CollectionResult(
                success=True,
                total_collected=len(collected_data),
                new_count=len(diff_result.new),
                updated_count=len(diff_result.updated),
                deleted_count=len(diff_result.deleted_candidates),
                errors=errors,
                execution_time_seconds=execution_time,
            )

        except ParsingError as e:
            # ページ構造変更検知
            self.logger.error(f"Parsing error (structure changed): {e!s}", exc_info=True)
            self._structure_changed = True
            self.notification_client.send_alert(
                NotificationLevel.CRITICAL,
                "Page structure changed",
                {"prefecture": self.adapter.municipality_name, "error": str(e)},
            )
            errors.append(str(e))
            execution_time = time.time() - start_time
            return CollectionResult(
                success=False, errors=errors, execution_time_seconds=execution_time
            )

        except Exception as e:
            self.logger.error(f"Collection failed: {e!s}", exc_info=True)
            errors.append(str(e))
            execution_time = time.time() - start_time
            return CollectionResult(
                success=False, errors=errors, execution_time_seconds=execution_time
            )

        finally:
            self._release_lock()

    def _collect_with_retry(
        self,
        max_retries: int = 3,
        soft_deadline: SoftDeadline | None = None,
    ) -> list[AnimalData]:
        """
        リトライ付き収集

        SnapshotStore に前回の AnimalData が保存されている場合、
        既知 source_url については LLM 抽出をスキップして前回データを再利用する
        （Groq の無料枠を 2 日目以降節約するため）。

        Args:
            max_retries: 最大リトライ回数
            soft_deadline: ハード timeout の手前で early-return するための協調
                キャンセル。detail ループ内で should_soft_stop を見て、True に
                なったら既収集分を返す (= タイムアウト全件破棄を防ぐ部分保存)。

        Returns:
            List[AnimalData]: 収集した動物データリスト

        Raises:
            NetworkError: ネットワークエラーが最大リトライ回数後も解決しない場合
            ParsingError: ページ構造が想定と異なる場合（リトライなし）
        """
        retry_count = 0
        last_error = None

        # 前回 snapshot を読み込み: 既知 URL は LLM スキップ対象
        known_animals = self.snapshot_store.load_animal_map()

        while retry_count < max_retries:
            try:
                # 一覧ページから個体詳細 URL リストとカテゴリを取得
                detail_url_category_pairs = self.adapter.fetch_animal_list()

                # 各個体詳細ページから情報を抽出・正規化
                collected_data = []
                skipped = 0
                soft_stopped_at: int | None = None
                detail_failures = 0
                for idx, (url, category) in enumerate(detail_url_category_pairs):
                    # ソフトデッドラインチェック: detail ループは politeness throttle で
                    # 件数に比例して時間が伸びる。ハード timeout 直前で残り detail を
                    # 諦めて既収集分を返す = 全件破棄を回避する部分保存フォールバック。
                    if soft_deadline is not None and soft_deadline.should_soft_stop():
                        soft_stopped_at = idx
                        break
                    # 既知 URL は LLM スキップ → 前回 AnimalData を再利用
                    if url in known_animals:
                        collected_data.append(known_animals[url])
                        skipped += 1
                        continue
                    try:
                        raw_data = self.adapter.extract_animal_details(url, category)
                        normalized_data = self.adapter.normalize(raw_data)
                        collected_data.append(normalized_data)
                    except NetworkError as e:
                        # 個別ページのネットワークエラーはスキップ。URL はサイト上に実在
                        # するが collected_data に入らないため、prune 不可の部分取得とみなす。
                        detail_failures += 1
                        self.logger.warning(
                            f"Failed to fetch detail page: {url} (category: {category})",
                            extra={"error": str(e)},
                        )
                    except Exception as e:
                        # その他のエラーもスキップ（ベストエフォート）。同上、部分取得扱い。
                        detail_failures += 1
                        self.logger.warning(
                            f"Failed to process detail page: {url} (category: {category})",
                            extra={"error": str(e)},
                        )

                if soft_stopped_at is not None:
                    self.logger.warning(
                        "Soft deadline reached during detail loop: "
                        f"processed {soft_stopped_at}/{len(detail_url_category_pairs)} URLs, "
                        f"returning {len(collected_data)} animals (partial save fallback)",
                        extra={
                            "soft_stopped_at": soft_stopped_at,
                            "total_urls": len(detail_url_category_pairs),
                            "collected": len(collected_data),
                        },
                    )

                if skipped > 0:
                    extracted = len(collected_data) - skipped
                    self.logger.info(
                        f"LLM extraction skipped (snapshot reuse): "
                        f"skipped {skipped}, extracted {extracted}",
                        extra={"skipped": skipped, "extracted": extracted},
                    )

                # この run がサイト全件を失敗なく列挙できたか。soft-stop でも detail
                # 失敗でも無い場合のみ「完全」とし、prune_disappeared を許可する。
                self._collection_complete = soft_stopped_at is None and detail_failures == 0

                return collected_data

            except ParsingError:
                # ParsingError の場合はリトライせず即座にスロー
                self._structure_changed = True
                raise

            except NetworkError as e:
                retry_count += 1
                last_error = e
                if retry_count < max_retries:
                    # 指数バックオフ
                    sleep_time = 2**retry_count
                    self.logger.warning(
                        f"Network error, retrying in {sleep_time}s (attempt {retry_count}/{max_retries})",
                        extra={"error": str(e)},
                    )
                    time.sleep(sleep_time)
                else:
                    self.logger.error(
                        "Max retries exceeded for network error", extra={"error": str(e)}
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

    def _save_to_database(self, collected_data: list[AnimalData]) -> None:
        """
        収集データをデータベースに永続化

        db_connection が設定されている場合はセッションを作成して保存（本番用）。
        repository が設定されている場合はそれを使って保存（テスト用）。
        """
        if self.db_connection:
            self._save_via_db_connection(collected_data)
        elif self.repository:
            self._save_via_repository(collected_data)

    def _save_via_db_connection(self, collected_data: list[AnimalData]) -> None:
        """db_connection からセッションを作成して一括保存"""
        from ..infrastructure.database.connection import DatabaseConnection
        from ..infrastructure.database.repository import AnimalRepository
        from ..infrastructure.url_hash_recorder import URLHashRecorder

        # サイト毎に _save_via_db_connection が呼ばれ、その度に asyncio.run() が
        # 新しいイベントループを生成する。SQLAlchemy async engine は最初のループに
        # 紐付いた接続を保持してしまうため、2 回目以降に asyncpg が
        # "another operation is in progress" を返してほぼ全件の save が失敗する。
        # サイト毎にエンジンを使い捨てることで、各 asyncio.run() が独立した接続を
        # 持つようにする。
        assert self.db_connection is not None
        settings = self.db_connection.settings

        async def _do_save() -> tuple[int, int]:
            saved = 0
            errors = 0
            db = DatabaseConnection(settings=settings)
            try:
                async with db.get_session() as session:
                    repo = AnimalRepository(session)
                    url_recorder = URLHashRecorder(session)
                    site_name = self.adapter.municipality_name
                    for animal in collected_data:
                        try:
                            await repo.save_animal(animal, source_site=site_name)
                            saved += 1
                        except Exception as e:
                            errors += 1
                            self.logger.warning(
                                f"Failed to save animal to database: {animal.source_url}: {e}",
                            )
                            continue
                        # Phase 1 MVP: 画像URLのSHA-256を image_hashes に記録（重複検出の足場）。
                        # AnimalData.image_urls は HttpUrl を含むため str に正規化する。
                        # 失敗してもメイン保存処理は継続する。
                        try:
                            await url_recorder.record_urls([str(u) for u in animal.image_urls])
                        except Exception as e:
                            self.logger.warning(
                                f"Failed to record image URL hashes for {animal.source_url}: {e}",
                            )

                    # ソースから消えた動物を同期削除する（このサイトで今回見つからなかった
                    # = もういない）。0 件時は prune_disappeared 側で無効化（全消し防止）。
                    # ただし soft-stop / detail 失敗で部分取得になった run では、未取得の
                    # 実在個体を誤削除する恐れがあるため prune をスキップする。
                    if not self._collection_complete:
                        self.logger.info(
                            f"[{site_name}] 部分取得のため消滅同期削除(prune)をスキップ"
                        )
                    else:
                        try:
                            seen_urls = {str(a.source_url) for a in collected_data}
                            removed = await repo.prune_disappeared(site_name, seen_urls)
                            if removed:
                                self.logger.info(
                                    f"[{site_name}] ソースから消えた {removed} 件を削除（同期）"
                                )
                        except Exception as e:
                            self.logger.warning(f"[{site_name}] 消滅同期削除に失敗: {e}")
            finally:
                await db.close()
            return saved, errors

        saved_count, error_count = asyncio.run(_do_save())
        self._log_db_result(saved_count, error_count, len(collected_data))

    def _save_via_repository(self, collected_data: list[AnimalData]) -> None:
        """既存の repository を使って保存（テスト用途）"""
        import concurrent.futures

        saved_count = 0
        error_count = 0

        # 実行中ループの有無はこの同期メソッド内で変化しないので一度だけ判定する。
        # asyncio.get_event_loop() は current loop 未設定時に RuntimeError を
        # 投げるため使わない（pytest-asyncio 1.4+ / Python 3.12+ で顕在化）。
        try:
            asyncio.get_running_loop()
            loop_running = True
        except RuntimeError:
            loop_running = False

        for animal in collected_data:
            try:
                if loop_running:
                    # 既にイベントループ実行中 → 別スレッドで新ループを回す。
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.repository.save_animal(animal),  # type: ignore[union-attr]
                        )
                        future.result()
                else:
                    # 通常の同期コンテキスト → current loop の有無に依存しない asyncio.run。
                    asyncio.run(self.repository.save_animal(animal))  # type: ignore[union-attr]
                saved_count += 1
            except Exception as e:
                error_count += 1
                self.logger.warning(
                    f"Failed to save animal to database: {animal.source_url}",
                    extra={"error": str(e)},
                )

        self._log_db_result(saved_count, error_count, len(collected_data))

    def _log_db_result(self, saved_count: int, error_count: int, total: int) -> None:
        self.logger.info(
            "Database persistence completed",
            extra={"saved_count": saved_count, "error_count": error_count},
        )
        if error_count > 0 and error_count >= total / 2:
            self.notification_client.send_alert(
                NotificationLevel.WARNING,
                "Database persistence errors",
                {
                    "prefecture": self.adapter.municipality_name,
                    "saved_count": saved_count,
                    "error_count": error_count,
                },
            )
