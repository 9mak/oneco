"""FieldQualityTracker のテスト"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.data_collector.adapters.rule_based.field_quality_tracker import (
    HISTORY_LIMIT,
    FieldDrift,
    FieldQualityTracker,
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
