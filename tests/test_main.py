"""CLI エントリーポイントのテスト"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

from src.data_collector.__main__ import main
from src.data_collector.orchestration.collector_service import CollectionResult


class TestCLI:
    """CLI エントリーポイントのテストケース"""

    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_success_exits_with_zero(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class
    ):
        """成功時に終了コード 0 で終了することを確認"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=True,
            total_collected=10,
            new_count=2,
            updated_count=1,
            deleted_count=0,
            errors=[],
            execution_time_seconds=5.0
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行し、sys.exit をキャッチ
        with pytest.raises(SystemExit) as exc_info:
            main()

        # 終了コード 0 を確認
        assert exc_info.value.code == 0

    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_failure_exits_with_one(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class
    ):
        """失敗時に終了コード 1 で終了することを確認"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=False,
            errors=["Test error"],
            execution_time_seconds=1.0
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行し、sys.exit をキャッチ
        with pytest.raises(SystemExit) as exc_info:
            main()

        # 終了コード 1 を確認
        assert exc_info.value.code == 1

    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_initializes_all_components(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class
    ):
        """すべてのコンポーネントが初期化されることを確認（高知+LLMサイト群）"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=True,
            total_collected=0,
            errors=[],
            execution_time_seconds=0.1
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行
        with pytest.raises(SystemExit):
            main()

        # 各コンポーネントが初期化されたことを確認
        mock_kochi_adapter_class.assert_called_once()
        mock_snapshot_store_class.assert_called_once()
        mock_diff_detector_class.assert_called_once()
        mock_output_writer_class.assert_called_once()
        mock_notification_client_class.assert_called_once()
        # CollectorServiceは高知+LLMサイト分で複数回呼ばれる
        assert mock_collector_service_class.call_count >= 1

    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_calls_run_collection(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class
    ):
        """run_collection() が呼ばれることを確認"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=True,
            total_collected=0,
            errors=[],
            execution_time_seconds=0.1
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行
        with pytest.raises(SystemExit):
            main()

        # run_collection() が高知+LLMサイト分で呼ばれたことを確認
        assert mock_service.run_collection.call_count >= 1

    @patch('src.data_collector.__main__.logging.basicConfig')
    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_configures_logging(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class,
        mock_logging_config
    ):
        """ロギングが設定されることを確認"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=True,
            total_collected=0,
            errors=[],
            execution_time_seconds=0.1
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行
        with pytest.raises(SystemExit):
            main()

        # logging.basicConfig が呼ばれたことを確認
        mock_logging_config.assert_called_once()


class TestCLIWithDatabase:
    """DATABASE_URL 設定時の CLI テストケース"""

    @patch.dict('os.environ', {'DATABASE_URL': 'postgresql+asyncpg://user:pass@localhost/test'})
    @patch('src.data_collector.__main__.DatabaseConnection')
    @patch('src.data_collector.__main__.AnimalRepository')
    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_initializes_database_when_url_set(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class,
        mock_repository_class,
        mock_db_connection_class
    ):
        """DATABASE_URL 設定時に DatabaseConnection が初期化されることを確認"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=True,
            total_collected=0,
            errors=[],
            execution_time_seconds=0.1
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行
        with pytest.raises(SystemExit):
            main()

        # DatabaseConnection が初期化されたことを確認
        mock_db_connection_class.assert_called_once()

    @patch.dict('os.environ', {}, clear=True)
    @patch('src.data_collector.__main__.CollectorService')
    @patch('src.data_collector.__main__.KochiAdapter')
    @patch('src.data_collector.__main__.SnapshotStore')
    @patch('src.data_collector.__main__.DiffDetector')
    @patch('src.data_collector.__main__.OutputWriter')
    @patch('src.data_collector.__main__.NotificationClient')
    def test_main_skips_database_when_url_not_set(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_kochi_adapter_class,
        mock_collector_service_class
    ):
        """DATABASE_URL 未設定時は repository=None で CollectorService が作成されることを確認"""
        # モックの設定
        mock_service = Mock()
        mock_service.run_collection.return_value = CollectionResult(
            success=True,
            total_collected=0,
            errors=[],
            execution_time_seconds=0.1
        )
        mock_collector_service_class.return_value = mock_service

        # main() を実行
        with pytest.raises(SystemExit):
            main()

        # CollectorService が repository=None で呼ばれたことを確認
        call_kwargs = mock_collector_service_class.call_args[1]
        assert call_kwargs.get('repository') is None
