"""CLI エントリーポイントのテスト"""

from unittest.mock import patch

import pytest

from src.data_collector.__main__ import main


@pytest.fixture(autouse=True)
def stub_sites_runners(tmp_path, monkeypatch):
    """main() 内の sites.yaml 走査関数を全テストで stub し、
    本物の broken_tracker / output_writer 等に副作用が漏れないようにする。

    監視状態ファイル (broken_sites / site_baselines / field_quality_drift) の
    書き込み先を tmp に逃がし、テストが repo 内 data/ を汚染しないようにする
    (MagicMock 化された SnapshotStore は int() で 1 を返すため、パスを逃がさ
    ないと全実サイトのベースラインが data/site_baselines.yaml に書かれる)。

    デフォルトの戻り値 (0, 0, [], []) は成功サイト・失敗サイトとも 0 件、
    つまり「収集対象サイトが実質ゼロ」の中立ケース。exit code に影響する
    総失敗率 / 全滅判定を個別テストで検証したい場合は、返り値の Mock を
    `stub_sites_runners` 経由で上書きする。
    """
    monkeypatch.setenv("BROKEN_SITES_PATH", str(tmp_path / "broken_sites.yaml"))
    monkeypatch.setenv("SITE_BASELINE_PATH", str(tmp_path / "site_baselines.yaml"))
    monkeypatch.setenv("FIELD_QUALITY_DRIFT_PATH", str(tmp_path / "field_quality_drift.yaml"))
    with (
        patch(
            "src.data_collector.__main__.run_rule_based_sites",
            return_value=(0, 0, [], []),
        ) as mock_rule_based,
        patch(
            "src.data_collector.__main__.run_llm_sites",
            return_value=(0, 0, [], []),
        ) as mock_llm,
    ):
        yield mock_rule_based, mock_llm


class TestCLI:
    """CLI エントリーポイントのテストケース"""

    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_success_exits_with_zero(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
    ):
        """成功時 (失敗サイト 0 件) に終了コード 0 で終了することを確認"""
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0

    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_failure_exits_with_one(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        stub_sites_runners,
    ):
        """全サイト失敗（成功 0・失敗 >0）時に終了コード 1 で終了することを確認

        高知県専用の直列パス（旧 KochiAdapter 個別呼び出し）は sites.yaml +
        KochiApcAdapter ラッパー経由の rule-based 経路に統合済み。高知県だけが
        単発でこけても他サイトが動いていれば全体失敗率で吸収されるべきで、
        「1 サイトの失敗が即ジョブ全体を failure にする」非対称な旧挙動が
        再発していないことをここで検証する。
        """
        mock_rule_based, _mock_llm = stub_sites_runners
        mock_rule_based.return_value = (0, 1, [], [])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_single_site_failure_does_not_fail_whole_job(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        stub_sites_runners,
    ):
        """他サイトが成功していれば、1 サイトの失敗だけでは exit 0 のままであることを確認

        高知県 (kochi-apc.com) のような単一サイトのネットワーク起因失敗が
        207 サイト中の 1 件に過ぎない場合、デフォルト閾値 (ONECO_MAX_FAIL_RATIO=1.0)
        の下では失敗率超過にならず、ジョブ全体は成功扱いになるべき。
        """
        mock_rule_based, _mock_llm = stub_sites_runners
        mock_rule_based.return_value = (206, 1, [], [f"site-{i}" for i in range(206)])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0

    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_initializes_all_components(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
    ):
        """すべてのコンポーネントが初期化されることを確認"""
        with pytest.raises(SystemExit):
            main()

        mock_snapshot_store_class.assert_called_once()
        mock_diff_detector_class.assert_called_once()
        mock_output_writer_class.assert_called_once()
        mock_notification_client_class.assert_called_once()

    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_calls_site_runners(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        stub_sites_runners,
    ):
        """rule-based / LLM 両方のサイトランナーが呼ばれることを確認"""
        mock_rule_based, mock_llm = stub_sites_runners

        with pytest.raises(SystemExit):
            main()

        mock_rule_based.assert_called_once()
        mock_llm.assert_called_once()

    @patch("src.data_collector.__main__.logging.basicConfig")
    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_configures_logging(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_logging_config,
    ):
        """ロギングが設定されることを確認"""
        with pytest.raises(SystemExit):
            main()

        mock_logging_config.assert_called_once()


class TestCLIWithDatabase:
    """DATABASE_URL 設定時の CLI テストケース"""

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/test"})
    @patch("src.data_collector.__main__.DatabaseConnection")
    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_initializes_database_when_url_set(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        mock_db_connection_class,
    ):
        """DATABASE_URL 設定時に DatabaseConnection が初期化されることを確認"""
        with pytest.raises(SystemExit):
            main()

        mock_db_connection_class.assert_called_once()

    @patch("src.data_collector.__main__.SnapshotStore")
    @patch("src.data_collector.__main__.DiffDetector")
    @patch("src.data_collector.__main__.OutputWriter")
    @patch("src.data_collector.__main__.NotificationClient")
    def test_main_skips_database_when_url_not_set(
        self,
        mock_notification_client_class,
        mock_output_writer_class,
        mock_diff_detector_class,
        mock_snapshot_store_class,
        stub_sites_runners,
        monkeypatch,
    ):
        """DATABASE_URL 未設定時は db_connection=None でサイトランナーが呼ばれることを確認"""
        # DATABASE_URL のみ削除する。os.environ を clear=True で全消去すると
        # autouse fixture が設定した SITE_BASELINE_PATH 等まで消え、main() が
        # repo 内 data/ に状態ファイルを書いてしまうため delenv で限定する。
        monkeypatch.delenv("DATABASE_URL", raising=False)
        mock_rule_based, _mock_llm = stub_sites_runners

        with pytest.raises(SystemExit):
            main()

        assert mock_rule_based.call_args.kwargs["db_connection"] is None
