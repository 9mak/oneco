"""BrokenSitesTracker のテスト

連続失敗サイトの追跡・YAML 永続化を検証。
"""

from __future__ import annotations

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
