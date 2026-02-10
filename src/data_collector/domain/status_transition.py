"""
StatusTransitionValidator - ステータス遷移検証

動物のステータス遷移の妥当性を検証するバリデータを提供します。
"""

from typing import Set, Tuple
from src.data_collector.domain.models import AnimalStatus


class StatusTransitionError(ValueError):
    """
    不正なステータス遷移エラー

    無効なステータス遷移が試行された場合に発生します。
    """

    def __init__(self, old_status: AnimalStatus, new_status: AnimalStatus):
        """
        StatusTransitionError を初期化

        Args:
            old_status: 現在のステータス
            new_status: 新しいステータス
        """
        self.old_status = old_status
        self.new_status = new_status
        super().__init__(
            f"無効なステータス遷移: {old_status.value} → {new_status.value}"
        )


class StatusTransitionValidator:
    """
    ステータス遷移検証

    動物のステータス遷移が有効かどうかを検証します。
    """

    # 有効な遷移: (from_status, to_status)
    VALID_TRANSITIONS: Set[Tuple[AnimalStatus, AnimalStatus]] = {
        (AnimalStatus.SHELTERED, AnimalStatus.ADOPTED),
        (AnimalStatus.SHELTERED, AnimalStatus.RETURNED),
        (AnimalStatus.SHELTERED, AnimalStatus.DECEASED),
        (AnimalStatus.ADOPTED, AnimalStatus.RETURNED),  # 返還
        (AnimalStatus.ADOPTED, AnimalStatus.DECEASED),
        (AnimalStatus.RETURNED, AnimalStatus.ADOPTED),  # 再譲渡
        (AnimalStatus.RETURNED, AnimalStatus.DECEASED),
    }

    def validate_transition(
        self,
        old_status: AnimalStatus,
        new_status: AnimalStatus
    ) -> None:
        """
        ステータス遷移を検証

        Args:
            old_status: 現在のステータス
            new_status: 新しいステータス

        Raises:
            StatusTransitionError: 不正な遷移の場合
        """
        if (old_status, new_status) not in self.VALID_TRANSITIONS:
            raise StatusTransitionError(old_status, new_status)
