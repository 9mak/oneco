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


def test_field_drifts_alone_triggers_warning():
    """failures 0 でも field_drifts があれば WARNING を出す (自己修復 Phase 1)"""
    from src.data_collector.adapters.rule_based.field_quality_tracker import FieldDrift

    client = MagicMock()
    drifts = [
        FieldDrift(
            site_name="サイトA", field="location", prev_rate=0.05, curr_rate=0.85, delta=0.80
        ),
    ]
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        field_drifts=drifts,
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.WARNING
    # details にドリフト情報が含まれる
    details = client.send_alert.call_args[0][2]
    assert details.get("field_drifts_count") == 1
    assert "サイトA" in details.get("field_drifts_sample", "")
    assert "location" in details.get("field_drifts_sample", "")


def test_field_drifts_empty_or_none_does_not_change_behavior():
    """field_drifts が None / 空リストなら既存の判定そのまま (後方互換)"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=10,
        total_succeeded=10,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        field_drifts=[],
    )
    client.send_alert.assert_not_called()


def test_field_drifts_alongside_failures_warning():
    """field_drifts と failure 両方ある場合も WARNING (CRITICAL 閾値未満なら)"""
    from src.data_collector.adapters.rule_based.field_quality_tracker import FieldDrift

    client = MagicMock()
    drifts = [
        FieldDrift("サイトX", "size", 0.0, 0.5, 0.5),
        FieldDrift("サイトY", "phone", 0.1, 0.9, 0.8),
    ]
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(1),
        total_sites=100,
        total_succeeded=98,
        total_failed=2,
        threshold=3,
        logger=_make_logger(),
        field_drifts=drifts,
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.WARNING
    details = client.send_alert.call_args[0][2]
    assert details["field_drifts_count"] == 2


def test_zero_count_regression_alone_triggers_warning():
    """失敗 0 でも件数ゼロ回帰があれば WARNING（サイレント破損の検知）"""
    from src.data_collector.infrastructure.site_baseline_tracker import ZeroCountRegression

    client = MagicMock()
    regs = [
        ZeroCountRegression(
            site_name="船橋市", baseline_count=21, consecutive_zero_runs=2, last_nonzero_at=None
        ),
    ]
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        zero_count_regressions=regs,
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.WARNING
    details = client.send_alert.call_args[0][2]
    assert details.get("zero_count_regressions_count") == 1
    assert "船橋市" in details.get("zero_count_regressions_sample", "")


def test_zero_count_regression_empty_does_not_change_behavior():
    """件数ゼロ回帰が None / 空なら既存判定そのまま（後方互換）"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=10,
        total_succeeded=10,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        zero_count_regressions=[],
    )
    client.send_alert.assert_not_called()


def test_auto_fix_dispatch_failure_triggers_warning():
    """失敗 0 でも auto-fix dispatch が失敗していれば WARNING を出す。
    silent failure 検知 feature が silent fail する皮肉を解消する。"""
    client = MagicMock()
    af = {"invoked": 0, "attempted": 3, "candidates": 3, "disabled": False}
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        auto_fix_result=af,
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.WARNING
    details = client.send_alert.call_args[0][2]
    assert details["auto_fix_attempted"] == 3
    assert details["auto_fix_invoked"] == 0
    assert details["auto_fix_dispatch_failures"] == 3
    # message にも分かりやすく含まれる
    assert "自己修復 dispatch 失敗" in args[1]


def test_auto_fix_all_success_no_warning():
    """auto-fix が全件 invoked = attempted なら dispatch_failures は出ず、
    他のシグナルが無ければ通知しない (info only)。"""
    client = MagicMock()
    af = {"invoked": 2, "attempted": 2, "candidates": 2, "disabled": False}
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=10,
        total_succeeded=10,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        auto_fix_result=af,
    )
    client.send_alert.assert_not_called()


def test_auto_fix_disabled_does_not_trigger_warning():
    """kill switch off は通知トリガーにしない (info purpose のみ)。"""
    client = MagicMock()
    af = {"invoked": 0, "attempted": 0, "candidates": 5, "disabled": True}
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=10,
        total_succeeded=10,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        auto_fix_result=af,
    )
    client.send_alert.assert_not_called()


def test_persistent_zero_site_alone_triggers_warning():
    """失敗0・回帰0でも長期0件(baseline無し)サイトがあれば WARNING を出す"""
    from src.data_collector.infrastructure.site_baseline_tracker import PersistentZeroSite

    client = MagicMock()
    sites = [PersistentZeroSite(site_name="長崎犬猫ネット（保健所収容）", consecutive_zero_runs=28)]
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        persistent_zero_sites=sites,
    )
    assert client.send_alert.called
    args, _ = client.send_alert.call_args
    assert args[0] == NotificationLevel.WARNING
    details = client.send_alert.call_args[0][2]
    assert details.get("persistent_zero_sites_count") == 1
    assert "長崎犬猫ネット（保健所収容）" in details.get("persistent_zero_sites_sample", "")
    assert "28" in details.get("persistent_zero_sites_sample", "")


def test_persistent_zero_site_empty_does_not_change_behavior():
    """persistent_zero_sites が None / 空なら既存判定そのまま（後方互換）"""
    client = MagicMock()
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=10,
        total_succeeded=10,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        persistent_zero_sites=[],
    )
    client.send_alert.assert_not_called()


def test_persistent_zero_site_sample_truncated():
    """長期0件サンプルは先頭10件に切り詰め、残数を表示する"""
    from src.data_collector.infrastructure.site_baseline_tracker import PersistentZeroSite

    client = MagicMock()
    sites = [PersistentZeroSite(f"サイト{i}", consecutive_zero_runs=14) for i in range(15)]
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        persistent_zero_sites=sites,
    )
    details = client.send_alert.call_args[0][2]
    assert details["persistent_zero_sites_count"] == 15
    assert "more" in details["persistent_zero_sites_sample"]


def test_zero_count_regression_sample_truncated():
    """回帰サンプルは先頭 10 件に切り詰め、残数を表示する"""
    from src.data_collector.infrastructure.site_baseline_tracker import ZeroCountRegression

    client = MagicMock()
    regs = [
        ZeroCountRegression(
            f"サイト{i}", baseline_count=5, consecutive_zero_runs=2, last_nonzero_at=None
        )
        for i in range(15)
    ]
    _send_run_summary_alert(
        notification_client=client,
        broken_tracker=_make_tracker(0),
        total_sites=209,
        total_succeeded=209,
        total_failed=0,
        threshold=3,
        logger=_make_logger(),
        zero_count_regressions=regs,
    )
    details = client.send_alert.call_args[0][2]
    assert details["zero_count_regressions_count"] == 15
    assert "more" in details["zero_count_regressions_sample"]
