"""
notification-manager データベースモデルのテスト

Task 1.1, 1.2, 1.3: Users, NotificationPreferences, NotificationHistory テーブルのテスト
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.notification_manager.infrastructure.database.models import (
    NotificationBase,
    NotificationHistory,
    NotificationPreference,
    User,
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


class TestUserModel:
    """Task 1.1: ユーザー管理テーブルのテスト"""

    def test_create_user(self, session):
        """ユーザーを作成できる"""
        user = User(
            line_user_id_encrypted="encrypted_U1234567890abcdef",
            is_active=True,
        )
        session.add(user)
        session.commit()

        assert user.id is not None
        assert user.line_user_id_encrypted == "encrypted_U1234567890abcdef"
        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None

    def test_user_line_user_id_encrypted_unique(self, session):
        """line_user_id_encrypted はユニーク制約がある"""
        user1 = User(line_user_id_encrypted="encrypted_same_id")
        session.add(user1)
        session.commit()

        user2 = User(line_user_id_encrypted="encrypted_same_id")
        session.add(user2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_user_line_user_id_encrypted_length(self, session):
        """暗号化フィールドは255文字まで格納可能"""
        long_encrypted_id = "a" * 255
        user = User(line_user_id_encrypted=long_encrypted_id)
        session.add(user)
        session.commit()

        assert user.line_user_id_encrypted == long_encrypted_id

    def test_user_default_is_active(self, session):
        """is_active のデフォルト値は True"""
        user = User(line_user_id_encrypted="encrypted_test")
        session.add(user)
        session.commit()

        assert user.is_active is True

    def test_user_timestamps_auto_set(self, session):
        """created_at と updated_at は自動設定される"""
        datetime.now(UTC)
        user = User(line_user_id_encrypted="encrypted_timestamp_test")
        session.add(user)
        session.commit()
        datetime.now(UTC)

        assert user.created_at is not None
        assert user.updated_at is not None


class TestNotificationPreferenceModel:
    """Task 1.2: 通知条件テーブルのテスト"""

    def test_create_preference(self, session):
        """通知条件を作成できる"""
        user = User(line_user_id_encrypted="encrypted_user_pref")
        session.add(user)
        session.commit()

        pref = NotificationPreference(
            user_id=user.id,
            species="犬",
            prefectures=["高知県", "愛媛県"],
            age_min_months=0,
            age_max_months=24,
            size="中型",
            sex="男の子",
            notifications_enabled=True,
        )
        session.add(pref)
        session.commit()

        assert pref.id is not None
        assert pref.user_id == user.id
        assert pref.species == "犬"
        assert pref.prefectures == ["高知県", "愛媛県"]
        assert pref.age_min_months == 0
        assert pref.age_max_months == 24
        assert pref.size == "中型"
        assert pref.sex == "男の子"
        assert pref.notifications_enabled is True

    def test_preference_user_unique(self, session):
        """1ユーザーにつき1つの通知条件のみ（ユニーク制約）"""
        user = User(line_user_id_encrypted="encrypted_user_unique")
        session.add(user)
        session.commit()

        pref1 = NotificationPreference(user_id=user.id, species="犬")
        session.add(pref1)
        session.commit()

        pref2 = NotificationPreference(user_id=user.id, species="猫")
        session.add(pref2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_preference_nullable_fields(self, session):
        """条件項目はNULL許容（すべて許可を意味する）"""
        user = User(line_user_id_encrypted="encrypted_user_nullable")
        session.add(user)
        session.commit()

        pref = NotificationPreference(
            user_id=user.id,
            species=None,
            prefectures=None,
            age_min_months=None,
            age_max_months=None,
            size=None,
            sex=None,
        )
        session.add(pref)
        session.commit()

        assert pref.species is None
        assert pref.prefectures is None
        assert pref.size is None
        assert pref.sex is None

    def test_preference_cascade_delete(self, session):
        """ユーザー削除時に通知条件もカスケード削除される"""
        user = User(line_user_id_encrypted="encrypted_user_cascade")
        session.add(user)
        session.commit()

        pref = NotificationPreference(user_id=user.id, species="猫")
        session.add(pref)
        session.commit()
        pref_id = pref.id

        session.delete(user)
        session.commit()

        result = session.execute(
            select(NotificationPreference).where(NotificationPreference.id == pref_id)
        )
        assert result.scalar_one_or_none() is None

    def test_preference_default_notifications_enabled(self, session):
        """notifications_enabled のデフォルト値は True"""
        user = User(line_user_id_encrypted="encrypted_user_default")
        session.add(user)
        session.commit()

        pref = NotificationPreference(user_id=user.id)
        session.add(pref)
        session.commit()

        assert pref.notifications_enabled is True


class TestNotificationHistoryModel:
    """Task 1.3: 通知履歴テーブルのテスト"""

    def test_create_history(self, session):
        """通知履歴を作成できる"""
        user = User(line_user_id_encrypted="encrypted_user_history")
        session.add(user)
        session.commit()

        history = NotificationHistory(
            user_id=user.id,
            animal_source_url="https://example.com/animals/123",
            status="sent",
        )
        session.add(history)
        session.commit()

        assert history.id is not None
        assert history.user_id == user.id
        assert history.animal_source_url == "https://example.com/animals/123"
        assert history.status == "sent"
        assert history.notified_at is not None

    def test_history_user_url_unique(self, session):
        """同一ユーザー・同一動物URLの組み合わせはユニーク（重複通知防止）"""
        user = User(line_user_id_encrypted="encrypted_user_dup")
        session.add(user)
        session.commit()

        history1 = NotificationHistory(
            user_id=user.id,
            animal_source_url="https://example.com/animals/456",
            status="sent",
        )
        session.add(history1)
        session.commit()

        history2 = NotificationHistory(
            user_id=user.id,
            animal_source_url="https://example.com/animals/456",
            status="sent",
        )
        session.add(history2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_history_different_users_same_url(self, session):
        """異なるユーザーは同じ動物URLに対して通知履歴を持てる"""
        user1 = User(line_user_id_encrypted="encrypted_user1")
        user2 = User(line_user_id_encrypted="encrypted_user2")
        session.add_all([user1, user2])
        session.commit()

        history1 = NotificationHistory(
            user_id=user1.id,
            animal_source_url="https://example.com/animals/789",
            status="sent",
        )
        history2 = NotificationHistory(
            user_id=user2.id,
            animal_source_url="https://example.com/animals/789",
            status="sent",
        )
        session.add_all([history1, history2])
        session.commit()

        assert history1.id is not None
        assert history2.id is not None

    def test_history_cascade_delete(self, session):
        """ユーザー削除時に通知履歴もカスケード削除される"""
        user = User(line_user_id_encrypted="encrypted_user_hist_cascade")
        session.add(user)
        session.commit()

        history = NotificationHistory(
            user_id=user.id,
            animal_source_url="https://example.com/animals/cascade",
            status="sent",
        )
        session.add(history)
        session.commit()
        history_id = history.id

        session.delete(user)
        session.commit()

        result = session.execute(
            select(NotificationHistory).where(NotificationHistory.id == history_id)
        )
        assert result.scalar_one_or_none() is None

    def test_history_status_values(self, session):
        """ステータスは 'sent', 'failed', 'skipped' を格納可能"""
        user = User(line_user_id_encrypted="encrypted_user_status")
        session.add(user)
        session.commit()

        for i, status in enumerate(["sent", "failed", "skipped"]):
            history = NotificationHistory(
                user_id=user.id,
                animal_source_url=f"https://example.com/animals/{i}",
                status=status,
            )
            session.add(history)
            session.commit()
            assert history.status == status
