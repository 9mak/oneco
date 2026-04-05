"""
notification-manager 監視機能のテスト

Task 8.1-8.3: メトリクス記録、アラート、ログのテスト
"""

from unittest.mock import patch

import pytest

from src.notification_manager.infrastructure.monitoring import (
    AlertLevel,
    AlertManager,
    AuditLogger,
    MetricsCollector,
    MetricType,
)


class TestMetricsCollector:
    """メトリクス記録のテスト (Task 8.1)"""

    @pytest.fixture
    def collector(self):
        """テスト用メトリクスコレクター"""
        return MetricsCollector()

    def test_record_notification_sent(self, collector):
        """通知送信数を記録"""
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        assert collector.get_count(MetricType.NOTIFICATIONS_SENT) == 1

    def test_record_multiple_notifications(self, collector):
        """複数回の通知送信を記録"""
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        assert collector.get_count(MetricType.NOTIFICATIONS_SENT) == 3

    def test_record_api_response_time(self, collector):
        """API応答時間を記録"""
        collector.record_timing(MetricType.API_RESPONSE_TIME, 0.5)
        collector.record_timing(MetricType.API_RESPONSE_TIME, 1.0)
        collector.record_timing(MetricType.API_RESPONSE_TIME, 1.5)

        stats = collector.get_timing_stats(MetricType.API_RESPONSE_TIME)
        assert stats["count"] == 3
        assert stats["avg"] == 1.0
        assert stats["p50"] == 1.0

    def test_record_matching_time(self, collector):
        """マッチング処理時間を記録"""
        collector.record_timing(MetricType.MATCHING_TIME, 0.1)
        stats = collector.get_timing_stats(MetricType.MATCHING_TIME)
        assert stats["count"] == 1

    def test_record_error_count(self, collector):
        """エラー数を記録"""
        collector.record(MetricType.ERRORS, 1)
        assert collector.get_count(MetricType.ERRORS) == 1

    def test_calculate_error_rate(self, collector):
        """エラー率を計算"""
        # 10件送信、2件エラー
        for _ in range(10):
            collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        collector.record(MetricType.ERRORS, 1)
        collector.record(MetricType.ERRORS, 1)

        error_rate = collector.get_error_rate()
        assert error_rate == 0.2  # 20%

    def test_get_hourly_stats(self, collector):
        """1時間あたりの統計を取得"""
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)

        stats = collector.get_hourly_stats()
        assert "notifications_sent" in stats
        assert stats["notifications_sent"] == 2

    def test_reset_metrics(self, collector):
        """メトリクスをリセット"""
        collector.record(MetricType.NOTIFICATIONS_SENT, 1)
        collector.reset()
        assert collector.get_count(MetricType.NOTIFICATIONS_SENT) == 0


class TestAlertManager:
    """アラート機能のテスト (Task 8.2)"""

    @pytest.fixture
    def alert_manager(self):
        """テスト用アラートマネージャー"""
        return AlertManager(
            warning_error_rate=0.05,
            critical_error_rate=0.20,
            warning_response_time_p95=5.0,
        )

    def test_no_alert_when_healthy(self, alert_manager):
        """正常時はアラートなし"""
        alerts = alert_manager.check_thresholds(
            error_rate=0.01,
            response_time_p95=1.0,
        )
        assert len(alerts) == 0

    def test_warning_alert_on_error_rate(self, alert_manager):
        """エラー率警告閾値でアラート"""
        alerts = alert_manager.check_thresholds(
            error_rate=0.10,
            response_time_p95=1.0,
        )
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert "エラー率" in alerts[0].message

    def test_critical_alert_on_error_rate(self, alert_manager):
        """エラー率緊急閾値でアラート"""
        alerts = alert_manager.check_thresholds(
            error_rate=0.25,
            response_time_p95=1.0,
        )
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.CRITICAL

    def test_warning_alert_on_response_time(self, alert_manager):
        """応答時間警告閾値でアラート"""
        alerts = alert_manager.check_thresholds(
            error_rate=0.01,
            response_time_p95=6.0,
        )
        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert "応答時間" in alerts[0].message

    def test_multiple_alerts(self, alert_manager):
        """複数アラートの同時発生"""
        alerts = alert_manager.check_thresholds(
            error_rate=0.25,
            response_time_p95=6.0,
        )
        assert len(alerts) == 2


class TestAuditLogger:
    """監査ログのテスト (Task 8.3)"""

    @pytest.fixture
    def audit_logger(self):
        """テスト用監査ロガー"""
        return AuditLogger()

    def test_log_authentication_failure(self, audit_logger):
        """認証エラーをログ記録"""
        with patch("logging.Logger.warning") as mock_log:
            audit_logger.log_auth_failure(
                source="api",
                reason="invalid_api_key",
                ip_address="192.168.1.1",
            )
            mock_log.assert_called_once()
            call_args = mock_log.call_args[0][0]
            assert "AUTH_FAILURE" in call_args

    def test_log_signature_verification_failure(self, audit_logger):
        """署名検証失敗をログ記録"""
        with patch("logging.Logger.warning") as mock_log:
            audit_logger.log_signature_failure(
                source="line_webhook",
                ip_address="192.168.1.1",
            )
            mock_log.assert_called_once()
            call_args = mock_log.call_args[0][0]
            assert "SIGNATURE_FAILURE" in call_args

    def test_log_database_error(self, audit_logger):
        """データベースエラーをログ記録"""
        with patch("logging.Logger.error") as mock_log:
            audit_logger.log_db_error(
                operation="insert",
                error="Connection refused",
            )
            mock_log.assert_called_once()
            call_args = mock_log.call_args[0][0]
            assert "DB_ERROR" in call_args

    def test_log_line_api_error(self, audit_logger):
        """LINE APIエラーをログ記録"""
        with patch("logging.Logger.error") as mock_log:
            audit_logger.log_line_api_error(
                operation="push_message",
                error_code="429",
                error_message="Rate limited",
            )
            mock_log.assert_called_once()

    def test_log_personal_data_access(self, audit_logger):
        """個人データアクセスをログ記録"""
        with patch("logging.Logger.info") as mock_log:
            audit_logger.log_personal_data_access(
                user_id=123,
                action="read_preferences",
                accessed_by="system",
            )
            mock_log.assert_called_once()
            call_args = mock_log.call_args[0][0]
            assert "PERSONAL_DATA_ACCESS" in call_args
