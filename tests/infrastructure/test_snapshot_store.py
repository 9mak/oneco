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


class TestLoadCountsBySiteUrlPrefix:
    """サイト別の前回件数集計

    Task #9 (snapshot 件数比較ベースの異常検出) の基盤メソッド。
    `{site_name: list_url}` から前回 snapshot の AnimalData を site 別に
    集計する。
    """

    def test_empty_snapshot_returns_zero_for_all_sites(self, tmp_path):
        """snapshot が空なら全サイト 0 件"""
        store = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
        site_urls = {
            "サイトA": "https://example.com/a/",
            "サイトB": "https://example.com/b/",
        }
        counts = store.load_counts_by_site_url_prefix(site_urls)
        assert counts == {"サイトA": 0, "サイトB": 0}

    def test_groups_animals_by_site_url_prefix(self, tmp_path):
        """source_url の前方一致でサイト別件数が集計される"""
        store = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
        store.save_snapshot(
            [
                _make_animal("https://example.com/a/page#row=0"),
                _make_animal("https://example.com/a/page#row=1"),
                _make_animal("https://example.com/a/page#row=2"),
                _make_animal("https://example.com/b/page#h3=0"),
            ]
        )
        site_urls = {
            "サイトA": "https://example.com/a/page",
            "サイトB": "https://example.com/b/page",
            "サイトC": "https://example.com/c/page",
        }
        counts = store.load_counts_by_site_url_prefix(site_urls)
        assert counts == {"サイトA": 3, "サイトB": 1, "サイトC": 0}

    def test_url_not_matching_any_site_is_ignored(self, tmp_path):
        """どの site にも一致しない source_url は無視される"""
        store = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
        store.save_snapshot(
            [
                _make_animal("https://example.com/a/page#row=0"),
                _make_animal("https://other.example.com/x/1"),
            ]
        )
        counts = store.load_counts_by_site_url_prefix({"サイトA": "https://example.com/a/page"})
        assert counts == {"サイトA": 1}

    def test_one_url_counted_only_once(self, tmp_path):
        """1 動物の URL は最初にマッチしたサイトに 1 回だけカウント

        URL prefix が重複する設計はしないが、念のため辞書順 first-match の
        挙動を固定しておく (break による早期離脱)。
        """
        store = SnapshotStore(snapshot_dir=tmp_path / "snapshots")
        store.save_snapshot([_make_animal("https://example.com/a/page#row=0")])
        # 「サイトA」「サイトA子」の両方が prefix match する作為的なケース
        counts = store.load_counts_by_site_url_prefix(
            {"サイトA": "https://example.com/a/page", "サイトA子": "https://example.com/a/"}
        )
        # dict 反復順は挿入順なので最初の "サイトA" が 1、"サイトA子" は 0
        assert sum(counts.values()) == 1
