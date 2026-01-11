"""
SnapshotStore のユニットテスト

スナップショットの読み込み・保存ロジックを検証します。
"""

import json
import pytest
from pathlib import Path
from datetime import date
from tempfile import TemporaryDirectory

from src.data_collector.infrastructure.snapshot_store import SnapshotStore
from src.data_collector.domain.models import AnimalData


class TestSnapshotStoreInitialization:
    """SnapshotStore 初期化のテスト"""

    def test_snapshot_store_creates_directory(self):
        """SnapshotStore 初期化時にディレクトリが自動作成されること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)
            assert snapshot_dir.exists()

    def test_snapshot_store_with_existing_directory(self):
        """既存ディレクトリでも正常に初期化できること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            snapshot_dir.mkdir()
            store = SnapshotStore(snapshot_dir=snapshot_dir)
            assert snapshot_dir.exists()


class TestSnapshotStoreLoadSnapshot:
    """スナップショット読み込みのテスト"""

    def test_load_snapshot_returns_empty_list_when_file_not_exists(self):
        """スナップショットファイルが存在しない場合は空リストを返すこと"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)
            result = store.load_snapshot()
            assert result == []

    def test_load_snapshot_returns_animal_data_list(self):
        """スナップショットファイルから AnimalData リストを読み込めること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            snapshot_dir.mkdir()
            snapshot_file = snapshot_dir / "latest.json"

            # テストデータ作成
            test_data = [
                {
                    "species": "犬",
                    "sex": "男の子",
                    "age_months": 24,
                    "color": "茶色",
                    "size": "中型",
                    "shelter_date": "2026-01-05",
                    "location": "高知県動物愛護センター",
                    "phone": "088-123-4567",
                    "image_urls": ["https://example.com/image1.jpg"],
                    "source_url": "https://example.com/animals/001"
                }
            ]
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(test_data, f, ensure_ascii=False)

            store = SnapshotStore(snapshot_dir=snapshot_dir)
            result = store.load_snapshot()

            assert len(result) == 1
            assert isinstance(result[0], AnimalData)
            assert result[0].species == "犬"
            assert result[0].sex == "男の子"
            assert result[0].age_months == 24

    def test_load_snapshot_with_multiple_animals(self):
        """複数の AnimalData を正しく読み込めること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            snapshot_dir.mkdir()
            snapshot_file = snapshot_dir / "latest.json"

            test_data = [
                {
                    "species": "犬",
                    "shelter_date": "2026-01-05",
                    "source_url": "https://example.com/animals/001"
                },
                {
                    "species": "猫",
                    "shelter_date": "2026-01-06",
                    "source_url": "https://example.com/animals/002"
                }
            ]
            with open(snapshot_file, "w", encoding="utf-8") as f:
                json.dump(test_data, f, ensure_ascii=False)

            store = SnapshotStore(snapshot_dir=snapshot_dir)
            result = store.load_snapshot()

            assert len(result) == 2
            assert result[0].species == "犬"
            assert result[1].species == "猫"

    def test_load_snapshot_raises_on_invalid_json(self):
        """不正な JSON ファイルの場合は例外をスローすること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            snapshot_dir.mkdir()
            snapshot_file = snapshot_dir / "latest.json"

            with open(snapshot_file, "w", encoding="utf-8") as f:
                f.write("{ invalid json }")

            store = SnapshotStore(snapshot_dir=snapshot_dir)
            with pytest.raises(json.JSONDecodeError):
                store.load_snapshot()


class TestSnapshotStoreSaveSnapshot:
    """スナップショット保存のテスト"""

    def test_save_snapshot_creates_file(self):
        """スナップショットがファイルに保存されること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)

            animal = AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/animals/001"
            )
            store.save_snapshot([animal])

            snapshot_file = snapshot_dir / "latest.json"
            assert snapshot_file.exists()

    def test_save_snapshot_writes_correct_json(self):
        """正しい JSON 形式でスナップショットが保存されること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)

            animal = AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/animals/001"
            )
            store.save_snapshot([animal])

            snapshot_file = snapshot_dir / "latest.json"
            with open(snapshot_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)

            assert len(saved_data) == 1
            assert saved_data[0]["species"] == "犬"
            assert saved_data[0]["sex"] == "男の子"
            assert saved_data[0]["age_months"] == 24

    def test_save_snapshot_uses_ensure_ascii_false(self):
        """日本語がエスケープされずに保存されること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)

            animal = AnimalData(
                species="犬",
                location="高知県動物愛護センター",
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/animals/001"
            )
            store.save_snapshot([animal])

            snapshot_file = snapshot_dir / "latest.json"
            with open(snapshot_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 日本語がそのまま含まれていること（Unicode エスケープされていない）
            assert "高知県動物愛護センター" in content

    def test_save_snapshot_uses_indent(self):
        """インデントされた形式で保存されること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)

            animal = AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/animals/001"
            )
            store.save_snapshot([animal])

            snapshot_file = snapshot_dir / "latest.json"
            with open(snapshot_file, "r", encoding="utf-8") as f:
                content = f.read()

            # インデントが含まれていること
            assert "\n" in content
            assert "  " in content

    def test_save_snapshot_overwrites_existing_file(self):
        """既存のスナップショットファイルを上書きすること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)

            # 最初のデータを保存
            animal1 = AnimalData(
                species="犬",
                shelter_date=date(2026, 1, 5),
                source_url="https://example.com/animals/001"
            )
            store.save_snapshot([animal1])

            # 新しいデータで上書き
            animal2 = AnimalData(
                species="猫",
                shelter_date=date(2026, 1, 6),
                source_url="https://example.com/animals/002"
            )
            store.save_snapshot([animal2])

            # 読み込んで確認
            result = store.load_snapshot()
            assert len(result) == 1
            assert result[0].species == "猫"


class TestSnapshotStoreRoundTrip:
    """保存と読み込みの往復テスト"""

    def test_save_and_load_roundtrip(self):
        """保存したデータが正しく読み込めること"""
        with TemporaryDirectory() as tmp_dir:
            snapshot_dir = Path(tmp_dir) / "snapshots"
            store = SnapshotStore(snapshot_dir=snapshot_dir)

            original_animals = [
                AnimalData(
                    species="犬",
                    sex="男の子",
                    age_months=24,
                    color="茶色",
                    size="中型",
                    shelter_date=date(2026, 1, 5),
                    location="高知県動物愛護センター",
                    phone="088-123-4567",
                    image_urls=["https://example.com/image1.jpg"],
                    source_url="https://example.com/animals/001"
                ),
                AnimalData(
                    species="猫",
                    sex="女の子",
                    age_months=12,
                    shelter_date=date(2026, 1, 6),
                    source_url="https://example.com/animals/002"
                )
            ]

            store.save_snapshot(original_animals)
            loaded_animals = store.load_snapshot()

            assert len(loaded_animals) == 2

            # 各フィールドを比較
            assert loaded_animals[0].species == original_animals[0].species
            assert loaded_animals[0].sex == original_animals[0].sex
            assert loaded_animals[0].age_months == original_animals[0].age_months
            assert loaded_animals[0].shelter_date == original_animals[0].shelter_date
            assert str(loaded_animals[0].source_url) == str(original_animals[0].source_url)

            assert loaded_animals[1].species == original_animals[1].species
            assert loaded_animals[1].sex == original_animals[1].sex
