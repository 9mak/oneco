"""_send_run_summary_alert のテスト

収集 run 終了時に Slack へ Warning/Critical 通知を出す判定ロジックを検証。
broken_sites の状態と全体失敗率に応じて分類される。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from src.data_collector.__main__ import _send_run_summary_alert
from src.data_collector.infrastructure.notification_client import NotificationLevel


def _make_tracker(critical_count: int) -> MagicMock:
    tracker = MagicMock()
    tracker.critical_sites.return_value = [f"サイト{i}" for i in range(critical_count)]
    return tracker


def _make_logger() -> logging.Logger:
    return logging.getLogger("test_run_summary_alert")


def test_no_failures_no_alert():
    """failures 0 / critical_sites 0 なら通知しない"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
    )
    client.send_alert.assert_not_called()


def test_few_failures_warning():
    """failure_ratio 低 + critical_sites>0 → WARNING"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(2),
        total_sites=209,
        total_succeeded=205,
        total_failed=4,  # 1.9% (< 20%)
        threshold=3,
        logger=_make_logger(),
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.WARNING


def test_high_failure_ratio_critical():
    """failure_ratio > 20% → CRITICAL"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(50),
        total_sites=100,
        total_succeeded=70,
        total_failed=30,  # 30% > 20%
        threshold=3,
        logger=_make_logger(),
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.CRITICAL


def test_all_failed_critical():
    """全件失敗 → CRITICAL"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=10,
        total_succeeded=0,
        total_failed=10,
        threshold=3,
        logger=_make_logger(),
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.CRITICAL


def test_details_include_critical_sites_sample():
    """critical_sites の先頭 10 件が details に含まれる"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(15),
        total_sites=100,
        total_succeeded=85,
        total_failed=15,
        threshold=3,
        logger=_make_logger(),
    )
    args, _ = client.send_alert.call_args
    details = args[2]
    assert "critical_sites_count" in details
    assert details["critical_sites_count"] == 15
    assert "critical_sites_sample" in details
    assert "..." in details["critical_sites_sample"]


def test_no_tracker_still_works():
    """broken_tracker=None でも total_failed>0 なら WARNING (落ちない)"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=None,
        total_sites=10,
        total_succeeded=9,
        total_failed=1,
        threshold=3,
        logger=_make_logger(),
    )
    assert client.send_alert.called


def test_zero_sites_no_alert():
    """サイト数 0 でも例外にならず通知も出さない"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=None,
        total_sites=0,
        total_succeeded=0,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
    )
    client.send_alert.assert_not_called()
