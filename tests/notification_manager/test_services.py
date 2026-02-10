"""
notification-manager ドメインサービスのテスト

Task 5.1-5.4: ユーザーサービス、マッチングサービス、通知サービスのテスト
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import date

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


class TestMatchingService:
    """マッチングサービスのテスト (Task 5.2)"""

    @pytest.fixture
    def matching_service(self):
        """テスト用マッチングサービス"""
        from src.notification_manager.domain.services import MatchingService

        mock_pref_repo = Mock()
        mock_user_repo = Mock()
        return MatchingService(
            preference_repository=mock_pref_repo,
            user_repository=mock_user_repo,
        )

    @pytest.fixture
    def sample_animal(self):
        """サンプル動物データ"""
        return AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            size="中型",
            shelter_date=date(2026, 1, 15),
            location="高知県高知市",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

    @pytest.fixture
    def matching_preference(self):
        """マッチする通知条件"""
        return NotificationPreferenceEntity(
            id=1,
            user_id=100,
            species="犬",
            prefectures=["高知県"],
            age_min_months=12,
            age_max_months=36,
            size="中型",
            sex="男の子",
            notifications_enabled=True,
        )

    def test_exact_match_all_conditions(self, matching_service, sample_animal, matching_preference):
        """全条件が完全一致する場合"""
        # 準備
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        # 実行
        results = matching_service.find_matching_users(sample_animal)

        # 検証
        assert len(results) == 1
        assert results[0].user_id == 100
        assert results[0].preference_id == 1
        assert results[0].match_score == 1.0

    def test_species_mismatch(self, matching_service, sample_animal, matching_preference):
        """種別が一致しない場合"""
        # 猫を探している人
        matching_preference.species = "猫"
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0

    def test_prefecture_mismatch(self, matching_service, sample_animal, matching_preference):
        """都道府県が一致しない場合"""
        # 東京都を探している人
        matching_preference.prefectures = ["東京都"]
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0

    def test_age_below_minimum(self, matching_service, sample_animal, matching_preference):
        """年齢が下限より若い場合"""
        # 1歳以上を希望しているが、動物は6ヶ月
        sample_animal.age_months = 6
        matching_preference.age_min_months = 12
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0

    def test_age_above_maximum(self, matching_service, sample_animal, matching_preference):
        """年齢が上限を超えている場合"""
        # 3歳以下を希望しているが、動物は5歳
        sample_animal.age_months = 60
        matching_preference.age_max_months = 36
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0

    def test_size_mismatch(self, matching_service, sample_animal, matching_preference):
        """サイズが一致しない場合"""
        # 小型犬を探している人
        matching_preference.size = "小型"
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0

    def test_sex_mismatch(self, matching_service, sample_animal, matching_preference):
        """性別が一致しない場合"""
        # 女の子を探している人
        matching_preference.sex = "女の子"
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0

    def test_none_species_matches_any(self, matching_service, sample_animal, matching_preference):
        """種別がNoneの場合は全種別にマッチ"""
        matching_preference.species = None
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_none_prefectures_matches_any(self, matching_service, sample_animal, matching_preference):
        """都道府県がNoneまたは空の場合は全都道府県にマッチ"""
        matching_preference.prefectures = None
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_none_age_range_matches_any(self, matching_service, sample_animal, matching_preference):
        """年齢範囲がNoneの場合は全年齢にマッチ"""
        matching_preference.age_min_months = None
        matching_preference.age_max_months = None
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_none_size_matches_any(self, matching_service, sample_animal, matching_preference):
        """サイズがNoneの場合は全サイズにマッチ"""
        matching_preference.size = None
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_none_sex_matches_any(self, matching_service, sample_animal, matching_preference):
        """性別がNoneの場合は全性別にマッチ"""
        matching_preference.sex = None
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_multiple_users_match(self, matching_service, sample_animal):
        """複数ユーザーがマッチする場合"""
        prefs = [
            NotificationPreferenceEntity(
                id=1, user_id=100, species="犬", prefectures=["高知県"],
                age_min_months=None, age_max_months=None, size=None, sex=None,
                notifications_enabled=True,
            ),
            NotificationPreferenceEntity(
                id=2, user_id=200, species=None, prefectures=None,
                age_min_months=None, age_max_months=None, size=None, sex=None,
                notifications_enabled=True,
            ),
        ]
        matching_service._preference_repository.get_active_preferences.return_value = prefs

        def get_user_by_id(user_id):
            return UserEntity(
                id=user_id,
                line_user_id_encrypted=f"encrypted_{user_id}",
                is_active=True,
            )
        matching_service._user_repository.get_by_id = Mock(side_effect=get_user_by_id)

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 2

    def test_multiple_prefectures_match(self, matching_service, sample_animal, matching_preference):
        """複数都道府県を設定している場合、いずれかにマッチすればOK"""
        matching_preference.prefectures = ["東京都", "高知県", "愛媛県"]
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_animal_with_unknown_age_matches_no_age_filter(
        self, matching_service, sample_animal, matching_preference
    ):
        """動物の年齢がNoneで、年齢条件がない場合はマッチ"""
        sample_animal.age_months = None
        matching_preference.age_min_months = None
        matching_preference.age_max_months = None
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]
        matching_service._user_repository.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_user_id_100",
                is_active=True,
            )
        )

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 1

    def test_animal_with_unknown_age_skips_age_filter(
        self, matching_service, sample_animal, matching_preference
    ):
        """動物の年齢がNoneで、年齢条件がある場合はマッチしない"""
        sample_animal.age_months = None
        matching_preference.age_min_months = 12
        matching_service._preference_repository.get_active_preferences.return_value = [
            matching_preference
        ]

        results = matching_service.find_matching_users(sample_animal)

        assert len(results) == 0


class TestUserService:
    """ユーザーサービスのテスト (Task 5.1)"""

    @pytest.fixture
    def user_service(self):
        """テスト用ユーザーサービス"""
        from src.notification_manager.domain.services import UserService

        mock_user_repo = Mock()
        mock_pref_repo = Mock()
        mock_encryption = Mock()
        return UserService(
            user_repository=mock_user_repo,
            preference_repository=mock_pref_repo,
            encryption_service=mock_encryption,
        )

    def test_register_new_user(self, user_service):
        """新規ユーザーを登録できる"""
        user_service._encryption_service.encrypt.return_value = "encrypted_U123"
        user_service._user_repository.get_by_encrypted_line_id.return_value = None
        user_service._user_repository.create_user.return_value = UserEntity(
            id=1,
            line_user_id_encrypted="encrypted_U123",
            is_active=True,
        )

        result = user_service.register_user("U123")

        assert result.id == 1
        assert result.is_active is True
        user_service._encryption_service.encrypt.assert_called_once_with("U123")

    def test_register_existing_user_reactivates(self, user_service):
        """既存ユーザーが再登録した場合は再アクティブ化"""
        user_service._encryption_service.encrypt.return_value = "encrypted_U123"
        user_service._user_repository.get_by_encrypted_line_id.return_value = UserEntity(
            id=1,
            line_user_id_encrypted="encrypted_U123",
            is_active=False,
        )
        user_service._user_repository.reactivate.return_value = UserEntity(
            id=1,
            line_user_id_encrypted="encrypted_U123",
            is_active=True,
        )

        result = user_service.register_user("U123")

        assert result.is_active is True

    def test_update_preferences(self, user_service):
        """通知条件を更新できる"""
        pref_input = NotificationPreferenceInput(
            species="犬",
            prefectures=["高知県"],
            size="中型",
        )
        user_service._pref_repository.create_or_update.return_value = NotificationPreferenceEntity(
            id=1,
            user_id=100,
            species="犬",
            prefectures=["高知県"],
            age_min_months=None,
            age_max_months=None,
            size="中型",
            sex=None,
            notifications_enabled=True,
        )

        result = user_service.update_preferences(100, pref_input)

        assert result.species == "犬"
        assert result.prefectures == ["高知県"]

    def test_deactivate_user(self, user_service):
        """ユーザーを無効化できる"""
        user_service._encryption_service.encrypt.return_value = "encrypted_U123"
        user_service._user_repository.deactivate.return_value = True

        result = user_service.deactivate_user("U123")

        assert result is True

    def test_toggle_notifications(self, user_service):
        """通知の有効/無効を切り替えできる"""
        user_service._pref_repository.set_notifications_enabled.return_value = True

        result = user_service.toggle_notifications(100, False)

        assert result is True
        user_service._pref_repository.set_notifications_enabled.assert_called_once_with(
            100, False
        )


class TestNotificationService:
    """通知サービスのテスト (Task 5.3, 5.4)"""

    @pytest.fixture
    def notification_service(self):
        """テスト用通知サービス"""
        from src.notification_manager.domain.services import NotificationService

        mock_matching = Mock()
        mock_history_repo = Mock()
        mock_line_adapter = Mock()
        mock_encryption = Mock()
        return NotificationService(
            matching_service=mock_matching,
            history_repository=mock_history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

    @pytest.fixture
    def sample_animal(self):
        """サンプル動物データ"""
        return AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            size="中型",
            shelter_date=date(2026, 1, 15),
            location="高知県高知市",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

    @pytest.mark.asyncio
    async def test_process_single_animal_success(self, notification_service, sample_animal):
        """単一動物の通知処理が成功する"""
        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )
        notification_service._matching_service.find_matching_users.return_value = [match_result]
        notification_service._history_repository.is_already_notified.return_value = False
        notification_service._encryption_service.decrypt.return_value = "U123"
        notification_service._line_adapter.send_with_retry = AsyncMock(
            return_value=SendResult(success=True)
        )
        notification_service._history_repository.record = Mock()

        result = await notification_service.process_new_animals([sample_animal])

        assert result.total_animals == 1
        assert result.total_matches == 1
        assert result.sent_count == 1
        assert result.skipped_count == 0
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_process_skip_duplicate_notification(self, notification_service, sample_animal):
        """既に通知済みの場合はスキップする"""
        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )
        notification_service._matching_service.find_matching_users.return_value = [match_result]
        notification_service._history_repository.is_already_notified.return_value = True

        result = await notification_service.process_new_animals([sample_animal])

        assert result.total_animals == 1
        assert result.total_matches == 1
        assert result.sent_count == 0
        assert result.skipped_count == 1
        assert result.failed_count == 0

    @pytest.mark.asyncio
    async def test_process_failed_send(self, notification_service, sample_animal):
        """送信失敗時はfailed_countが増加する"""
        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )
        notification_service._matching_service.find_matching_users.return_value = [match_result]
        notification_service._history_repository.is_already_notified.return_value = False
        notification_service._encryption_service.decrypt.return_value = "U123"
        notification_service._line_adapter.send_with_retry = AsyncMock(
            return_value=SendResult(success=False, error_code="500")
        )
        notification_service._history_repository.record = Mock()

        result = await notification_service.process_new_animals([sample_animal])

        assert result.total_animals == 1
        assert result.total_matches == 1
        assert result.sent_count == 0
        assert result.skipped_count == 0
        assert result.failed_count == 1

    @pytest.mark.asyncio
    async def test_process_no_matches(self, notification_service, sample_animal):
        """マッチするユーザーがいない場合"""
        notification_service._matching_service.find_matching_users.return_value = []

        result = await notification_service.process_new_animals([sample_animal])

        assert result.total_animals == 1
        assert result.total_matches == 0
        assert result.sent_count == 0

    @pytest.mark.asyncio
    async def test_process_multiple_animals(self, notification_service):
        """複数動物の処理"""
        animals = [
            AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                shelter_date=date(2026, 1, 15),
                location="高知県",
                source_url=f"https://example.com/animals/{i}",
                category="adoption",
            )
            for i in range(3)
        ]

        notification_service._matching_service.find_matching_users.return_value = [
            MatchResult(
                user_id=100,
                line_user_id_encrypted="encrypted_U123",
                preference_id=1,
                match_score=1.0,
            )
        ]
        notification_service._history_repository.is_already_notified.return_value = False
        notification_service._encryption_service.decrypt.return_value = "U123"
        notification_service._line_adapter.send_with_retry = AsyncMock(
            return_value=SendResult(success=True)
        )
        notification_service._history_repository.record = Mock()

        result = await notification_service.process_new_animals(animals)

        assert result.total_animals == 3
        assert result.total_matches == 3
        assert result.sent_count == 3

    @pytest.mark.asyncio
    async def test_records_history_on_success(self, notification_service, sample_animal):
        """送信成功時に履歴を記録する"""
        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )
        notification_service._matching_service.find_matching_users.return_value = [match_result]
        notification_service._history_repository.is_already_notified.return_value = False
        notification_service._encryption_service.decrypt.return_value = "U123"
        notification_service._line_adapter.send_with_retry = AsyncMock(
            return_value=SendResult(success=True)
        )
        notification_service._history_repository.record = Mock()

        await notification_service.process_new_animals([sample_animal])

        notification_service._history_repository.record.assert_called_once_with(
            user_id=100,
            animal_source_url=str(sample_animal.source_url),
            status="sent",
        )

    @pytest.mark.asyncio
    async def test_records_history_on_failure(self, notification_service, sample_animal):
        """送信失敗時も履歴を記録する"""
        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )
        notification_service._matching_service.find_matching_users.return_value = [match_result]
        notification_service._history_repository.is_already_notified.return_value = False
        notification_service._encryption_service.decrypt.return_value = "U123"
        notification_service._line_adapter.send_with_retry = AsyncMock(
            return_value=SendResult(success=False, error_code="500")
        )
        notification_service._history_repository.record = Mock()

        await notification_service.process_new_animals([sample_animal])

        notification_service._history_repository.record.assert_called_once_with(
            user_id=100,
            animal_source_url=str(sample_animal.source_url),
            status="failed",
        )
