"""
notification-manager ドメインサービス

このモジュールはnotification-managerのドメインサービス層を提供します:
- UserService: ユーザー登録・条件管理
- MatchingService: 新着動物と条件のマッチング
- NotificationService: 通知配信オーケストレーション

Requirements: 1.1-1.7, 3.1-3.5, 4.1-4.6, 5.2, 5.3, 8.1-8.5
"""

import asyncio
import logging
import time
from typing import List, Optional, Protocol

from src.notification_manager.domain.models import (
    UserEntity,
    NotificationPreferenceInput,
    NotificationPreferenceEntity,
    MatchResult,
    NotificationMessage,
    SendResult,
    NotificationResult,
)
from src.data_collector.domain.models import AnimalData

logger = logging.getLogger(__name__)


class UserRepositoryProtocol(Protocol):
    """ユーザーリポジトリプロトコル"""

    def create_user(self, encrypted_line_user_id: str) -> UserEntity: ...
    def get_by_encrypted_line_id(self, encrypted_line_user_id: str) -> Optional[UserEntity]: ...
    def get_by_id(self, user_id: int) -> Optional[UserEntity]: ...
    def deactivate(self, encrypted_line_user_id: str) -> bool: ...
    def reactivate(self, encrypted_line_user_id: str) -> Optional[UserEntity]: ...
    def get_active_users(self) -> List[UserEntity]: ...


class PreferenceRepositoryProtocol(Protocol):
    """通知条件リポジトリプロトコル"""

    def create_or_update(
        self, user_id: int, pref_input: NotificationPreferenceInput
    ) -> NotificationPreferenceEntity: ...
    def get_by_user_id(self, user_id: int) -> Optional[NotificationPreferenceEntity]: ...
    def set_notifications_enabled(self, user_id: int, enabled: bool) -> bool: ...
    def get_active_preferences(self) -> List[NotificationPreferenceEntity]: ...


class NotificationHistoryRepositoryProtocol(Protocol):
    """通知履歴リポジトリプロトコル"""

    def record(self, user_id: int, animal_source_url: str, status: str): ...
    def is_already_notified(self, user_id: int, animal_source_url: str) -> bool: ...
    def delete_older_than_days(self, days: int) -> int: ...


class EncryptionServiceProtocol(Protocol):
    """暗号化サービスプロトコル"""

    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, ciphertext: str) -> str: ...


class LineAdapterProtocol(Protocol):
    """LINEアダプタープロトコル"""

    async def send_with_retry(
        self, line_user_id: str, notification: NotificationMessage, max_retries: int = 3
    ) -> SendResult: ...


class MatchingService:
    """
    マッチングサービス

    新着動物データとユーザー通知条件のマッチング評価を行う。

    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """

    def __init__(
        self,
        preference_repository: PreferenceRepositoryProtocol,
        user_repository: UserRepositoryProtocol,
    ):
        """
        MatchingService を初期化

        Args:
            preference_repository: 通知条件リポジトリ
            user_repository: ユーザーリポジトリ
        """
        self._preference_repository = preference_repository
        self._user_repository = user_repository

    def find_matching_users(self, animal: AnimalData) -> List[MatchResult]:
        """
        動物データに対してマッチするユーザーを検索

        Args:
            animal: 動物データ

        Returns:
            List[MatchResult]: マッチしたユーザーのリスト
        """
        results = []
        active_preferences = self._preference_repository.get_active_preferences()

        for pref in active_preferences:
            if self._matches(animal, pref):
                user = self._user_repository.get_by_id(pref.user_id)
                if user and user.is_active:
                    results.append(
                        MatchResult(
                            user_id=pref.user_id,
                            line_user_id_encrypted=user.line_user_id_encrypted,
                            preference_id=pref.id,
                            match_score=1.0,
                        )
                    )
                    logger.debug(
                        f"Match found: user_id={pref.user_id}, "
                        f"animal={animal.source_url}"
                    )

        logger.info(
            f"Matching completed: {len(results)} matches for animal {animal.source_url}"
        )
        return results

    def _matches(self, animal: AnimalData, pref: NotificationPreferenceEntity) -> bool:
        """
        動物データと通知条件のマッチング評価

        すべての条件がAND条件で評価される。
        条件が未設定（None）の場合は「すべて許可」として扱う。
        早期リターンで効率化。

        Args:
            animal: 動物データ
            pref: 通知条件

        Returns:
            bool: マッチする場合はTrue
        """
        # 種別チェック
        if pref.species is not None:
            if animal.species != pref.species:
                return False

        # 都道府県チェック
        if pref.prefectures is not None and len(pref.prefectures) > 0:
            if not self._location_matches(animal.location, pref.prefectures):
                return False

        # 年齢チェック（動物の年齢が不明な場合は、年齢条件がなければマッチ）
        if pref.age_min_months is not None or pref.age_max_months is not None:
            if animal.age_months is None:
                return False
            if pref.age_min_months is not None and animal.age_months < pref.age_min_months:
                return False
            if pref.age_max_months is not None and animal.age_months > pref.age_max_months:
                return False

        # サイズチェック
        if pref.size is not None:
            if animal.size != pref.size:
                return False

        # 性別チェック
        if pref.sex is not None:
            if animal.sex != pref.sex:
                return False

        return True

    def _location_matches(self, location: str, prefectures: List[str]) -> bool:
        """
        収容場所が指定都道府県のいずれかに含まれるかチェック

        Args:
            location: 収容場所文字列
            prefectures: 都道府県リスト

        Returns:
            bool: いずれかの都道府県を含む場合はTrue
        """
        for prefecture in prefectures:
            if prefecture in location:
                return True
        return False


class UserService:
    """
    ユーザーサービス

    LINEユーザーの登録、通知条件の管理、対話フローの制御を行う。

    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 7.5
    """

    def __init__(
        self,
        user_repository: UserRepositoryProtocol,
        preference_repository: PreferenceRepositoryProtocol,
        encryption_service: EncryptionServiceProtocol,
    ):
        """
        UserService を初期化

        Args:
            user_repository: ユーザーリポジトリ
            preference_repository: 通知条件リポジトリ
            encryption_service: 暗号化サービス
        """
        self._user_repository = user_repository
        self._pref_repository = preference_repository
        self._encryption_service = encryption_service

    def register_user(self, line_user_id: str) -> UserEntity:
        """
        新規ユーザーを登録（友だち追加時）

        既に登録済みの場合は再アクティブ化する。

        Args:
            line_user_id: LINEユーザーID

        Returns:
            UserEntity: 登録されたユーザー
        """
        encrypted_id = self._encryption_service.encrypt(line_user_id)
        existing = self._user_repository.get_by_encrypted_line_id(encrypted_id)

        if existing:
            if not existing.is_active:
                logger.info(f"Reactivating user: {line_user_id[:8]}...")
                return self._user_repository.reactivate(encrypted_id)
            return existing

        logger.info(f"Registering new user: {line_user_id[:8]}...")
        return self._user_repository.create_user(encrypted_id)

    def update_preferences(
        self, user_id: int, preferences: NotificationPreferenceInput
    ) -> NotificationPreferenceEntity:
        """
        通知条件を更新

        Args:
            user_id: ユーザーID
            preferences: 通知条件入力

        Returns:
            NotificationPreferenceEntity: 更新された通知条件
        """
        logger.info(f"Updating preferences for user_id={user_id}")
        return self._pref_repository.create_or_update(user_id, preferences)

    def get_preferences(self, user_id: int) -> Optional[NotificationPreferenceEntity]:
        """
        通知条件を取得

        Args:
            user_id: ユーザーID

        Returns:
            Optional[NotificationPreferenceEntity]: 通知条件、存在しない場合はNone
        """
        return self._pref_repository.get_by_user_id(user_id)

    def deactivate_user(self, line_user_id: str) -> bool:
        """
        ユーザーを無効化（ブロック/削除時）

        Args:
            line_user_id: LINEユーザーID

        Returns:
            bool: 無効化成功時はTrue
        """
        encrypted_id = self._encryption_service.encrypt(line_user_id)
        logger.info(f"Deactivating user: {line_user_id[:8]}...")
        return self._user_repository.deactivate(encrypted_id)

    def toggle_notifications(self, user_id: int, enabled: bool) -> bool:
        """
        通知の有効/無効を切り替え

        Args:
            user_id: ユーザーID
            enabled: 有効フラグ

        Returns:
            bool: 設定成功時はTrue
        """
        logger.info(f"Toggling notifications for user_id={user_id}: enabled={enabled}")
        return self._pref_repository.set_notifications_enabled(user_id, enabled)


class NotificationService:
    """
    通知サービス

    通知配信プロセス全体のオーケストレーションを行う。

    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.2, 5.3, 8.1, 8.2, 8.3, 8.4, 8.5
    """

    # バッチサイズと並列数
    BATCH_SIZE = 100
    MAX_PARALLEL = 10

    def __init__(
        self,
        matching_service: MatchingService,
        history_repository: NotificationHistoryRepositoryProtocol,
        line_adapter: LineAdapterProtocol,
        encryption_service: EncryptionServiceProtocol,
    ):
        """
        NotificationService を初期化

        Args:
            matching_service: マッチングサービス
            history_repository: 通知履歴リポジトリ
            line_adapter: LINEアダプター
            encryption_service: 暗号化サービス
        """
        self._matching_service = matching_service
        self._history_repository = history_repository
        self._line_adapter = line_adapter
        self._encryption_service = encryption_service

    async def process_new_animals(
        self, animals: List[AnimalData]
    ) -> NotificationResult:
        """
        新着動物の通知処理を実行

        Args:
            animals: 動物データのリスト

        Returns:
            NotificationResult: 処理結果
        """
        start_time = time.time()

        total_matches = 0
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        for animal in animals:
            matches = self._matching_service.find_matching_users(animal)
            total_matches += len(matches)

            # バッチ処理
            for i in range(0, len(matches), self.BATCH_SIZE):
                batch = matches[i:i + self.BATCH_SIZE]
                tasks = []

                for match in batch:
                    # 重複チェック
                    if self._history_repository.is_already_notified(
                        match.user_id, str(animal.source_url)
                    ):
                        skipped_count += 1
                        logger.debug(
                            f"Skipping duplicate notification: "
                            f"user_id={match.user_id}, url={animal.source_url}"
                        )
                        continue

                    tasks.append(self._send_notification(animal, match))

                if tasks:
                    # 並列送信（最大10並列）
                    results = await self._run_parallel(tasks)
                    for result, match in zip(results, batch):
                        if isinstance(result, Exception):
                            failed_count += 1
                            self._record_history(
                                match.user_id, str(animal.source_url), "failed"
                            )
                        elif result.success:
                            sent_count += 1
                            self._record_history(
                                match.user_id, str(animal.source_url), "sent"
                            )
                        else:
                            failed_count += 1
                            self._record_history(
                                match.user_id, str(animal.source_url), "failed"
                            )

        processing_time = time.time() - start_time

        result = NotificationResult(
            total_animals=len(animals),
            total_matches=total_matches,
            sent_count=sent_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            processing_time_seconds=processing_time,
        )

        logger.info(
            f"Notification processing completed: "
            f"animals={result.total_animals}, matches={result.total_matches}, "
            f"sent={result.sent_count}, skipped={result.skipped_count}, "
            f"failed={result.failed_count}, time={result.processing_time_seconds:.2f}s"
        )

        return result

    async def _send_notification(
        self, animal: AnimalData, match: MatchResult
    ) -> SendResult:
        """
        個別通知を送信

        Args:
            animal: 動物データ
            match: マッチング結果

        Returns:
            SendResult: 送信結果
        """
        line_user_id = self._encryption_service.decrypt(match.line_user_id_encrypted)

        message = NotificationMessage(
            species=animal.species,
            sex=animal.sex,
            age_months=animal.age_months,
            size=animal.size,
            location=animal.location,
            source_url=str(animal.source_url),
            category=animal.category,
        )

        return await self._line_adapter.send_with_retry(line_user_id, message)

    async def _run_parallel(self, tasks: list, max_parallel: int = None) -> list:
        """
        タスクを並列実行

        Args:
            tasks: 実行するタスクのリスト
            max_parallel: 最大並列数

        Returns:
            list: 結果のリスト
        """
        if max_parallel is None:
            max_parallel = self.MAX_PARALLEL

        semaphore = asyncio.Semaphore(max_parallel)

        async def limited_task(task):
            async with semaphore:
                return await task

        return await asyncio.gather(
            *[limited_task(t) for t in tasks],
            return_exceptions=True,
        )

    def _record_history(self, user_id: int, animal_source_url: str, status: str):
        """
        通知履歴を記録

        Args:
            user_id: ユーザーID
            animal_source_url: 動物ソースURL
            status: ステータス
        """
        try:
            self._history_repository.record(
                user_id=user_id,
                animal_source_url=animal_source_url,
                status=status,
            )
        except Exception as e:
            logger.error(f"Failed to record notification history: {e}")
