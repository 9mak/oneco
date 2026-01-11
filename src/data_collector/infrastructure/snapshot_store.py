"""
スナップショットストア

前回収集結果のスナップショットをファイルシステムに永続化します。
"""

import json
from typing import List, Optional
from pathlib import Path

from ..domain.models import AnimalData


class SnapshotStore:
    """
    スナップショット永続化

    前回収集した AnimalData のリストを JSON ファイルとして保存し、
    差分検知のための比較元データを提供します。
    """

    LATEST_SNAPSHOT_FILENAME = "latest.json"

    def __init__(self, snapshot_dir: Optional[Path] = None):
        """
        SnapshotStore を初期化

        Args:
            snapshot_dir: スナップショット保存ディレクトリ。
                          None の場合は "snapshots" を使用。
        """
        self.snapshot_dir = snapshot_dir or Path("snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    @property
    def snapshot_file(self) -> Path:
        """最新スナップショットファイルのパス"""
        return self.snapshot_dir / self.LATEST_SNAPSHOT_FILENAME

    def load_snapshot(self) -> List[AnimalData]:
        """
        最新スナップショットを読み込み

        Returns:
            List[AnimalData]: 前回収集したデータ（存在しない場合は空リスト）

        Raises:
            json.JSONDecodeError: JSON パースに失敗した場合
        """
        if not self.snapshot_file.exists():
            return []

        with open(self.snapshot_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [AnimalData(**item) for item in data]

    def save_snapshot(self, data: List[AnimalData]) -> None:
        """
        今回の収集結果をスナップショットとして保存

        Args:
            data: 今回収集したデータ

        Note:
            - ensure_ascii=False で日本語をそのまま保存
            - indent=2 で人間が読みやすい形式に整形
        """
        with open(self.snapshot_file, "w", encoding="utf-8") as f:
            json_data = [animal.model_dump(mode="json") for animal in data]
            json.dump(json_data, f, ensure_ascii=False, indent=2)
