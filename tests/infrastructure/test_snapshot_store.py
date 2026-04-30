"""
SnapshotStore のユニットテスト

no-op 実装の動作を検証します。
差分管理は DB の upsert が担うため、SnapshotStore はファイルを作成しません。
"""

from datetime import date

from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.snapshot_store import SnapshotStore


class TestSnapshotStoreInitialization:
    """SnapshotStore 初期化のテスト"""

    def test_snapshot_store_initializes_without_directory(self, tmp_path):
        """初期化時にディレクトリを作成しないこと"""
        snapshot_dir = tmp_path / "snapshots"
        SnapshotStore(snapshot_dir=snapshot_dir)
        assert not snapshot_dir.exists()

    def test_snapshot_store_initializes_without_args(self):
        """引数なしで初期化できること"""
        store = SnapshotStore()
        assert store is not None


class TestSnapshotStoreLoadSnapshot:
    """スナップショット読み込みのテスト"""

    def test_load_snapshot_always_returns_empty_list(self):
        """load_snapshot() は常に空リストを返すこと"""
        store = SnapshotStore()
        result = store.load_snapshot()
        assert result == []

    def test_load_snapshot_returns_empty_list_regardless_of_args(self, tmp_path):
        """引数を渡しても空リストを返すこと"""
        store = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
        result = store.load_snapshot()
        assert result == []


class TestSnapshotStoreSaveSnapshot:
    """スナップショット保存のテスト"""

    def test_save_snapshot_does_not_create_file(self, tmp_path):
        """save_snapshot() はファイルを作成しないこと"""
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)

        animal = AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/animals/001",
            category="adoption",
        )
        store.save_snapshot([animal])

        assert not snapshot_dir.exists()

    def test_save_snapshot_does_not_raise(self):
        """save_snapshot() は例外を発生させないこと"""
        store = SnapshotStore()
        animals = [
            AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/animals/001",
                category="adoption",
            )
        ]
        store.save_snapshot(animals)

    def test_save_then_load_returns_empty(self):
        """save 後に load しても空リストを返すこと（DBが差分を担う）"""
        store = SnapshotStore()
        animal = AnimalData(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/animals/002",
            category="adoption",
        )
        store.save_snapshot([animal])
        result = store.load_snapshot()
        assert result == []
