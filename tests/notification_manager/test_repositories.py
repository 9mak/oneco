"""
notification-manager リポジトリ層のテスト

Task 3.1, 3.2, 3.3: UserRepository, PreferenceRepository, NotificationHistoryRepository のテスト
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.notification_manager.infrastructure.database.models import (
    NotificationBase,
    User,
    NotificationPreference,
    NotificationHistory,
)
from src.notification_manager.infrastructure.database.repository import (
    UserRepository,
    PreferenceRepository,
    NotificationHistoryRepository,
)
from src.notification_manager.domain.models import (
    UserEntity,
    NotificationPreferenceInput,
    NotificationPreferenceEntity,
)


@pytest.fixture
def sync_engine():
    """テスト用の同期SQLiteエンジン"""
    engine = create_engine("sqlite:///:memory:")
    NotificationBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(sync_engine):
    """テスト用のデータベースセッション"""
    with Session(sync_engine) as session:
        yield session


class TestUserRepository:
    """Task 3.1: ユーザーリポジトリのテスト"""

    def test_create_user(self, session):
        """ユーザーを作成できる"""
        repo = UserRepository(session)
        user = repo.create_user("encrypted_U1234567890")

        assert user.id is not None
        assert user.line_user_id_encrypted == "encrypted_U1234567890"
        assert user.is_active is True

    def test_get_user_by_encrypted_id(self, session):
        """暗号化LINEユーザーIDでユーザーを取得できる"""
        repo = UserRepository(session)
        created_user = repo.create_user("encrypted_test_user")

        found_user = repo.get_by_encrypted_line_id("encrypted_test_user")
        assert found_user is not None
        assert found_user.id == created_user.id

    def test_get_user_by_encrypted_id_not_found(self, session):
        """存在しない暗号化LINEユーザーIDはNoneを返す"""
        repo = UserRepository(session)
        found_user = repo.get_by_encrypted_line_id("nonexistent")
        assert found_user is None

    def test_get_or_create_user_existing(self, session):
        """既存ユーザーを取得または作成（既存の場合）"""
        repo = UserRepository(session)
        created_user = repo.create_user("encrypted_existing")

        result = repo.get_or_create("encrypted_existing")
        assert result.id == created_user.id

    def test_get_or_create_user_new(self, session):
        """既存ユーザーを取得または作成（新規の場合）"""
        repo = UserRepository(session)
        result = repo.get_or_create("encrypted_new_user")
        assert result.id is not None
        assert result.line_user_id_encrypted == "encrypted_new_user"

    def test_deactivate_user(self, session):
        """ユーザーを無効化できる"""
        repo = UserRepository(session)
        user = repo.create_user("encrypted_to_deactivate")

        result = repo.deactivate("encrypted_to_deactivate")
        assert result is True

        updated_user = repo.get_by_encrypted_line_id("encrypted_to_deactivate")
        assert updated_user.is_active is False

    def test_deactivate_nonexistent_user(self, session):
        """存在しないユーザーの無効化はFalseを返す"""
        repo = UserRepository(session)
        result = repo.deactivate("nonexistent")
        assert result is False

    def test_get_active_users(self, session):
        """アクティブユーザー一覧を取得できる"""
        repo = UserRepository(session)
        repo.create_user("encrypted_active1")
        repo.create_user("encrypted_active2")
        user3 = repo.create_user("encrypted_inactive")
        repo.deactivate("encrypted_inactive")

        active_users = repo.get_active_users()
        assert len(active_users) == 2
        assert all(u.is_active for u in active_users)


class TestPreferenceRepository:
    """Task 3.2: 通知条件リポジトリのテスト"""

    @pytest.fixture
    def user(self, session):
        """テスト用ユーザー"""
        user_repo = UserRepository(session)
        return user_repo.create_user("encrypted_pref_user")

    def test_create_preference(self, session, user):
        """通知条件を作成できる"""
        repo = PreferenceRepository(session)
        pref_input = NotificationPreferenceInput(
            species="犬",
            prefectures=["高知県", "愛媛県"],
            age_min_months=0,
            age_max_months=24,
            size="中型",
            sex="男の子",
        )
        pref = repo.create_or_update(user.id, pref_input)

        assert pref.id is not None
        assert pref.user_id == user.id
        assert pref.species == "犬"
        assert pref.prefectures == ["高知県", "愛媛県"]

    def test_update_preference(self, session, user):
        """通知条件を更新できる"""
        repo = PreferenceRepository(session)

        # 初回作成
        pref_input1 = NotificationPreferenceInput(species="犬")
        pref1 = repo.create_or_update(user.id, pref_input1)

        # 更新
        pref_input2 = NotificationPreferenceInput(species="猫", size="小型")
        pref2 = repo.create_or_update(user.id, pref_input2)

        assert pref1.id == pref2.id
        assert pref2.species == "猫"
        assert pref2.size == "小型"

    def test_get_preference_by_user_id(self, session, user):
        """ユーザーIDで通知条件を取得できる"""
        repo = PreferenceRepository(session)
        pref_input = NotificationPreferenceInput(species="猫")
        repo.create_or_update(user.id, pref_input)

        found_pref = repo.get_by_user_id(user.id)
        assert found_pref is not None
        assert found_pref.species == "猫"

    def test_get_preference_by_user_id_not_found(self, session, user):
        """存在しない通知条件はNoneを返す"""
        repo = PreferenceRepository(session)
        found_pref = repo.get_by_user_id(user.id)
        assert found_pref is None

    def test_toggle_notifications(self, session, user):
        """通知の有効/無効を切り替えできる"""
        repo = PreferenceRepository(session)
        pref_input = NotificationPreferenceInput(species="犬")
        repo.create_or_update(user.id, pref_input)

        # 無効化
        result = repo.set_notifications_enabled(user.id, False)
        assert result is True

        pref = repo.get_by_user_id(user.id)
        assert pref.notifications_enabled is False

        # 有効化
        result = repo.set_notifications_enabled(user.id, True)
        assert result is True

        pref = repo.get_by_user_id(user.id)
        assert pref.notifications_enabled is True

    def test_get_active_preferences(self, session):
        """アクティブな通知条件を一括取得できる"""
        user_repo = UserRepository(session)
        pref_repo = PreferenceRepository(session)

        # アクティブユーザー1
        user1 = user_repo.create_user("encrypted_user1")
        pref_repo.create_or_update(user1.id, NotificationPreferenceInput(species="犬"))

        # アクティブユーザー2
        user2 = user_repo.create_user("encrypted_user2")
        pref_repo.create_or_update(user2.id, NotificationPreferenceInput(species="猫"))

        # 無効化されたユーザー
        user3 = user_repo.create_user("encrypted_user3")
        pref_repo.create_or_update(user3.id, NotificationPreferenceInput(species="犬"))
        pref_repo.set_notifications_enabled(user3.id, False)

        active_prefs = pref_repo.get_active_preferences()
        assert len(active_prefs) == 2


class TestNotificationHistoryRepository:
    """Task 3.3: 通知履歴リポジトリのテスト"""

    @pytest.fixture
    def user(self, session):
        """テスト用ユーザー"""
        user_repo = UserRepository(session)
        return user_repo.create_user("encrypted_history_user")

    def test_record_history(self, session, user):
        """通知履歴を記録できる"""
        repo = NotificationHistoryRepository(session)
        history = repo.record(
            user_id=user.id,
            animal_source_url="https://example.com/animals/123",
            status="sent",
        )

        assert history.id is not None
        assert history.user_id == user.id
        assert history.animal_source_url == "https://example.com/animals/123"
        assert history.status == "sent"

    def test_check_already_notified_true(self, session, user):
        """既に通知済みの場合はTrueを返す"""
        repo = NotificationHistoryRepository(session)
        repo.record(
            user_id=user.id,
            animal_source_url="https://example.com/animals/123",
            status="sent",
        )

        result = repo.is_already_notified(user.id, "https://example.com/animals/123")
        assert result is True

    def test_check_already_notified_false(self, session, user):
        """未通知の場合はFalseを返す"""
        repo = NotificationHistoryRepository(session)
        result = repo.is_already_notified(user.id, "https://example.com/animals/456")
        assert result is False

    def test_delete_old_history(self, session, user):
        """古い履歴を削除できる"""
        repo = NotificationHistoryRepository(session)

        # 91日前の履歴（削除対象）
        old_history = NotificationHistory(
            user_id=user.id,
            animal_source_url="https://example.com/animals/old",
            status="sent",
            notified_at=datetime.now(timezone.utc) - timedelta(days=91),
        )
        session.add(old_history)
        session.commit()

        # 今日の履歴（削除対象外）
        repo.record(
            user_id=user.id,
            animal_source_url="https://example.com/animals/new",
            status="sent",
        )

        # 90日超過した履歴を削除
        deleted_count = repo.delete_older_than_days(90)
        assert deleted_count == 1

        # 新しい履歴は残っている
        assert repo.is_already_notified(user.id, "https://example.com/animals/new")
        # 古い履歴は削除されている
        assert not repo.is_already_notified(user.id, "https://example.com/animals/old")

    def test_get_history_for_user(self, session, user):
        """ユーザーの通知履歴を取得できる"""
        repo = NotificationHistoryRepository(session)
        repo.record(user.id, "https://example.com/animals/1", "sent")
        repo.record(user.id, "https://example.com/animals/2", "sent")
        repo.record(user.id, "https://example.com/animals/3", "failed")

        history = repo.get_history_for_user(user.id)
        assert len(history) == 3

        # ステータスで絞り込み
        sent_history = repo.get_history_for_user(user.id, status="sent")
        assert len(sent_history) == 2
