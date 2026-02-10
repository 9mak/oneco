"""
notification-manager 監視機能

メトリクス記録、アラート管理、監査ログを提供する。

Requirements: 6.1-6.6, 7.3, 7.6
"""

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


class MetricType(str, Enum):
    """メトリクスの種類"""

    NOTIFICATIONS_SENT = "notifications_sent"
    ERRORS = "errors"
    API_RESPONSE_TIME = "api_response_time"
    MATCHING_TIME = "matching_time"


class AlertLevel(str, Enum):
    """アラートレベル"""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """アラート情報"""

    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsCollector:
    """
    メトリクス収集クラス

    Task 8.1: メトリクス記録の実装
    - 1時間あたりの通知送信数の記録
    - API応答時間（p50、p95、p99）の記録
    - エラー発生率の記録
    - マッチング処理時間の記録
    """

    def __init__(self) -> None:
        self._counts: Dict[MetricType, int] = defaultdict(int)
        self._timings: Dict[MetricType, List[float]] = defaultdict(list)

    def record(self, metric_type: MetricType, value: int) -> None:
        """カウントメトリクスを記録"""
        self._counts[metric_type] += value

    def record_timing(self, metric_type: MetricType, seconds: float) -> None:
        """タイミングメトリクスを記録"""
        self._timings[metric_type].append(seconds)

    def get_count(self, metric_type: MetricType) -> int:
        """カウントメトリクスを取得"""
        return self._counts[metric_type]

    def get_timing_stats(self, metric_type: MetricType) -> Dict[str, float]:
        """タイミングメトリクスの統計を取得"""
        values = self._timings[metric_type]
        if not values:
            return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0}

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": count,
            "avg": statistics.mean(sorted_values),
            "p50": self._percentile(sorted_values, 50),
            "p95": self._percentile(sorted_values, 95),
            "p99": self._percentile(sorted_values, 99),
        }

    def _percentile(self, sorted_values: List[float], percentile: int) -> float:
        """パーセンタイルを計算"""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_values) else f
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    def get_error_rate(self) -> float:
        """エラー率を計算"""
        total = self._counts[MetricType.NOTIFICATIONS_SENT]
        errors = self._counts[MetricType.ERRORS]
        if total == 0:
            return 0.0
        return errors / total

    def get_hourly_stats(self) -> Dict[str, int]:
        """1時間あたりの統計を取得"""
        return {
            "notifications_sent": self._counts[MetricType.NOTIFICATIONS_SENT],
            "errors": self._counts[MetricType.ERRORS],
        }

    def reset(self) -> None:
        """メトリクスをリセット"""
        self._counts.clear()
        self._timings.clear()


class AlertManager:
    """
    アラート管理クラス

    Task 8.2: アラート機能の実装
    - エラー率閾値（5%で警告、20%で緊急）によるアラート
    - API応答時間閾値（p95 > 5秒）によるアラート
    """

    def __init__(
        self,
        warning_error_rate: float = 0.05,
        critical_error_rate: float = 0.20,
        warning_response_time_p95: float = 5.0,
    ) -> None:
        self.warning_error_rate = warning_error_rate
        self.critical_error_rate = critical_error_rate
        self.warning_response_time_p95 = warning_response_time_p95

    def check_thresholds(
        self,
        error_rate: float,
        response_time_p95: float,
    ) -> List[Alert]:
        """閾値をチェックしてアラートを生成"""
        alerts: List[Alert] = []

        # エラー率チェック
        if error_rate >= self.critical_error_rate:
            alerts.append(
                Alert(
                    level=AlertLevel.CRITICAL,
                    message=f"エラー率が緊急閾値を超過: {error_rate:.1%} (閾値: {self.critical_error_rate:.1%})",
                )
            )
        elif error_rate >= self.warning_error_rate:
            alerts.append(
                Alert(
                    level=AlertLevel.WARNING,
                    message=f"エラー率が警告閾値を超過: {error_rate:.1%} (閾値: {self.warning_error_rate:.1%})",
                )
            )

        # 応答時間チェック
        if response_time_p95 > self.warning_response_time_p95:
            alerts.append(
                Alert(
                    level=AlertLevel.WARNING,
                    message=f"API応答時間(p95)が閾値を超過: {response_time_p95:.2f}秒 (閾値: {self.warning_response_time_p95:.2f}秒)",
                )
            )

        return alerts


class AuditLogger:
    """
    監査ログクラス

    Task 8.3: エラーログと監査ログの実装
    - 認証エラー（無効APIキー、署名検証失敗）のログ記録
    - データベース接続エラーのログ記録
    - LINE API接続エラーのログ記録
    - 個人データアクセスの監査ログ
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("notification_manager.audit")

    def log_auth_failure(
        self,
        source: str,
        reason: str,
        ip_address: Optional[str] = None,
    ) -> None:
        """認証エラーをログ記録"""
        self._logger.warning(
            f"AUTH_FAILURE | source={source} | reason={reason} | ip={ip_address}"
        )

    def log_signature_failure(
        self,
        source: str,
        ip_address: Optional[str] = None,
    ) -> None:
        """署名検証失敗をログ記録"""
        self._logger.warning(
            f"SIGNATURE_FAILURE | source={source} | ip={ip_address}"
        )

    def log_db_error(
        self,
        operation: str,
        error: str,
    ) -> None:
        """データベースエラーをログ記録"""
        self._logger.error(
            f"DB_ERROR | operation={operation} | error={error}"
        )

    def log_line_api_error(
        self,
        operation: str,
        error_code: str,
        error_message: str,
    ) -> None:
        """LINE APIエラーをログ記録"""
        self._logger.error(
            f"LINE_API_ERROR | operation={operation} | code={error_code} | message={error_message}"
        )

    def log_personal_data_access(
        self,
        user_id: int,
        action: str,
        accessed_by: str,
    ) -> None:
        """個人データアクセスをログ記録"""
        self._logger.info(
            f"PERSONAL_DATA_ACCESS | user_id={user_id} | action={action} | accessed_by={accessed_by}"
        )
