"""
インフラストラクチャ層

ファイル I/O、スケジューラー連携、通知などの外部システム依存を提供します。
"""

from .snapshot_store import SnapshotStore

__all__ = ["SnapshotStore"]
