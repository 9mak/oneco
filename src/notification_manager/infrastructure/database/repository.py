"""
notification-manager リポジトリ層

このモジュールはnotification-managerのデータアクセス層を提供します。
Repository パターンによりドメイン層とデータベース層を分離。

Requirements: 1.1, 1.4, 1.6, 3.1, 5.1, 5.2, 5.3, 5.4, 5.5, 7.5
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.notification_manager.domain.models import (
    NotificationPreferenceEntity,
    NotificationPreferenceInput,
    UserEntity,
)
from src.notification_manager.infrastructure.database.models import (
    NotificationHistory,
    NotificationPreference,
    User,
)


class UserRepository:
    """
    ユーザーリポジトリ

    LINEユーザーの登録、検索、無効化を担当。

    Requirements: 1.1, 1.4, 1.6, 7.5
    """

    def __init__(self, session: Session):
        """
        UserRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    def create_user(self, encrypted_line_user_id: str) -> UserEntity:
        """
        新規ユーザーを作成

        Args:
            encrypted_line_user_id: 暗号化されたLINEユーザーID

        Returns:
            UserEntity: 作成されたユーザー
        """
        user = User(
            line_user_id_encrypted=encrypted_line_user_id,
            is_active=True,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return self._to_entity(user)

    def get_by_encrypted_line_id(self, encrypted_line_user_id: str) -> UserEntity | None:
        """
        暗号化LINEユーザーIDでユーザーを取得

        Args:
            encrypted_line_user_id: 暗号化されたLINEユーザーID

        Returns:
            Optional[UserEntity]: ユーザー、存在しない場合はNone
        """
        stmt = select(User).where(User.line_user_id_encrypted == encrypted_line_user_id)
        result = self.session.execute(stmt)
        user = result.scalar_one_or_none()
        return self._to_entity(user) if user else None

    def get_or_create(self, encrypted_line_user_id: str) -> UserEntity:
        """
        ユーザーを取得、存在しない場合は作成

        Args:
            encrypted_line_user_id: 暗号化されたLINEユーザーID

        Returns:
            UserEntity: ユーザー
        """
        existing = self.get_by_encrypted_line_id(encrypted_line_user_id)
        if existing:
            return existing
        return self.create_user(encrypted_line_user_id)

    def deactivate(self, encrypted_line_user_id: str) -> bool:
        """
        ユーザーを無効化（ブロック/削除時）

        Args:
            encrypted_line_user_id: 暗号化されたLINEユーザーID

        Returns:
            bool: 無効化成功時はTrue、ユーザーが存在しない場合はFalse
        """
        stmt = select(User).where(User.line_user_id_encrypted == encrypted_line_user_id)
        result = self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return False

        user.is_active = False
        user.updated_at = datetime.now(UTC)
        self.session.commit()
        return True

    def get_by_id(self, user_id: int) -> UserEntity | None:
        """
        ユーザーIDでユーザーを取得

        Args:
            user_id: ユーザーID

        Returns:
            Optional[UserEntity]: ユーザー、存在しない場合はNone
        """
        stmt = select(User).where(User.id == user_id)
        result = self.session.execute(stmt)
        user = result.scalar_one_or_none()
        return self._to_entity(user) if user else None

    def reactivate(self, encrypted_line_user_id: str) -> UserEntity | None:
        """
        ユーザーを再アクティブ化

        Args:
            encrypted_line_user_id: 暗号化されたLINEユーザーID

        Returns:
            Optional[UserEntity]: 再アクティブ化されたユーザー、存在しない場合はNone
        """
        stmt = select(User).where(User.line_user_id_encrypted == encrypted_line_user_id)
        result = self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        user.is_active = True
        user.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(user)
        return self._to_entity(user)

    def get_active_users(self) -> list[UserEntity]:
        """
        アクティブなユーザー一覧を取得

        Returns:
            List[UserEntity]: アクティブユーザーのリスト
        """
        stmt = select(User).where(User.is_active)
        result = self.session.execute(stmt)
        users = result.scalars().all()
        return [self._to_entity(u) for u in users]

    def _to_entity(self, user: User) -> UserEntity:
        """ORMモデルをエンティティに変換"""
        return UserEntity(
            id=user.id,
            line_user_id_encrypted=user.line_user_id_encrypted,
            is_active=user.is_active,
        )


class PreferenceRepository:
    """
    通知条件リポジトリ

    ユーザー通知条件のCRUD操作を担当。

    Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 3.1
    """

    def __init__(self, session: Session):
        """
        PreferenceRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    def create_or_update(
        self, user_id: int, pref_input: NotificationPreferenceInput
    ) -> NotificationPreferenceEntity:
        """
        通知条件を作成または更新

        Args:
            user_id: ユーザーID
            pref_input: 通知条件入力

        Returns:
            NotificationPreferenceEntity: 作成/更新された通知条件
        """
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # 更新
            existing.species = pref_input.species
            existing.prefectures = pref_input.prefectures
            existing.age_min_months = pref_input.age_min_months
            existing.age_max_months = pref_input.age_max_months
            existing.size = pref_input.size
            existing.sex = pref_input.sex
            existing.updated_at = datetime.now(UTC)
            pref = existing
        else:
            # 新規作成
            pref = NotificationPreference(
                user_id=user_id,
                species=pref_input.species,
                prefectures=pref_input.prefectures,
                age_min_months=pref_input.age_min_months,
                age_max_months=pref_input.age_max_months,
                size=pref_input.size,
                sex=pref_input.sex,
                notifications_enabled=True,
            )
            self.session.add(pref)

        self.session.commit()
        self.session.refresh(pref)
        return self._to_entity(pref)

    def get_by_user_id(self, user_id: int) -> NotificationPreferenceEntity | None:
        """
        ユーザーIDで通知条件を取得

        Args:
            user_id: ユーザーID

        Returns:
            Optional[NotificationPreferenceEntity]: 通知条件、存在しない場合はNone
        """
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = self.session.execute(stmt)
        pref = result.scalar_one_or_none()
        return self._to_entity(pref) if pref else None

    def set_notifications_enabled(self, user_id: int, enabled: bool) -> bool:
        """
        通知の有効/無効を設定

        Args:
            user_id: ユーザーID
            enabled: 有効フラグ

        Returns:
            bool: 設定成功時はTrue、条件が存在しない場合はFalse
        """
        stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        result = self.session.execute(stmt)
        pref = result.scalar_one_or_none()

        if not pref:
            return False

        pref.notifications_enabled = enabled
        pref.updated_at = datetime.now(UTC)
        self.session.commit()
        return True

    def get_active_preferences(self) -> list[NotificationPreferenceEntity]:
        """
        アクティブな通知条件を一括取得（マッチング用）

        Returns:
            List[NotificationPreferenceEntity]: 有効な通知条件のリスト
        """
        stmt = (
            select(NotificationPreference)
            .join(User)
            .where(
                NotificationPreference.notifications_enabled,
                User.is_active,
            )
        )
        result = self.session.execute(stmt)
        prefs = result.scalars().all()
        return [self._to_entity(p) for p in prefs]

    def _to_entity(self, pref: NotificationPreference) -> NotificationPreferenceEntity:
        """ORMモデルをエンティティに変換"""
        return NotificationPreferenceEntity(
            id=pref.id,
            user_id=pref.user_id,
            species=pref.species,
            prefectures=pref.prefectures,
            age_min_months=pref.age_min_months,
            age_max_months=pref.age_max_months,
            size=pref.size,
            sex=pref.sex,
            notifications_enabled=pref.notifications_enabled,
        )


class NotificationHistoryRepository:
    """
    通知履歴リポジトリ

    通知履歴の記録、重複チェック、古い履歴の削除を担当。

    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """

    def __init__(self, session: Session):
        """
        NotificationHistoryRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    def record(self, user_id: int, animal_source_url: str, status: str) -> NotificationHistory:
        """
        通知履歴を記録

        Args:
            user_id: ユーザーID
            animal_source_url: 動物ソースURL
            status: 送信ステータス ('sent', 'failed', 'skipped')

        Returns:
            NotificationHistory: 記録された履歴
        """
        history = NotificationHistory(
            user_id=user_id,
            animal_source_url=animal_source_url,
            status=status,
        )
        self.session.add(history)
        self.session.commit()
        self.session.refresh(history)
        return history

    def is_already_notified(self, user_id: int, animal_source_url: str) -> bool:
        """
        既に通知済みかどうかを確認

        Args:
            user_id: ユーザーID
            animal_source_url: 動物ソースURL

        Returns:
            bool: 既に通知済みの場合はTrue
        """
        stmt = select(NotificationHistory).where(
            NotificationHistory.user_id == user_id,
            NotificationHistory.animal_source_url == animal_source_url,
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    def delete_older_than_days(self, days: int) -> int:
        """
        指定日数より古い履歴を削除

        Args:
            days: 保持日数

        Returns:
            int: 削除した履歴の件数
        """
        cutoff_date = datetime.now(UTC) - timedelta(days=days)
        stmt = delete(NotificationHistory).where(NotificationHistory.notified_at < cutoff_date)
        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount

    def get_history_for_user(
        self, user_id: int, status: str | None = None, limit: int = 100
    ) -> list[NotificationHistory]:
        """
        ユーザーの通知履歴を取得

        Args:
            user_id: ユーザーID
            status: ステータスで絞り込み（オプション）
            limit: 最大取得件数

        Returns:
            List[NotificationHistory]: 通知履歴のリスト
        """
        stmt = select(NotificationHistory).where(NotificationHistory.user_id == user_id)
        if status:
            stmt = stmt.where(NotificationHistory.status == status)
        stmt = stmt.order_by(NotificationHistory.notified_at.desc()).limit(limit)

        result = self.session.execute(stmt)
        return list(result.scalars().all())
