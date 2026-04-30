"""
スナップショットストア

Cloud Run などエフェメラルな環境向けに、ファイルシステムへの書き込みを行わない
no-op 実装。差分検知はDBのupsert（source_url ユニーク制約）が担う。
"""

from ..domain.models import AnimalData


class SnapshotStore:
    """
    No-op スナップショットストア

    load_snapshot() は常に空リストを返し、save_snapshot() は何もしない。
    DB の upsert が差分管理を担うため、ファイルベースのスナップショットは不要。
    """

    def __init__(self, snapshot_dir=None):
        pass

    def load_snapshot(self) -> list[AnimalData]:
        return []

    def save_snapshot(self, data: list[AnimalData]) -> None:
        pass
