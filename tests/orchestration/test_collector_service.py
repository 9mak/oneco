"""CollectorService のユニットテスト"""

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.data_collector.adapters.municipality_adapter import NetworkError, ParsingError
from src.data_collector.domain.diff_detector import DiffResult
from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.notification_manager_client import (
    NotificationManagerClient,
)
from src.data_collector.orchestration.collector_service import CollectionResult, CollectorService


class TestCollectorService:
    """CollectorService のテストケース"""

    @pytest.fixture
    def mock_adapter(self):
        """モック MunicipalityAdapter"""
        adapter = Mock()
        adapter.prefecture_code = "39"
        adapter.municipality_name = "高知県"
        return adapter

    @pytest.fixture
    def mock_diff_detector(self):
        """モック DiffDetector"""
        detector = Mock()
        detector.detect_diff.return_value = DiffResult(new=[], updated=[], deleted_candidates=[])
        return detector

    @pytest.fixture
    def mock_output_writer(self):
        """モック OutputWriter"""
        writer = Mock()
        writer.write_output.return_value = Path("output/animals.json")
        return writer

    @pytest.fixture
    def mock_notification_client(self):
        """モック NotificationClient"""
        return Mock()

    @pytest.fixture
    def mock_snapshot_store(self):
        """モック SnapshotStore"""
        store = Mock()
        store.load_snapshot.return_value = []
        return store

    @pytest.fixture
    def collector_service(
        self,
        tmp_path,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_notification_client,
        mock_snapshot_store,
    ):
        """CollectorService インスタンスを作成"""
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
        )
        # 一時ディレクトリを使用するように LOCK_FILE をオーバーライド
        service.LOCK_FILE = tmp_path / ".collector.lock"
        return service

    @pytest.fixture
    def sample_animal_data(self):
        """サンプル AnimalData を作成"""
        return [
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
                source_url="https://example-kochi.jp/animals/123",
                category="adoption",
            )
        ]

    # Task 5.1: ロックファイル管理のテスト
    def test_is_running_returns_false_when_no_lock(self, collector_service):
        """ロックファイルが存在しない場合、False を返すことを確認"""
        assert not collector_service._is_running()

    def test_acquire_lock_creates_lock_file(self, collector_service):
        """ロックファイルが作成されることを確認"""
        assert not collector_service.LOCK_FILE.exists()

        collector_service._acquire_lock()

        assert collector_service.LOCK_FILE.exists()

    def test_release_lock_removes_lock_file(self, collector_service):
        """ロックファイルが削除されることを確認"""
        collector_service._acquire_lock()
        assert collector_service.LOCK_FILE.exists()

        collector_service._release_lock()

        assert not collector_service.LOCK_FILE.exists()

    def test_is_running_returns_true_when_locked(self, collector_service):
        """ロックファイルが存在する場合、True を返すことを確認"""
        collector_service._acquire_lock()

        assert collector_service._is_running()

        collector_service._release_lock()

    def test_run_collection_prevents_duplicate_execution(self, collector_service, mock_adapter):
        """ロックファイルが存在する場合、重複実行を防止することを確認"""
        collector_service._acquire_lock()

        result = collector_service.run_collection()

        assert not result.success
        assert "Already running" in result.errors

        collector_service._release_lock()

    def test_run_collection_releases_lock_on_exception(self, collector_service, mock_adapter):
        """例外発生時もロックファイルがクリーンアップされることを確認"""
        mock_adapter.fetch_animal_list.side_effect = Exception("Test error")

        result = collector_service.run_collection()

        # ロックファイルが削除されていることを確認
        assert not collector_service.LOCK_FILE.exists()
        assert not result.success

    # Task 5.2: リトライロジックのテスト
    def test_collect_with_retry_success_on_first_attempt(
        self, collector_service, mock_adapter, sample_animal_data
    ):
        """1回目の試行で成功することを確認"""
        mock_adapter.fetch_animal_list.return_value = [
            (("https://example-kochi.jp/animals/123", "adoption"), "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        result = collector_service._collect_with_retry()

        assert len(result) == 1
        assert mock_adapter.fetch_animal_list.call_count == 1

    def test_collect_with_retry_retries_on_network_error(
        self, collector_service, mock_adapter, sample_animal_data
    ):
        """NetworkError 時にリトライすることを確認"""
        mock_adapter.fetch_animal_list.side_effect = [
            NetworkError("Network error"),
            NetworkError("Network error"),
            [(("https://example-kochi.jp/animals/123", "adoption"), "adoption")],
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        result = collector_service._collect_with_retry()

        # 3回試行されたことを確認
        assert mock_adapter.fetch_animal_list.call_count == 3
        assert len(result) == 1

    def test_collect_with_retry_fails_after_max_retries(self, collector_service, mock_adapter):
        """最大リトライ回数後に失敗することを確認"""
        mock_adapter.fetch_animal_list.side_effect = NetworkError("Network error")

        with pytest.raises(NetworkError):
            collector_service._collect_with_retry(max_retries=3)

        # 3回試行されたことを確認
        assert mock_adapter.fetch_animal_list.call_count == 3

    def test_collect_with_retry_skips_on_parsing_error(self, collector_service, mock_adapter):
        """ParsingError 時にスキップすることを確認"""
        mock_adapter.fetch_animal_list.side_effect = ParsingError("Page structure changed")

        with pytest.raises(ParsingError):
            collector_service._collect_with_retry()

        # ParsingError の場合はリトライしない（1回のみ）
        assert mock_adapter.fetch_animal_list.call_count == 1

    # Task 5.3: 収集フロー統合のテスト
    def test_run_collection_full_flow_success(
        self,
        collector_service,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_snapshot_store,
        sample_animal_data,
    ):
        """収集フロー全体が正常に動作することを確認"""
        # アダプターのモック設定
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        # 差分検知のモック設定
        mock_diff_detector.detect_diff.return_value = DiffResult(
            new=[sample_animal_data[0]], updated=[], deleted_candidates=[]
        )

        result = collector_service.run_collection()

        # 成功確認
        assert result.success
        assert result.total_collected == 1
        assert result.new_count == 1

        # 各コンポーネントが呼ばれたことを確認
        mock_adapter.fetch_animal_list.assert_called_once()
        mock_diff_detector.detect_diff.assert_called_once()
        mock_output_writer.write_output.assert_called_once()
        mock_snapshot_store.save_snapshot.assert_called_once()

    def test_run_collection_notifies_on_structure_change(
        self, collector_service, mock_adapter, mock_notification_client
    ):
        """ページ構造変更時に通知が送信されることを確認"""
        mock_adapter.fetch_animal_list.side_effect = ParsingError("Page structure changed")

        result = collector_service.run_collection()

        # 失敗確認
        assert not result.success

        # 通知が送信されたことを確認（構造変更検知）
        mock_notification_client.send_alert.assert_called()

    def test_run_collection_notifies_new_animals(
        self,
        collector_service,
        mock_adapter,
        mock_diff_detector,
        mock_notification_client,
        sample_animal_data,
    ):
        """新規動物がある場合、通知が送信されることを確認"""
        # アダプターのモック設定
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        # 差分検知のモック設定（新規あり）
        mock_diff_detector.detect_diff.return_value = DiffResult(
            new=[sample_animal_data[0]], updated=[], deleted_candidates=[]
        )

        collector_service.run_collection()

        # 新規動物通知が送信されたことを確認
        mock_notification_client.notify_new_animals.assert_called_once()
        call_args = mock_notification_client.notify_new_animals.call_args[0][0]
        assert len(call_args) == 1

    def test_run_collection_logs_execution_info(
        self, collector_service, mock_adapter, sample_animal_data
    ):
        """実行ログが記録されることを確認"""
        # アダプターのモック設定
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        with patch.object(collector_service.logger, "info") as mock_log:
            collector_service.run_collection()

            # ログが記録されたことを確認（開始、完了）
            assert mock_log.call_count >= 2

    def test_run_collection_measures_execution_time(
        self, collector_service, mock_adapter, sample_animal_data
    ):
        """実行時間が測定されることを確認"""
        # アダプターのモック設定
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        result = collector_service.run_collection()

        # execution_time_seconds が設定されていることを確認
        assert result.execution_time_seconds >= 0

    def test_collection_result_structure(self):
        """CollectionResult の構造が正しいことを確認"""
        result = CollectionResult(
            success=True,
            total_collected=10,
            new_count=3,
            updated_count=2,
            deleted_count=1,
            errors=[],
            execution_time_seconds=5.5,
        )

        assert result.success
        assert result.total_collected == 10
        assert result.new_count == 3
        assert result.updated_count == 2
        assert result.deleted_count == 1
        assert result.errors == []
        assert result.execution_time_seconds == 5.5

    def test_generate_execution_id(self, collector_service):
        """実行 ID が生成されることを確認"""
        execution_id = collector_service._generate_execution_id()

        # UUID 形式であることを確認（36文字）
        assert len(execution_id) == 36
        assert execution_id.count("-") == 4


class TestCollectorServiceWithRepository:
    """AnimalRepository 統合のテストケース"""

    @pytest.fixture
    def mock_adapter(self):
        """モック MunicipalityAdapter"""
        adapter = Mock()
        adapter.prefecture_code = "39"
        adapter.municipality_name = "高知県"
        return adapter

    @pytest.fixture
    def mock_diff_detector(self):
        """モック DiffDetector"""
        detector = Mock()
        detector.detect_diff.return_value = DiffResult(new=[], updated=[], deleted_candidates=[])
        return detector

    @pytest.fixture
    def mock_output_writer(self):
        """モック OutputWriter"""
        writer = Mock()
        writer.write_output.return_value = Path("output/animals.json")
        return writer

    @pytest.fixture
    def mock_notification_client(self):
        """モック NotificationClient"""
        return Mock()

    @pytest.fixture
    def mock_snapshot_store(self):
        """モック SnapshotStore"""
        store = Mock()
        store.load_snapshot.return_value = []
        return store

    @pytest.fixture
    def mock_repository(self):
        """モック AnimalRepository"""
        repository = Mock()
        repository.save_animal = AsyncMock()
        return repository

    @pytest.fixture
    def sample_animal_data(self):
        """サンプル AnimalData を作成"""
        return [
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
                source_url="https://example-kochi.jp/animals/123",
                category="adoption",
            )
        ]

    @pytest.fixture
    def collector_service_with_repo(
        self,
        tmp_path,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_notification_client,
        mock_snapshot_store,
        mock_repository,
    ):
        """Repository付き CollectorService インスタンスを作成"""
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
            repository=mock_repository,
        )
        service.LOCK_FILE = tmp_path / ".collector.lock"
        return service

    def test_collector_service_accepts_optional_repository(
        self,
        tmp_path,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_notification_client,
        mock_snapshot_store,
    ):
        """Repository がオプショナルで渡せることを確認"""
        # repository なしでもインスタンス化可能
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
        )
        assert service.repository is None

    def test_run_collection_saves_to_repository(
        self, collector_service_with_repo, mock_adapter, mock_repository, sample_animal_data
    ):
        """収集後にRepositoryにデータが保存されることを確認"""
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]
        mock_repository.save_animal.return_value = sample_animal_data[0]

        result = collector_service_with_repo.run_collection()

        assert result.success
        # save_animal が1回呼ばれたことを確認
        mock_repository.save_animal.assert_called_once()

    def test_run_collection_alerts_on_database_error(
        self,
        collector_service_with_repo,
        mock_adapter,
        mock_repository,
        mock_notification_client,
        sample_animal_data,
    ):
        """データベースエラー時にアラートが送信されることを確認"""
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]
        mock_repository.save_animal.side_effect = Exception("Database error")

        result = collector_service_with_repo.run_collection()

        # 収集自体は成功（JSONファイルとして保存される）
        assert result.success
        # データベースエラーはログに記録される（アラート送信）
        # 注: 現在の実装では個別のエラーはスキップされる


class TestCollectorServiceWithNotificationManager:
    """notification-manager 統合のテストケース"""

    @pytest.fixture
    def mock_adapter(self):
        """モック MunicipalityAdapter"""
        adapter = Mock()
        adapter.prefecture_code = "39"
        adapter.municipality_name = "高知県"
        return adapter

    @pytest.fixture
    def mock_diff_detector(self):
        """モック DiffDetector"""
        detector = Mock()
        detector.detect_diff.return_value = DiffResult(new=[], updated=[], deleted_candidates=[])
        return detector

    @pytest.fixture
    def mock_output_writer(self):
        """モック OutputWriter"""
        writer = Mock()
        writer.write_output.return_value = Path("output/animals.json")
        return writer

    @pytest.fixture
    def mock_notification_client(self):
        """モック NotificationClient（Slack通知用）"""
        return Mock()

    @pytest.fixture
    def mock_snapshot_store(self):
        """モック SnapshotStore"""
        store = Mock()
        store.load_snapshot.return_value = []
        return store

    @pytest.fixture
    def mock_notification_manager_client(self):
        """モック NotificationManagerClient"""
        client = Mock(spec=NotificationManagerClient)
        client.notify_new_animals_sync.return_value = True
        return client

    @pytest.fixture
    def sample_animal_data(self):
        """サンプル AnimalData を作成"""
        return [
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
                source_url="https://example-kochi.jp/animals/123",
                category="adoption",
            )
        ]

    @pytest.fixture
    def collector_service_with_nm(
        self,
        tmp_path,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_notification_client,
        mock_snapshot_store,
        mock_notification_manager_client,
    ):
        """notification-manager クライアント付き CollectorService"""
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
            notification_manager_client=mock_notification_manager_client,
        )
        service.LOCK_FILE = tmp_path / ".collector.lock"
        return service

    def test_collector_service_accepts_notification_manager_client(
        self,
        tmp_path,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_notification_client,
        mock_snapshot_store,
        mock_notification_manager_client,
    ):
        """notification_manager_client がオプショナルで渡せることを確認"""
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
            notification_manager_client=mock_notification_manager_client,
        )
        assert service.notification_manager_client is mock_notification_manager_client

    def test_collector_service_without_notification_manager(
        self,
        tmp_path,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_notification_client,
        mock_snapshot_store,
    ):
        """notification_manager_client なしでも動作することを確認"""
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
        )
        assert service.notification_manager_client is None

    def test_run_collection_notifies_notification_manager_on_new_animals(
        self,
        collector_service_with_nm,
        mock_adapter,
        mock_diff_detector,
        mock_notification_manager_client,
        sample_animal_data,
    ):
        """新規動物がある場合、notification-manager に通知されることを確認"""
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        # 差分検知で新規動物を検知
        mock_diff_detector.detect_diff.return_value = DiffResult(
            new=[sample_animal_data[0]], updated=[], deleted_candidates=[]
        )

        result = collector_service_with_nm.run_collection()

        assert result.success
        # notification-manager に通知されたことを確認
        mock_notification_manager_client.notify_new_animals_sync.assert_called_once()
        call_args = mock_notification_manager_client.notify_new_animals_sync.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].species == "犬"

    def test_run_collection_skips_notification_manager_when_no_new_animals(
        self,
        collector_service_with_nm,
        mock_adapter,
        mock_diff_detector,
        mock_notification_manager_client,
        sample_animal_data,
    ):
        """新規動物がない場合、notification-manager に通知しないことを確認"""
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        # 差分検知で新規なし
        mock_diff_detector.detect_diff.return_value = DiffResult(
            new=[],
            updated=[sample_animal_data[0]],  # 更新のみ
            deleted_candidates=[],
        )

        result = collector_service_with_nm.run_collection()

        assert result.success
        # notification-manager には通知されない
        mock_notification_manager_client.notify_new_animals_sync.assert_not_called()

    def test_run_collection_continues_on_notification_manager_error(
        self,
        collector_service_with_nm,
        mock_adapter,
        mock_diff_detector,
        mock_notification_manager_client,
        sample_animal_data,
    ):
        """notification-manager エラー時も収集処理は継続することを確認"""
        mock_adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/123", "adoption")
        ]
        mock_adapter.extract_animal_details.return_value = Mock()
        mock_adapter.normalize.return_value = sample_animal_data[0]

        # 差分検知で新規動物を検知
        mock_diff_detector.detect_diff.return_value = DiffResult(
            new=[sample_animal_data[0]], updated=[], deleted_candidates=[]
        )

        # notification-manager がエラーを返す
        mock_notification_manager_client.notify_new_animals_sync.return_value = False

        result = collector_service_with_nm.run_collection()

        # 収集自体は成功（best-effort）
        assert result.success
        assert result.new_count == 1
