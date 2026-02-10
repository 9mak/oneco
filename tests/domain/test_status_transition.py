"""
StatusTransitionValidator のテスト

ステータス遷移の妥当性検証が要件通りに実装されているかを検証します。
"""
import pytest
from src.data_collector.domain.models import AnimalStatus
from src.data_collector.domain.status_transition import (
    StatusTransitionValidator,
    StatusTransitionError,
)


class TestStatusTransitionError:
    """StatusTransitionError 例外のテスト"""

    def test_status_transition_error_message(self):
        """エラーメッセージが正しく生成されることを確認"""
        error = StatusTransitionError(
            AnimalStatus.DECEASED, AnimalStatus.SHELTERED
        )

        assert "deceased" in str(error)
        assert "sheltered" in str(error)
        assert error.old_status == AnimalStatus.DECEASED
        assert error.new_status == AnimalStatus.SHELTERED

    def test_status_transition_error_is_value_error(self):
        """StatusTransitionError が ValueError のサブクラスであることを確認"""
        error = StatusTransitionError(
            AnimalStatus.DECEASED, AnimalStatus.SHELTERED
        )
        assert isinstance(error, ValueError)


class TestStatusTransitionValidator:
    """StatusTransitionValidator のテスト"""

    @pytest.fixture
    def validator(self):
        """テスト用の validator インスタンスを作成"""
        return StatusTransitionValidator()

    def test_valid_transition_sheltered_to_adopted(self, validator):
        """sheltered → adopted は有効な遷移"""
        # 例外が発生しなければ成功
        validator.validate_transition(
            AnimalStatus.SHELTERED, AnimalStatus.ADOPTED
        )

    def test_valid_transition_sheltered_to_returned(self, validator):
        """sheltered → returned は有効な遷移"""
        validator.validate_transition(
            AnimalStatus.SHELTERED, AnimalStatus.RETURNED
        )

    def test_valid_transition_sheltered_to_deceased(self, validator):
        """sheltered → deceased は有効な遷移"""
        validator.validate_transition(
            AnimalStatus.SHELTERED, AnimalStatus.DECEASED
        )

    def test_valid_transition_adopted_to_returned(self, validator):
        """adopted → returned は有効な遷移（返還）"""
        validator.validate_transition(
            AnimalStatus.ADOPTED, AnimalStatus.RETURNED
        )

    def test_valid_transition_adopted_to_deceased(self, validator):
        """adopted → deceased は有効な遷移"""
        validator.validate_transition(
            AnimalStatus.ADOPTED, AnimalStatus.DECEASED
        )

    def test_valid_transition_returned_to_adopted(self, validator):
        """returned → adopted は有効な遷移（再譲渡）"""
        validator.validate_transition(
            AnimalStatus.RETURNED, AnimalStatus.ADOPTED
        )

    def test_valid_transition_returned_to_deceased(self, validator):
        """returned → deceased は有効な遷移"""
        validator.validate_transition(
            AnimalStatus.RETURNED, AnimalStatus.DECEASED
        )

    def test_invalid_transition_deceased_to_sheltered(self, validator):
        """deceased → sheltered は無効な遷移"""
        with pytest.raises(StatusTransitionError) as exc_info:
            validator.validate_transition(
                AnimalStatus.DECEASED, AnimalStatus.SHELTERED
            )

        assert exc_info.value.old_status == AnimalStatus.DECEASED
        assert exc_info.value.new_status == AnimalStatus.SHELTERED

    def test_invalid_transition_deceased_to_adopted(self, validator):
        """deceased → adopted は無効な遷移"""
        with pytest.raises(StatusTransitionError):
            validator.validate_transition(
                AnimalStatus.DECEASED, AnimalStatus.ADOPTED
            )

    def test_invalid_transition_deceased_to_returned(self, validator):
        """deceased → returned は無効な遷移"""
        with pytest.raises(StatusTransitionError):
            validator.validate_transition(
                AnimalStatus.DECEASED, AnimalStatus.RETURNED
            )

    def test_invalid_transition_adopted_to_sheltered(self, validator):
        """adopted → sheltered は無効な遷移"""
        with pytest.raises(StatusTransitionError):
            validator.validate_transition(
                AnimalStatus.ADOPTED, AnimalStatus.SHELTERED
            )

    def test_invalid_transition_returned_to_sheltered(self, validator):
        """returned → sheltered は無効な遷移"""
        with pytest.raises(StatusTransitionError):
            validator.validate_transition(
                AnimalStatus.RETURNED, AnimalStatus.SHELTERED
            )

    def test_same_status_transition_is_invalid(self, validator):
        """同じステータスへの遷移は無効"""
        with pytest.raises(StatusTransitionError):
            validator.validate_transition(
                AnimalStatus.SHELTERED, AnimalStatus.SHELTERED
            )

        with pytest.raises(StatusTransitionError):
            validator.validate_transition(
                AnimalStatus.ADOPTED, AnimalStatus.ADOPTED
            )

    def test_valid_transitions_constant(self, validator):
        """VALID_TRANSITIONS 定数が正しく定義されていることを確認"""
        # 設計書で定義された有効な遷移が全て含まれている
        expected_transitions = {
            (AnimalStatus.SHELTERED, AnimalStatus.ADOPTED),
            (AnimalStatus.SHELTERED, AnimalStatus.RETURNED),
            (AnimalStatus.SHELTERED, AnimalStatus.DECEASED),
            (AnimalStatus.ADOPTED, AnimalStatus.RETURNED),
            (AnimalStatus.ADOPTED, AnimalStatus.DECEASED),
            (AnimalStatus.RETURNED, AnimalStatus.ADOPTED),
            (AnimalStatus.RETURNED, AnimalStatus.DECEASED),
        }

        assert StatusTransitionValidator.VALID_TRANSITIONS == expected_transitions
