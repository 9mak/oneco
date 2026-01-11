"""
差分検知ロジック

前回収集時からの差分を検知し、新規・更新・削除候補を識別します。
"""

from typing import List, TYPE_CHECKING
from pydantic import BaseModel, Field

from .models import AnimalData

if TYPE_CHECKING:
    from ..infrastructure.snapshot_store import SnapshotStore


class DiffResult(BaseModel):
    """
    差分検知結果

    新規・更新・削除候補の分類結果を保持します。
    """

    new: List[AnimalData] = Field(default_factory=list, description="新規個体リスト")
    updated: List[AnimalData] = Field(default_factory=list, description="更新個体リスト")
    deleted_candidates: List[str] = Field(
        default_factory=list,
        description="削除候補の source_url リスト"
    )


class DiffDetector:
    """
    差分検知ロジック

    前回スナップショットと今回収集データを比較し、
    新規・更新・削除候補を識別します。
    """

    def __init__(self, snapshot_store: "SnapshotStore"):
        """
        DiffDetector を初期化

        Args:
            snapshot_store: スナップショット読み込み用ストア
        """
        self.snapshot_store = snapshot_store

    def detect_diff(self, current_data: List[AnimalData]) -> DiffResult:
        """
        前回スナップショットとの差分を検知

        Args:
            current_data: 今回収集したデータ

        Returns:
            DiffResult: 新規・更新・削除候補の分類結果

        Note:
            - source_url をユニークキーとして使用
            - 新規: 前回スナップショットに存在しない URL
            - 更新: 既存 URL だが内容が変更されている
            - 削除候補: 今回リストに存在しない URL
        """
        previous_data = self.snapshot_store.load_snapshot()

        # source_url をキーとした辞書に変換
        previous_dict = {str(animal.source_url): animal for animal in previous_data}
        current_dict = {str(animal.source_url): animal for animal in current_data}

        result = DiffResult()

        # 新規・更新の検知
        for url, animal in current_dict.items():
            if url not in previous_dict:
                # 新規: 前回スナップショットに存在しない
                result.new.append(animal)
            elif not self._animals_equal(animal, previous_dict[url]):
                # 更新: 既存だが内容が変更されている
                result.updated.append(animal)

        # 削除候補の検知
        for url in previous_dict:
            if url not in current_dict:
                result.deleted_candidates.append(url)

        return result

    def _animals_equal(self, a: AnimalData, b: AnimalData) -> bool:
        """
        2つの AnimalData が等しいかを比較

        Args:
            a: 比較対象1
            b: 比較対象2

        Returns:
            bool: すべてのフィールドが一致すれば True
        """
        return (
            a.species == b.species
            and a.sex == b.sex
            and a.age_months == b.age_months
            and a.color == b.color
            and a.size == b.size
            and a.shelter_date == b.shelter_date
            and a.location == b.location
            and a.phone == b.phone
            and list(a.image_urls) == list(b.image_urls)
            and str(a.source_url) == str(b.source_url)
        )
