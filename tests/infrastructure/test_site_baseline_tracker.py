"""SiteBaselineTracker のユニットテスト

snapshot とは独立した永続ベースラインで「過去≥1件→今0件」のサイレント破損を
毎 run 検知できることを検証する。
"""

from __future__ import annotations

from datetime import datetime

from src.data_collector.infrastructure.site_baseline_tracker import (
    PersistentZeroSite,
    SiteBaselineTracker,
    ZeroCountRegression,
)


def _t(day: int) -> datetime:
    """テスト用の決定的タイムスタンプ"""
    return datetime(2026, 6, day, 0, 0, 0).astimezone()


class TestSiteBaselineTracker:
    def test_record_nonzero_sets_baseline(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))

        assert tracker.baseline("サイトA") == 5
        assert tracker.last_count("サイトA") == 5
        assert tracker.consecutive_zero_runs("サイトA") == 0

    def test_zero_does_not_reduce_baseline(self, tmp_path):
        """0 件を記録しても last_nonzero_count は維持される（盲点①の核心修正）"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))

        assert tracker.baseline("サイトA") == 5  # 0 で上書きされない
        assert tracker.last_count("サイトA") == 0
        assert tracker.consecutive_zero_runs("サイトA") == 1

    def test_consecutive_zero_runs_accumulate(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))
        tracker.record("サイトA", 0, now=_t(3))
        tracker.record("サイトA", 0, now=_t(4))

        assert tracker.consecutive_zero_runs("サイトA") == 3
        assert tracker.baseline("サイトA") == 5

    def test_recovery_resets_consecutive_zero(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))
        tracker.record("サイトA", 3, now=_t(3))  # 復活

        assert tracker.consecutive_zero_runs("サイトA") == 0
        assert tracker.baseline("サイトA") == 3  # last_nonzero は直近の非ゼロ
        assert tracker.high_water_count("サイトA") == 5  # high water は維持
        assert tracker.last_count("サイトA") == 3

    def test_high_water_count_tracks_max(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 8, now=_t(2))
        tracker.record("サイトA", 3, now=_t(3))

        assert tracker.high_water_count("サイトA") == 8

    def test_detect_regression_after_threshold(self, tmp_path):
        """過去≥1件のサイトが threshold 回連続 0 件 → 回帰として検知"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))
        tracker.record("サイトA", 0, now=_t(3))

        regs = tracker.detect_zero_count_regressions(threshold=2)
        assert len(regs) == 1
        assert isinstance(regs[0], ZeroCountRegression)
        assert regs[0].site_name == "サイトA"
        assert regs[0].baseline_count == 5
        assert regs[0].consecutive_zero_runs == 2

    def test_no_regression_below_threshold(self, tmp_path):
        """連続 0 が threshold 未満なら（単発の空在庫の可能性）検知しない"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))

        assert tracker.detect_zero_count_regressions(threshold=2) == []

    def test_never_seen_site_is_not_a_regression(self, tmp_path):
        """一度もデータが無いサイト（baseline 0）は回帰扱いしない（破損と区別不能なため）"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 0, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))
        tracker.record("サイトA", 0, now=_t(3))

        assert tracker.detect_zero_count_regressions(threshold=2) == []

    def test_recovered_site_is_not_a_regression(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        tracker.record("サイトA", 0, now=_t(2))
        tracker.record("サイトA", 0, now=_t(3))
        tracker.record("サイトA", 4, now=_t(4))  # 復活

        assert tracker.detect_zero_count_regressions(threshold=2) == []

    def test_persistence_across_reload(self, tmp_path):
        """状態が YAML に永続化され、別インスタンスで復元される（run 跨ぎ）"""
        path = tmp_path / "baselines.yaml"
        t1 = SiteBaselineTracker(path)
        t1.record("サイトA", 5, now=_t(1))
        t1.record("サイトA", 0, now=_t(2))

        t2 = SiteBaselineTracker(path)
        assert t2.baseline("サイトA") == 5
        assert t2.consecutive_zero_runs("サイトA") == 1
        assert t2.last_nonzero_at("サイトA") == _t(1).isoformat(timespec="seconds")

    def test_corrupt_yaml_initializes_empty(self, tmp_path):
        path = tmp_path / "baselines.yaml"
        path.write_text("{ this is: not valid: yaml ::", encoding="utf-8")
        tracker = SiteBaselineTracker(path)
        assert tracker.baseline("サイトA") == 0

    def test_unknown_site_returns_zero(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        assert tracker.baseline("未知") == 0
        assert tracker.last_count("未知") == 0
        assert tracker.consecutive_zero_runs("未知") == 0
        assert tracker.last_nonzero_at("未知") is None

    def test_multiple_sites_independent(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("健全", 10, now=_t(1))
        tracker.record("健全", 9, now=_t(2))
        tracker.record("破損", 7, now=_t(1))
        tracker.record("破損", 0, now=_t(2))
        tracker.record("破損", 0, now=_t(3))

        regs = tracker.detect_zero_count_regressions(threshold=2)
        names = {r.site_name for r in regs}
        assert names == {"破損"}

    def test_min_baseline_filter(self, tmp_path):
        """min_baseline 未満の薄いサイトは誤検知を避けるため除外できる"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("薄い", 1, now=_t(1))
        tracker.record("薄い", 0, now=_t(2))
        tracker.record("薄い", 0, now=_t(3))

        assert tracker.detect_zero_count_regressions(threshold=2, min_baseline=2) == []
        assert len(tracker.detect_zero_count_regressions(threshold=2, min_baseline=1)) == 1

    def test_detect_persistent_zero_never_seen_site(self, tmp_path):
        """一度も非ゼロ実績が無い(baseline=0)サイトが threshold 回連続0件 → 検知する。

        detect_zero_count_regressions は baseline>=1 が前提のため、導入時点
        から一貫して0件のサイト(長崎犬猫ネット等、トラッカー導入とほぼ同時期に
        サイト側が詰まったケース)を検知できない盲点があった(2026-07-24発覚)。
        """
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        for day in range(1, 16):
            tracker.record("長崎犬猫ネット", 0, now=_t(day))

        sites = tracker.detect_persistent_zero_sites(threshold=14)
        assert len(sites) == 1
        assert isinstance(sites[0], PersistentZeroSite)
        assert sites[0].site_name == "長崎犬猫ネット"
        assert sites[0].consecutive_zero_runs == 15

    def test_detect_persistent_zero_below_threshold_not_detected(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        for day in range(1, 5):
            tracker.record("新サイト", 0, now=_t(day))

        assert tracker.detect_persistent_zero_sites(threshold=14) == []

    def test_detect_persistent_zero_excludes_sites_with_baseline(self, tmp_path):
        """baseline>=1 のサイトは detect_zero_count_regressions の担当なので除外する
        (二重通知を避けるため排他的にする)"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 5, now=_t(1))
        for day in range(2, 20):
            tracker.record("サイトA", 0, now=_t(day))

        assert tracker.detect_persistent_zero_sites(threshold=14) == []
        assert len(tracker.detect_zero_count_regressions(threshold=2)) == 1

    def test_detect_persistent_zero_recovery_resets(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        for day in range(1, 15):
            tracker.record("サイトB", 0, now=_t(day))
        tracker.record("サイトB", 3, now=_t(15))  # 復活

        assert tracker.detect_persistent_zero_sites(threshold=14) == []
