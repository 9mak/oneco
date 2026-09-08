"""FieldQualityTracker のテスト"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.data_collector.adapters.rule_based.field_quality_tracker import (
    HISTORY_LIMIT,
    FieldDrift,
    FieldQualityTracker,
    NeverPopulatedAlert,
)


class TestFieldQualityTracker:
    def test_record_and_reload_roundtrip(self, tmp_path):
        """record → 再ロードで履歴が保存されていること"""
        path = tmp_path / "drift.yaml"
        tracker = FieldQualityTracker(path)
        tracker.record("サイトA", {"location": 0.1, "age_months": 0.5}, sample_size=20)
        tracker2 = FieldQualityTracker(path)
        history = tracker2._state["サイトA"]["location"]["history"]
        assert len(history) == 1
        assert history[0]["missing_rate"] == pytest.approx(0.1)
        assert history[0]["sample_size"] == 20

    def test_detect_drift_above_threshold(self, tmp_path):
        """前回比 +threshold 以上の急増を検出する"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"location": 0.05}, sample_size=20)
        tracker.record("サイトA", {"location": 0.85}, sample_size=20)
        drifts = tracker.detect_drifts(threshold=0.20)
        assert len(drifts) == 1
        d = drifts[0]
        assert isinstance(d, FieldDrift)
        assert d.site_name == "サイトA"
        assert d.field == "location"
        assert d.prev_rate == pytest.approx(0.05)
        assert d.curr_rate == pytest.approx(0.85)
        assert d.delta == pytest.approx(0.80)

    def test_no_drift_for_small_change(self, tmp_path):
        """+threshold 未満の小さな変化はドリフトにしない"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"location": 0.10}, sample_size=20)
        tracker.record("サイトA", {"location": 0.15}, sample_size=20)
        assert tracker.detect_drifts(threshold=0.20) == []

    def test_no_drift_for_improvement(self, tmp_path):
        """欠損率が改善 (前回より低い) した場合はドリフトにしない"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"location": 0.80}, sample_size=20)
        tracker.record("サイトA", {"location": 0.10}, sample_size=20)
        assert tracker.detect_drifts(threshold=0.20) == []

    def test_first_run_no_drift(self, tmp_path):
        """初回 (履歴 1 件) はドリフト判定しない"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"location": 1.0}, sample_size=20)
        assert tracker.detect_drifts() == []

    def test_history_capped_at_limit(self, tmp_path):
        """履歴は HISTORY_LIMIT 件で打ち切られる"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        for i in range(HISTORY_LIMIT + 5):
            tracker.record("サイトA", {"location": 0.01 * i}, sample_size=20)
        history = tracker._state["サイトA"]["location"]["history"]
        assert len(history) == HISTORY_LIMIT

    def test_detect_drift_multiple_sites_and_fields(self, tmp_path):
        """複数 site / field のドリフトを同時に返せる"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"location": 0.0, "age_months": 0.5}, sample_size=10)
        tracker.record(
            "サイトA", {"location": 0.9, "age_months": 0.6}, sample_size=10
        )  # location は +0.9 (drift), age_months は +0.1 (drift しない)
        tracker.record("サイトB", {"size": 0.1}, sample_size=10)
        tracker.record("サイトB", {"size": 0.95}, sample_size=10)  # +0.85 drift
        drifts = tracker.detect_drifts(threshold=0.20)
        pairs = {(d.site_name, d.field) for d in drifts}
        assert pairs == {("サイトA", "location"), ("サイトB", "size")}

    def test_now_parameter_for_deterministic_timestamp(self, tmp_path):
        """now を指定するとそのタイムスタンプで記録される (テスト容易性)"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        fixed = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
        tracker.record("サイトA", {"location": 0.0}, sample_size=10, now=fixed)
        ts = tracker._state["サイトA"]["location"]["history"][0]["run_at"]
        assert "2026-05-28T12:00:00" in ts


class TestNeverPopulated:
    """T149: 初回から欠損 (never-populated) 検知のテスト"""

    def test_fires_when_last_n_runs_all_full_missing(self, tmp_path):
        """直近3回すべて100%欠損なら検知する"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        for _ in range(3):
            tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        alerts = tracker.detect_never_populated()
        assert len(alerts) == 1
        a = alerts[0]
        assert isinstance(a, NeverPopulatedAlert)
        assert a.site_name == "サイトA"
        assert a.field == "breed"
        assert a.runs_checked == 3
        assert a.missing_rate == pytest.approx(1.0)

    def test_fires_from_first_run_if_history_shorter_than_min_runs(self, tmp_path):
        """履歴が min_runs 未満でも、現有全 run が閾値以上なら初回から鳴らす"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        alerts = tracker.detect_never_populated()
        assert len(alerts) == 1
        assert alerts[0].runs_checked == 1

    def test_no_alert_if_one_of_recent_runs_below_threshold(self, tmp_path):
        """直近 N 回のうち1回でも欠損率が閾値未満なら検知しない (=直っている)"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        tracker.record("サイトA", {"breed": 0.2}, sample_size=10)
        assert tracker.detect_never_populated() == []

    def test_ledger_not_provided_suppresses_alert(self, tmp_path):
        """台帳で false と宣言された field は 100%欠損でも検知しない"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        for _ in range(3):
            tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        alerts = tracker.detect_never_populated(provided_fields={"サイトA": {"breed": False}})
        assert alerts == []

    def test_suppression_window_blocks_repeat_alert(self, tmp_path):
        """suppress_days 以内の再アラートは抑制される"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        base = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
        for _ in range(3):
            tracker.record("サイトA", {"breed": 1.0}, sample_size=10, now=base)
        alerts = tracker.detect_never_populated(now=base)
        assert len(alerts) == 1
        tracker.mark_never_populated_alerted(alerts, now=base)

        # 3日後: 抑制期間内なので鳴らない
        soon = base.replace(day=4)
        assert tracker.detect_never_populated(now=soon) == []

        # 8日後: 抑制期間を過ぎたので再度鳴る
        later = base.replace(day=9)
        alerts_later = tracker.detect_never_populated(now=later)
        assert len(alerts_later) == 1

    def test_recovering_field_does_not_alert(self, tmp_path):
        """一度100%欠損でも直近が改善していれば鳴らさない (drift 検知の役目と分離)"""
        tracker = FieldQualityTracker(tmp_path / "drift.yaml")
        tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        tracker.record("サイトA", {"breed": 1.0}, sample_size=10)
        tracker.record("サイトA", {"breed": 0.0}, sample_size=10)
        assert tracker.detect_never_populated() == []
