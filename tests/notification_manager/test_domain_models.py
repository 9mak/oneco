"""
notification-manager ドメインモデルのテスト

Task 2.1: ドメインモデル（User, NotificationPreference, MatchResult）のテスト
"""

import pytest
from pydantic import ValidationError

from src.notification_manager.domain.models import (
    MatchResult,
    NotificationMessage,
    NotificationPreferenceEntity,
    NotificationPreferenceInput,
    SendResult,
    UserEntity,
)


class TestUserEntity:
    """ユーザーエンティティのテスト"""

    def test_create_user_entity(self):
        """ユーザーエンティティを作成できる"""
        user = UserEntity(
            id=1,
            line_user_id_encrypted="encrypted_U1234567890",
            is_active=True,
        )
        assert user.id == 1
        assert user.line_user_id_encrypted == "encrypted_U1234567890"
        assert user.is_active is True

    def test_user_entity_default_is_active(self):
        """is_active のデフォルト値は True"""
        user = UserEntity(
            id=1,
            line_user_id_encrypted="encrypted_test",
        )
        assert user.is_active is True


class TestNotificationPreferenceInput:
    """通知条件入力のテスト"""

    def test_create_preference_input_full(self):
        """完全な通知条件入力を作成できる"""
        pref = NotificationPreferenceInput(
            species="犬",
            prefectures=["高知県", "愛媛県"],
            age_min_months=0,
            age_max_months=24,
            size="中型",
            sex="男の子",
        )
        assert pref.species == "犬"
        assert pref.prefectures == ["高知県", "愛媛県"]
        assert pref.age_min_months == 0
        assert pref.age_max_months == 24
        assert pref.size == "中型"
        assert pref.sex == "男の子"

    def test_create_preference_input_minimal(self):
        """最小限の通知条件入力を作成できる（全項目オプショナル）"""
        pref = NotificationPreferenceInput()
        assert pref.species is None
        assert pref.prefectures is None
        assert pref.age_min_months is None
        assert pref.age_max_months is None
        assert pref.size is None
        assert pref.sex is None

    def test_species_validation(self):
        """種別は '犬', '猫', None のいずれかである必要がある"""
        # 有効な値
        pref_dog = NotificationPreferenceInput(species="犬")
        assert pref_dog.species == "犬"

        pref_cat = NotificationPreferenceInput(species="猫")
        assert pref_cat.species == "猫"

        pref_none = NotificationPreferenceInput(species=None)
        assert pref_none.species is None

        # 無効な値
        with pytest.raises(ValidationError):
            NotificationPreferenceInput(species="ウサギ")

    def test_sex_validation(self):
        """性別は '男の子', '女の子', None のいずれかである必要がある"""
        # 有効な値
        pref_male = NotificationPreferenceInput(sex="男の子")
        assert pref_male.sex == "男の子"

        pref_female = NotificationPreferenceInput(sex="女の子")
        assert pref_female.sex == "女の子"

        # 無効な値
        with pytest.raises(ValidationError):
            NotificationPreferenceInput(sex="オス")

    def test_size_validation(self):
        """サイズは '小型', '中型', '大型', None のいずれかである必要がある"""
        for valid_size in ["小型", "中型", "大型", None]:
            pref = NotificationPreferenceInput(size=valid_size)
            assert pref.size == valid_size

        with pytest.raises(ValidationError):
            NotificationPreferenceInput(size="特大")

    def test_age_range_validation(self):
        """年齢範囲は非負の整数である必要がある"""
        pref = NotificationPreferenceInput(age_min_months=0, age_max_months=24)
        assert pref.age_min_months == 0
        assert pref.age_max_months == 24

        with pytest.raises(ValidationError):
            NotificationPreferenceInput(age_min_months=-1)


class TestNotificationPreferenceEntity:
    """通知条件エンティティのテスト"""

    def test_create_preference_entity(self):
        """通知条件エンティティを作成できる"""
        pref = NotificationPreferenceEntity(
            id=1,
            user_id=10,
            species="猫",
            prefectures=["東京都"],
            age_min_months=12,
            age_max_months=60,
            size="小型",
            sex="女の子",
            notifications_enabled=True,
        )
        assert pref.id == 1
        assert pref.user_id == 10
        assert pref.species == "猫"
        assert pref.notifications_enabled is True

    def test_preference_entity_default_notifications_enabled(self):
        """notifications_enabled のデフォルト値は True"""
        pref = NotificationPreferenceEntity(id=1, user_id=10)
        assert pref.notifications_enabled is True


class TestMatchResult:
    """マッチング結果のテスト"""

    def test_create_match_result(self):
        """マッチング結果を作成できる"""
        result = MatchResult(
            user_id=1,
            line_user_id_encrypted="encrypted_user",
            preference_id=10,
            match_score=1.0,
        )
        assert result.user_id == 1
        assert result.line_user_id_encrypted == "encrypted_user"
        assert result.preference_id == 10
        assert result.match_score == 1.0

    def test_match_score_range(self):
        """マッチスコアは 0.0 から 1.0 の範囲"""
        result_full = MatchResult(
            user_id=1,
            line_user_id_encrypted="test",
            preference_id=1,
            match_score=1.0,
        )
        assert result_full.match_score == 1.0

        result_zero = MatchResult(
            user_id=1,
            line_user_id_encrypted="test",
            preference_id=1,
            match_score=0.0,
        )
        assert result_zero.match_score == 0.0


class TestNotificationMessage:
    """通知メッセージのテスト"""

    def test_create_notification_message(self):
        """通知メッセージを作成できる"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            age_months=24,
            size="中型",
            location="高知県高知市",
            source_url="https://example.com/animals/123",
            category="adoption",
        )
        assert msg.species == "犬"
        assert msg.sex == "男の子"
        assert msg.age_months == 24
        assert msg.size == "中型"
        assert msg.location == "高知県高知市"
        assert msg.source_url == "https://example.com/animals/123"
        assert msg.category == "adoption"

    def test_notification_message_optional_fields(self):
        """age_months と size はオプショナル"""
        msg = NotificationMessage(
            species="猫",
            sex="女の子",
            location="東京都新宿区",
            source_url="https://example.com/animals/456",
            category="lost",
        )
        assert msg.age_months is None
        assert msg.size is None

    def test_format_message(self):
        """メッセージをフォーマットできる"""
        msg = NotificationMessage(
            species="犬",
            sex="男の子",
            age_months=24,
            size="中型",
            location="高知県高知市",
            source_url="https://example.com/animals/123",
            category="adoption",
        )
        formatted = msg.format_message()
        assert "犬" in formatted
        assert "男の子" in formatted
        assert "高知県高知市" in formatted
        assert "https://example.com/animals/123" in formatted


class TestSendResult:
    """送信結果のテスト"""

    def test_create_send_result_success(self):
        """成功した送信結果を作成できる"""
        result = SendResult(success=True)
        assert result.success is True
        assert result.error_code is None
        assert result.retry_after is None

    def test_create_send_result_failure(self):
        """失敗した送信結果を作成できる"""
        result = SendResult(
            success=False,
            error_code="429",
            retry_after=60,
        )
        assert result.success is False
        assert result.error_code == "429"
        assert result.retry_after == 60
