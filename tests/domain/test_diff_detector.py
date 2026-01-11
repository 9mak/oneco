"""
DiffDetector のユニットテスト

前回スナップショットと今回データの差分検知ロジックを検証します。
"""

import pytest
from datetime import date
from unittest.mock import Mock

from src.data_collector.domain.diff_detector import DiffDetector, DiffResult
from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.snapshot_store import SnapshotStore


def create_animal(
    source_url: str,
    species: str = "犬",
    sex: str = "男の子",
    age_months: int = 24,
    color: str = "茶色"
) -> AnimalData:
    """テスト用 AnimalData を作成するヘルパー"""
    return AnimalData(
        species=species,
        sex=sex,
        age_months=age_months,
        color=color,
        shelter_date=date(2026, 1, 5),
        source_url=source_url
    )


class TestDiffResult:
    """DiffResult モデルのテスト"""

    def test_diff_result_default_values(self):
        """DiffResult のデフォルト値が空リストであること"""
        result = DiffResult()
        assert result.new == []
        assert result.updated == []
        assert result.deleted_candidates == []

    def test_diff_result_with_values(self):
        """DiffResult に値を設定できること"""
        animal = create_animal("https://example.com/001")
        result = DiffResult(
            new=[animal],
            updated=[],
            deleted_candidates=["https://example.com/002"]
        )
        assert len(result.new) == 1
        assert result.new[0].source_url == animal.source_url
        assert len(result.deleted_candidates) == 1


class TestDiffDetectorInitialization:
    """DiffDetector 初期化のテスト"""

    def test_diff_detector_requires_snapshot_store(self):
        """DiffDetector は SnapshotStore を必要とすること"""
        mock_store = Mock(spec=SnapshotStore)
        detector = DiffDetector(snapshot_store=mock_store)
        assert detector.snapshot_store == mock_store


class TestDiffDetectorNewDetection:
    """新規検知のテスト"""

    def test_detect_new_animals(self):
        """前回スナップショットに存在しない URL を新規として検知すること"""
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = []  # 空のスナップショット

        detector = DiffDetector(snapshot_store=mock_store)
        current_data = [
            create_animal("https://example.com/001"),
            create_animal("https://example.com/002")
        ]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 2
        assert len(result.updated) == 0
        assert len(result.deleted_candidates) == 0

    def test_detect_new_animal_with_existing_data(self):
        """既存データがある場合でも新規を正しく検知すること"""
        existing_animal = create_animal("https://example.com/001")
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = [existing_animal]

        detector = DiffDetector(snapshot_store=mock_store)
        current_data = [
            existing_animal,  # 既存
            create_animal("https://example.com/002")  # 新規
        ]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 1
        assert str(result.new[0].source_url) == "https://example.com/002"


class TestDiffDetectorUpdateDetection:
    """更新検知のテスト"""

    def test_detect_updated_animal(self):
        """既存 URL の内容変更を更新として検知すること"""
        old_animal = create_animal("https://example.com/001", sex="男の子")
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = [old_animal]

        detector = DiffDetector(snapshot_store=mock_store)
        updated_animal = create_animal("https://example.com/001", sex="女の子")
        current_data = [updated_animal]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 0
        assert len(result.updated) == 1
        assert result.updated[0].sex == "女の子"

    def test_detect_updated_age(self):
        """年齢の変更を更新として検知すること"""
        old_animal = create_animal("https://example.com/001", age_months=12)
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = [old_animal]

        detector = DiffDetector(snapshot_store=mock_store)
        updated_animal = create_animal("https://example.com/001", age_months=24)
        current_data = [updated_animal]

        result = detector.detect_diff(current_data)

        assert len(result.updated) == 1
        assert result.updated[0].age_months == 24

    def test_no_update_when_data_unchanged(self):
        """データが変更されていない場合は更新として検知しないこと"""
        animal = create_animal("https://example.com/001")
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = [animal]

        detector = DiffDetector(snapshot_store=mock_store)
        # 同じデータで新しいインスタンスを作成
        same_animal = create_animal("https://example.com/001")
        current_data = [same_animal]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 0
        assert len(result.updated) == 0
        assert len(result.deleted_candidates) == 0


class TestDiffDetectorDeleteDetection:
    """削除候補検知のテスト"""

    def test_detect_deleted_candidates(self):
        """今回リストに存在しない URL を削除候補として検知すること"""
        old_animal = create_animal("https://example.com/001")
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = [old_animal]

        detector = DiffDetector(snapshot_store=mock_store)
        current_data = []  # 空リスト

        result = detector.detect_diff(current_data)

        assert len(result.new) == 0
        assert len(result.updated) == 0
        assert len(result.deleted_candidates) == 1
        assert "https://example.com/001" in result.deleted_candidates

    def test_detect_multiple_deleted_candidates(self):
        """複数の削除候補を正しく検知すること"""
        old_animals = [
            create_animal("https://example.com/001"),
            create_animal("https://example.com/002"),
            create_animal("https://example.com/003")
        ]
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = old_animals

        detector = DiffDetector(snapshot_store=mock_store)
        current_data = [create_animal("https://example.com/002")]  # 002 のみ残存

        result = detector.detect_diff(current_data)

        assert len(result.deleted_candidates) == 2
        assert "https://example.com/001" in result.deleted_candidates
        assert "https://example.com/003" in result.deleted_candidates


class TestDiffDetectorEmptySnapshot:
    """空スナップショット時のテスト"""

    def test_empty_snapshot_all_new(self):
        """初回実行時（空スナップショット）は全件が新規になること"""
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = []

        detector = DiffDetector(snapshot_store=mock_store)
        current_data = [
            create_animal("https://example.com/001"),
            create_animal("https://example.com/002"),
            create_animal("https://example.com/003")
        ]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 3
        assert len(result.updated) == 0
        assert len(result.deleted_candidates) == 0


class TestDiffDetectorComplexScenario:
    """複合シナリオのテスト"""

    def test_mixed_new_updated_deleted(self):
        """新規・更新・削除候補が混在するケース"""
        old_animals = [
            create_animal("https://example.com/001", sex="男の子"),  # 更新される
            create_animal("https://example.com/002"),  # そのまま
            create_animal("https://example.com/003")  # 削除候補
        ]
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = old_animals

        detector = DiffDetector(snapshot_store=mock_store)
        current_data = [
            create_animal("https://example.com/001", sex="女の子"),  # 更新
            create_animal("https://example.com/002"),  # 変更なし
            create_animal("https://example.com/004")  # 新規
        ]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 1
        assert str(result.new[0].source_url) == "https://example.com/004"

        assert len(result.updated) == 1
        assert str(result.updated[0].source_url) == "https://example.com/001"

        assert len(result.deleted_candidates) == 1
        assert "https://example.com/003" in result.deleted_candidates

    def test_url_as_unique_key(self):
        """source_url がユニークキーとして機能すること"""
        # 同じ内容でも URL が異なれば別個体として扱う
        old_animal = create_animal("https://example.com/001", species="犬")
        mock_store = Mock(spec=SnapshotStore)
        mock_store.load_snapshot.return_value = [old_animal]

        detector = DiffDetector(snapshot_store=mock_store)
        # 同じ内容だが URL が異なる
        new_animal = create_animal("https://example.com/002", species="犬")
        current_data = [new_animal]

        result = detector.detect_diff(current_data)

        assert len(result.new) == 1  # 新規として検知
        assert len(result.deleted_candidates) == 1  # 001 は削除候補
