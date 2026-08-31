"""SiteBaselineTracker のユニットテスト

snapshot とは独立した永続ベースラインで「過去≥1件→今0件」のサイレント破損を
毎 run 検知できることを検証する。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.data_collector.infrastructure.site_baseline_tracker import (
    PersistentZeroSite,
    SiteBaselineTracker,
    SuddenDropRegression,
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


class TestDetectSuddenDrops:
    """detect_sudden_drops: 直近1回の収集での急減検知 (T107)

    detect_zero_count_regressions は「複数run連続で0件」しか検知できず、
    大分65→32件のような「0にはならないが1回で激減」する部分的な件数低下を
    捉えられない盲点があった。ここでは前回 last_count と今回件数を比較し、
    1 run で 50% 以上減少したサイトを検知する。

    呼び出しタイミングは record() より前 (state がまだ「前回」の値を
    保持している間) であること。
    """

    def test_detects_drop_at_exactly_50_percent(self, tmp_path):
        """大分65→32型 (比率 0.49、50%以上減) を検知する"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("大分県動物愛護センター", 65, now=_t(1))

        drops = tracker.detect_sudden_drops({"大分県動物愛護センター": 32})

        assert len(drops) == 1
        assert isinstance(drops[0], SuddenDropRegression)
        assert drops[0].site_name == "大分県動物愛護センター"
        assert drops[0].previous_count == 65
        assert drops[0].current_count == 32
        assert drops[0].drop_ratio == pytest.approx((65 - 32) / 65)

    def test_no_detection_when_drop_is_under_50_percent(self, tmp_path):
        """前回比 50% 未満の減少 (自然な譲渡進行) は検知しない

        長野県譲渡猫の実測比率 0.60 相当 (40%減) を想定
        """
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("長野県譲渡猫", 10, now=_t(1))

        drops = tracker.detect_sudden_drops({"長野県譲渡猫": 6})

        assert drops == []

    def test_exactly_at_threshold_boundary_is_detected(self, tmp_path):
        """ちょうど50%減 (境界値) は検知される (閾値は以上)"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 10, now=_t(1))

        drops = tracker.detect_sudden_drops({"サイトA": 5})

        assert len(drops) == 1
        assert drops[0].drop_ratio == pytest.approx(0.5)

    def test_just_under_threshold_boundary_not_detected(self, tmp_path):
        """50%未満 (49%減) は検知しない"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 100, now=_t(1))

        drops = tracker.detect_sudden_drops({"サイトA": 51})

        assert drops == []

    def test_complete_zero_is_excluded(self, tmp_path):
        """完全ゼロは既存の detect_zero_count_regressions の担当なので対象外"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 10, now=_t(1))

        drops = tracker.detect_sudden_drops({"サイトA": 0})

        assert drops == []

    def test_small_previous_count_excluded_by_default(self, tmp_path):
        """前回件数が母数の薄いサイト (デフォルト閾値未満) は誤検知回避のため対象外"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("薄いサイト", 2, now=_t(1))  # 前回2件

        drops = tracker.detect_sudden_drops({"薄いサイト": 0})  # 対象外(current<=0)

        assert drops == []

        tracker.record("薄いサイト2", 2, now=_t(1))
        drops2 = tracker.detect_sudden_drops({"薄いサイト2": 1})  # 50%減だが母数薄い

        assert drops2 == []

    def test_min_previous_count_threshold_is_configurable(self, tmp_path):
        """min_previous_count を引き下げれば薄いサイトも検知対象にできる"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 2, now=_t(1))

        drops = tracker.detect_sudden_drops({"サイトA": 1}, min_previous_count=1)

        assert len(drops) == 1

    def test_no_previous_run_is_not_a_drop(self, tmp_path):
        """初回収集 (前回データなし) は減少として扱わない"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")

        drops = tracker.detect_sudden_drops({"新規サイト": 5})

        assert drops == []

    def test_increase_is_not_a_drop(self, tmp_path):
        """前回より増えている場合は検知しない"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 10, now=_t(1))

        drops = tracker.detect_sudden_drops({"サイトA": 20})

        assert drops == []

    def test_custom_drop_ratio_threshold(self, tmp_path):
        """drop_ratio_threshold を変更すればより緩い/厳しい閾値で検知できる"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 10, now=_t(1))

        # 30%減はデフォルト閾値では検知されない
        assert tracker.detect_sudden_drops({"サイトA": 7}) == []
        # 閾値を0.3に緩めると検知される
        drops = tracker.detect_sudden_drops({"サイトA": 7}, drop_ratio_threshold=0.3)
        assert len(drops) == 1

    def test_multiple_sites_only_flags_the_dropping_one(self, tmp_path):
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("健全", 10, now=_t(1))
        tracker.record("急減", 65, now=_t(1))

        drops = tracker.detect_sudden_drops({"健全": 9, "急減": 32})

        assert len(drops) == 1
        assert drops[0].site_name == "急減"

    def test_called_before_record_reflects_previous_run(self, tmp_path):
        """record() より前に呼ぶことで「前回」の値と比較できる (呼び出し順序の契約確認)"""
        tracker = SiteBaselineTracker(tmp_path / "baselines.yaml")
        tracker.record("サイトA", 65, now=_t(1))

        current_counts = {"サイトA": 32}
        drops = tracker.detect_sudden_drops(current_counts)
        tracker.record("サイトA", current_counts["サイトA"], now=_t(2))

        assert len(drops) == 1
        # record() 後は last_count が今回値に上書きされるので前回比は取れない
        assert tracker.last_count("サイトA") == 32
