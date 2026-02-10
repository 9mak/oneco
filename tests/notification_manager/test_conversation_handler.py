"""
notification-manager 対話機能のテスト

Task 7.1-7.2: コマンド解析、対話フロー制御、条件入力のテスト
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.notification_manager.domain.conversation import (
    ConversationHandler,
    ConversationState,
    Command,
)
from src.notification_manager.domain.models import (
    NotificationPreferenceInput,
    NotificationPreferenceEntity,
)


class TestCommandParsing:
    """コマンド解析のテスト (Task 7.1)"""

    @pytest.fixture
    def handler(self):
        """テスト用対話ハンドラー"""
        return ConversationHandler(
            user_service=Mock(),
            line_adapter=Mock(),
        )

    def test_recognize_settings_command(self, handler):
        """「設定」コマンドを認識"""
        cmd = handler.parse_command("設定")
        assert cmd == Command.SETTINGS

    def test_recognize_settings_command_variation(self, handler):
        """「条件設定」コマンドを認識"""
        cmd = handler.parse_command("条件設定")
        assert cmd == Command.SETTINGS

    def test_recognize_change_command(self, handler):
        """「条件変更」コマンドを認識"""
        cmd = handler.parse_command("条件変更")
        assert cmd == Command.CHANGE

    def test_recognize_stop_command(self, handler):
        """「停止」コマンドを認識"""
        cmd = handler.parse_command("停止")
        assert cmd == Command.STOP

    def test_recognize_stop_command_variation(self, handler):
        """「通知停止」コマンドを認識"""
        cmd = handler.parse_command("通知停止")
        assert cmd == Command.STOP

    def test_recognize_resume_command(self, handler):
        """「再開」コマンドを認識"""
        cmd = handler.parse_command("再開")
        assert cmd == Command.RESUME

    def test_recognize_status_command(self, handler):
        """「確認」コマンドを認識"""
        cmd = handler.parse_command("確認")
        assert cmd == Command.STATUS

    def test_recognize_help_command(self, handler):
        """「ヘルプ」コマンドを認識"""
        cmd = handler.parse_command("ヘルプ")
        assert cmd == Command.HELP

    def test_unknown_command(self, handler):
        """不明なテキストはNone"""
        cmd = handler.parse_command("こんにちは")
        assert cmd is None


class TestConversationFlow:
    """対話フロー制御のテスト (Task 7.1)"""

    @pytest.fixture
    def handler(self):
        """テスト用対話ハンドラー"""
        return ConversationHandler(
            user_service=Mock(),
            line_adapter=Mock(),
        )

    def test_initial_state_is_idle(self, handler):
        """初期状態はIDLE"""
        state = handler.get_state("user_123")
        assert state == ConversationState.IDLE

    def test_start_settings_flow(self, handler):
        """設定フローを開始"""
        handler.start_settings_flow("user_123")
        state = handler.get_state("user_123")
        assert state == ConversationState.AWAITING_SPECIES

    def test_advance_to_prefectures(self, handler):
        """種別選択後に都道府県選択へ進む"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "犬")
        state = handler.get_state("user_123")
        assert state == ConversationState.AWAITING_PREFECTURES

    def test_advance_to_age(self, handler):
        """都道府県選択後に年齢選択へ進む"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "犬")
        handler.process_input("user_123", "高知県")
        state = handler.get_state("user_123")
        assert state == ConversationState.AWAITING_AGE

    def test_advance_to_size(self, handler):
        """年齢選択後にサイズ選択へ進む"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "犬")
        handler.process_input("user_123", "高知県")
        handler.process_input("user_123", "指定なし")
        state = handler.get_state("user_123")
        assert state == ConversationState.AWAITING_SIZE

    def test_advance_to_sex(self, handler):
        """サイズ選択後に性別選択へ進む"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "犬")
        handler.process_input("user_123", "高知県")
        handler.process_input("user_123", "指定なし")
        handler.process_input("user_123", "中型")
        state = handler.get_state("user_123")
        assert state == ConversationState.AWAITING_SEX

    def test_complete_flow(self, handler):
        """フロー完了"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "犬")
        handler.process_input("user_123", "高知県")
        handler.process_input("user_123", "指定なし")
        handler.process_input("user_123", "中型")
        handler.process_input("user_123", "男の子")
        state = handler.get_state("user_123")
        assert state == ConversationState.IDLE

    def test_cancel_flow(self, handler):
        """「キャンセル」でフローを中断"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "キャンセル")
        state = handler.get_state("user_123")
        assert state == ConversationState.IDLE

    def test_collect_preferences(self, handler):
        """入力された条件を収集（完了前に確認）"""
        handler.start_settings_flow("user_123")
        handler.process_input("user_123", "犬")
        handler.process_input("user_123", "高知県,愛媛県")
        handler.process_input("user_123", "1歳以上")
        handler.process_input("user_123", "中型")

        # 最後のステップの前に収集された条件を確認
        prefs = handler.get_collected_preferences("user_123")
        assert prefs.species == "犬"
        assert "高知県" in prefs.prefectures
        assert "愛媛県" in prefs.prefectures
        assert prefs.age_min_months == 12
        assert prefs.size == "中型"

        # 完了メッセージから最終的な設定を確認
        completion_msg = handler.process_input("user_123", "男の子")
        assert "設定" in completion_msg
        assert "完了" in completion_msg
        assert "犬" in completion_msg


class TestInputValidation:
    """入力バリデーションのテスト (Task 7.2)"""

    @pytest.fixture
    def handler(self):
        """テスト用対話ハンドラー"""
        return ConversationHandler(
            user_service=Mock(),
            line_adapter=Mock(),
        )

    def test_valid_species_dog(self, handler):
        """犬は有効"""
        result = handler.validate_species("犬")
        assert result.is_valid is True
        assert result.value == "犬"

    def test_valid_species_cat(self, handler):
        """猫は有効"""
        result = handler.validate_species("猫")
        assert result.is_valid is True
        assert result.value == "猫"

    def test_valid_species_any(self, handler):
        """どちらでもは有効（Noneとして処理）"""
        result = handler.validate_species("どちらでも")
        assert result.is_valid is True
        assert result.value is None

    def test_invalid_species(self, handler):
        """無効な種別"""
        result = handler.validate_species("鳥")
        assert result.is_valid is False

    def test_valid_prefecture(self, handler):
        """有効な都道府県"""
        result = handler.validate_prefectures("高知県")
        assert result.is_valid is True
        assert result.value == ["高知県"]

    def test_multiple_prefectures(self, handler):
        """複数の都道府県"""
        result = handler.validate_prefectures("高知県,愛媛県,徳島県")
        assert result.is_valid is True
        assert len(result.value) == 3

    def test_valid_age_range(self, handler):
        """年齢範囲の解釈"""
        result = handler.validate_age("1歳以上")
        assert result.is_valid is True
        assert result.min_months == 12
        assert result.max_months is None

    def test_valid_age_range_max(self, handler):
        """年齢上限の解釈"""
        result = handler.validate_age("3歳以下")
        assert result.is_valid is True
        assert result.min_months is None
        assert result.max_months == 36

    def test_valid_age_unspecified(self, handler):
        """年齢指定なし"""
        result = handler.validate_age("指定なし")
        assert result.is_valid is True
        assert result.min_months is None
        assert result.max_months is None

    def test_valid_size(self, handler):
        """有効なサイズ"""
        result = handler.validate_size("中型")
        assert result.is_valid is True
        assert result.value == "中型"

    def test_valid_sex(self, handler):
        """有効な性別"""
        result = handler.validate_sex("男の子")
        assert result.is_valid is True
        assert result.value == "男の子"


class TestMessageGeneration:
    """メッセージ生成のテスト (Task 7.2)"""

    @pytest.fixture
    def handler(self):
        """テスト用対話ハンドラー"""
        return ConversationHandler(
            user_service=Mock(),
            line_adapter=Mock(),
        )

    def test_generate_species_prompt(self, handler):
        """種別選択プロンプト"""
        message = handler.get_prompt_message(ConversationState.AWAITING_SPECIES)
        assert "種別" in message
        assert "犬" in message
        assert "猫" in message

    def test_generate_prefectures_prompt(self, handler):
        """都道府県選択プロンプト"""
        message = handler.get_prompt_message(ConversationState.AWAITING_PREFECTURES)
        assert "都道府県" in message

    def test_generate_completion_message(self, handler):
        """設定完了メッセージ"""
        prefs = NotificationPreferenceInput(
            species="犬",
            prefectures=["高知県"],
            size="中型",
        )
        message = handler.get_completion_message(prefs)
        assert "設定完了" in message or "完了" in message
        assert "犬" in message
        assert "高知県" in message

    def test_generate_help_message(self, handler):
        """ヘルプメッセージ"""
        message = handler.get_help_message()
        assert "設定" in message
        assert "停止" in message
        assert "再開" in message
