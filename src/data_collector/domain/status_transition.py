"""
StatusTransitionValidator - ステータス遷移検証

動物のステータス遷移の妥当性を検証するバリデータを提供します。
"""

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
        super().__init__(f"無効なステータス遷移: {old_status.value} → {new_status.value}")


class StatusTransitionValidator:
    """
    ステータス遷移検証

    動物のステータス遷移が有効かどうかを検証します。
    """

    # 有効な遷移: (from_status, to_status)
    VALID_TRANSITIONS: set[tuple[AnimalStatus, AnimalStatus]] = {
        (AnimalStatus.SHELTERED, AnimalStatus.ADOPTED),
        (AnimalStatus.SHELTERED, AnimalStatus.RETURNED),
        (AnimalStatus.SHELTERED, AnimalStatus.DECEASED),
        (AnimalStatus.ADOPTED, AnimalStatus.RETURNED),  # 返還
        (AnimalStatus.ADOPTED, AnimalStatus.DECEASED),
        (AnimalStatus.RETURNED, AnimalStatus.ADOPTED),  # 再譲渡
        (AnimalStatus.RETURNED, AnimalStatus.DECEASED),
        # 死亡の取り消し (T424)。収集が備考の「死亡確認」を読んで deceased を
        # 立てるようになったため、誤検知や自治体側の誤記を人が戻せる経路が要る。
        # これが無いと deceased は終端で、誤って公開から消えた子を DB を直接
        # 書き換える以外に戻せない。収集経路がこの遷移を使うことは無い
        # (adapter は死亡を検知したときだけ status を返し、sheltered は返さない)。
        (AnimalStatus.DECEASED, AnimalStatus.SHELTERED),
    }

    def validate_transition(self, old_status: AnimalStatus, new_status: AnimalStatus) -> None:
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
