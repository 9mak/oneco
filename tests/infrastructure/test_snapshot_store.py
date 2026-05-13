"""
SnapshotStore のテスト

snapshots/latest.json への永続化を検証。LLM 抽出を 2 日目以降スキップする
ために、source_url をキーに前回の AnimalData を再利用できる設計。
"""

import json
from datetime import date

from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.snapshot_store import SnapshotStore


def _make_animal(
    url: str, location: str = "高知県", phone: str = "088-1234", species: str = "犬"
) -> AnimalData:
    return AnimalData(
        species=species,
        shelter_date=date(2026, 1, 5),
        location=location,
        source_url=url,
        category="adoption",
        phone=phone,
    )


class TestSnapshotStoreInitialization:
    def test_initializes_without_creating_directory(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        SnapshotStore(snapshot_dir=snapshot_dir)
        # __init__ ではディレクトリを作らない（save 時に mkdir）
        assert not snapshot_dir.exists()

    def test_initializes_without_args(self):
        store = SnapshotStore()
        assert store is not None


class TestSaveSnapshot:
    def test_save_creates_latest_json(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        animals = [_make_animal("https://example.com/a/1")]
        store.save_snapshot(animals)
        assert (snapshot_dir / "latest.json").exists()

    def test_save_creates_directory_if_missing(self, tmp_path):
        snapshot_dir = tmp_path / "deep" / "nested" / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        store.save_snapshot([_make_animal("https://example.com/a/1")])
        assert snapshot_dir.exists()

    def test_saved_json_contains_source_url_and_fields(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        store.save_snapshot([_make_animal("https://example.com/a/1", location="徳島県")])

        with open(snapshot_dir / "latest.json", encoding="utf-8") as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["source_url"] == "https://example.com/a/1"
        assert data[0]["location"] == "徳島県"

    def test_save_empty_list_creates_empty_array_file(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        store.save_snapshot([])

        with open(snapshot_dir / "latest.json", encoding="utf-8") as f:
            data = json.load(f)
        assert data == []


class TestLoadAnimalMap:
    def test_save_then_load_roundtrip(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        a = _make_animal("https://example.com/a/1", location="高知県")
        b = _make_animal("https://example.com/a/2", location="徳島県", species="猫")

        store.save_snapshot([a, b])
        loaded = store.load_animal_map()

        assert set(loaded.keys()) == {"https://example.com/a/1", "https://example.com/a/2"}
        assert loaded["https://example.com/a/1"].location == "高知県"
        assert loaded["https://example.com/a/2"].species == "猫"

    def test_load_missing_file_returns_empty_dict(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        # 保存していない状態
        assert store.load_animal_map() == {}

    def test_load_corrupt_json_returns_empty_dict(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / "latest.json").write_text("{ this is not json }", encoding="utf-8")
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        assert store.load_animal_map() == {}

    def test_load_empty_array_returns_empty_dict(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        store.save_snapshot([])
        assert store.load_animal_map() == {}


class TestLoadUrlHashMap:
    def test_returns_url_to_stable_hash(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        a = _make_animal("https://example.com/a/1", location="高知県", phone="088-1", species="犬")
        store.save_snapshot([a])

        m = store.load_url_hash_map()
        assert "https://example.com/a/1" in m
        # ハッシュが英数の40文字（SHA-1 hex）であること
        assert len(m["https://example.com/a/1"]) == 40

    def test_missing_file_returns_empty(self, tmp_path):
        snapshot_dir = tmp_path / "snapshots"
        store = SnapshotStore(snapshot_dir=snapshot_dir)
        assert store.load_url_hash_map() == {}


class TestComputeStableHash:
    def test_same_input_returns_same_hash(self):
        a = _make_animal("https://example.com/a/1", location="高知県", phone="088-1", species="犬")
        b = _make_animal("https://example.com/a/2", location="高知県", phone="088-1", species="犬")
        # source_url が違っても location/phone/species 同じならハッシュ同じ
        assert SnapshotStore.compute_stable_hash(a) == SnapshotStore.compute_stable_hash(b)

    def test_different_location_changes_hash(self):
        a = _make_animal("https://example.com/x", location="高知県")
        b = _make_animal("https://example.com/x", location="徳島県")
        assert SnapshotStore.compute_stable_hash(a) != SnapshotStore.compute_stable_hash(b)

    def test_different_species_changes_hash(self):
        a = _make_animal("https://example.com/x", species="犬")
        b = _make_animal("https://example.com/x", species="猫")
        assert SnapshotStore.compute_stable_hash(a) != SnapshotStore.compute_stable_hash(b)


class TestBackwardCompatLoadSnapshot:
    """既存 DiffDetector が呼ぶ load_snapshot() の後方互換動作"""

    def test_load_snapshot_returns_empty_list(self, tmp_path):
        """v1 では load_snapshot は空リストを維持（DiffDetector の挙動を変えない）"""
        store = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
        store.save_snapshot([_make_animal("https://example.com/a/1")])
        # DiffDetector はこのメソッドを使い続けるので空 → 全件を「新規扱い」のまま
        assert store.load_snapshot() == []
