"""BrokenSitesTracker のテスト

連続失敗サイトの追跡・YAML 永続化を検証。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker


@pytest.fixture
def tracker_path(tmp_path: Path) -> Path:
    return tmp_path / "broken_sites.yaml"


class TestBrokenSitesTracker:
    def test_record_failure_increments_counter(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        t.record_failure("サイトA", "ParsingError: missing")
        t.record_failure("サイトA", "ParsingError: missing")
        assert t.consecutive_failures("サイトA") == 2

    def test_record_success_resets_counter(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        t.record_failure("サイトA", "err1")
        t.record_failure("サイトA", "err2")
        t.record_success("サイトA")
        assert t.consecutive_failures("サイトA") == 0

    def test_persisted_to_yaml(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        t.record_failure("サイトA", "ParsingError")
        # ファイルに永続化されている
        assert tracker_path.exists()
        data = yaml.safe_load(tracker_path.read_text())
        assert "サイトA" in data
        assert data["サイトA"]["consecutive_failures"] == 1

    def test_loads_existing_state(self, tracker_path: Path):
        # 事前に YAML 配置
        existing = {
            "サイトB": {
                "consecutive_failures": 5,
                "last_error": "old error",
                "last_failed_at": "2026-05-14T10:00:00+09:00",
            }
        }
        tracker_path.write_text(yaml.safe_dump(existing, allow_unicode=True))
        t = BrokenSitesTracker(tracker_path)
        assert t.consecutive_failures("サイトB") == 5

    def test_critical_sites_with_threshold(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        for _ in range(3):
            t.record_failure("サイトA", "err")
        t.record_failure("サイトB", "err")  # 1回だけ
        critical = t.critical_sites(threshold=3)
        assert "サイトA" in critical
        assert "サイトB" not in critical

    def test_handles_missing_file_gracefully(self, tracker_path: Path):
        # ファイルなしから start
        assert not tracker_path.exists()
        t = BrokenSitesTracker(tracker_path)
        assert t.consecutive_failures("サイトA") == 0

    def test_handles_corrupt_yaml(self, tracker_path: Path):
        tracker_path.write_text("not: valid: yaml: at: all: [[[")
        # 空状態で初期化されること
        t = BrokenSitesTracker(tracker_path)
        assert t.consecutive_failures("サイトA") == 0


class TestShouldSkipGracePeriod:
    """`should_skip` の grace_days による再チェック動作

    Task #12: 自動スキップ対象サイトを最終失敗から grace_days 経過後に
    再試行できる仕組み。サイト側 / adapter が修正されたら次の grace 期間
    満了時に自動復活する。
    """

    def _now(self) -> datetime:
        return datetime(2026, 6, 1, 12, 0, 0).astimezone()

    def test_below_threshold_never_skipped(self, tracker_path: Path):
        """連続失敗が閾値未満なら常に skip=False"""
        t = BrokenSitesTracker(tracker_path)
        t.record_failure("サイトA", "fail")
        t.record_failure("サイトA", "fail")
        # 連続 2 回失敗、閾値 3
        assert not t.should_skip("サイトA", threshold=3, grace_days=7, now=self._now())

    def test_at_threshold_skipped_within_grace(self, tracker_path: Path):
        """閾値以上 かつ grace 期間内なら skip=True"""
        t = BrokenSitesTracker(tracker_path)
        for _ in range(3):
            t.record_failure("サイトB", "fail")
        # 失敗直後にチェック (grace_days=7 だが経過 0 日)
        assert t.should_skip("サイトB", threshold=3, grace_days=7)

    def test_at_threshold_recheck_after_grace_expired(self, tracker_path: Path):
        """grace 期間経過後は skip=False で再試行される"""
        t = BrokenSitesTracker(tracker_path)
        for _ in range(3):
            t.record_failure("サイトC", "fail")
        # last_failed_at を 10 日前に書き換え (yaml に直接 inject)
        old_failed_at = (self._now() - timedelta(days=10)).isoformat(timespec="seconds")
        t._state["サイトC"]["last_failed_at"] = old_failed_at
        t._save()
        # 再ロードして確認
        t2 = BrokenSitesTracker(tracker_path)
        assert not t2.should_skip("サイトC", threshold=3, grace_days=7, now=self._now()), (
            "10 日前の失敗 + grace_days=7 → 再試行する"
        )

    def test_grace_days_none_skips_forever(self, tracker_path: Path):
        """grace_days=None なら閾値以上は常に skip"""
        t = BrokenSitesTracker(tracker_path)
        for _ in range(3):
            t.record_failure("サイトD", "fail")
        old_failed_at = (self._now() - timedelta(days=365)).isoformat(timespec="seconds")
        t._state["サイトD"]["last_failed_at"] = old_failed_at
        assert t.should_skip("サイトD", threshold=3, grace_days=None, now=self._now()), (
            "grace_days=None なら 365 日経過しても skip"
        )

    def test_missing_last_failed_at_skips_safely(self, tracker_path: Path):
        """last_failed_at が未記録なら安全側で skip=True (情報不足時)"""
        t = BrokenSitesTracker(tracker_path)
        # 直接 state を作って consecutive_failures だけセット
        t._state["サイトE"] = {"consecutive_failures": 5}
        assert t.should_skip("サイトE", threshold=3, grace_days=7)

    def test_record_success_resets_skip(self, tracker_path: Path):
        """record_success でカウンタリセットされ skip 解除される"""
        t = BrokenSitesTracker(tracker_path)
        for _ in range(5):
            t.record_failure("サイトF", "fail")
        assert t.should_skip("サイトF", threshold=3, grace_days=7)
        t.record_success("サイトF")
        assert not t.should_skip("サイトF", threshold=3, grace_days=7)


class TestLastFailedAt:
    """`last_failed_at` API の挙動"""

    def test_returns_none_when_unrecorded(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        assert t.last_failed_at("サイトA") is None

    def test_returns_datetime_after_record_failure(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        t.record_failure("サイトA", "fail")
        ts = t.last_failed_at("サイトA")
        assert ts is not None
        assert isinstance(ts, datetime)

    def test_returns_none_when_timestamp_corrupt(self, tracker_path: Path):
        t = BrokenSitesTracker(tracker_path)
        t._state["サイトA"] = {"consecutive_failures": 1, "last_failed_at": "not a date"}
        assert t.last_failed_at("サイトA") is None
