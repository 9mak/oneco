"""scripts/field_ledger_report.py の単体テスト (T148/T149)。"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from field_ledger_report import (  # noqa: E402
    UndeclaredMissingPair,
    find_undeclared_full_missing,
    load_drift_state,
)


class TestFindUndeclaredFullMissing:
    def test_flags_pair_at_100pct_not_declared(self):
        provided = {}
        drift_state = {
            "サイトA": {
                "breed": {
                    "history": [{"missing_rate": 1.0, "sample_size": 10}],
                }
            }
        }
        pairs = find_undeclared_full_missing(provided, drift_state)
        assert pairs == [
            UndeclaredMissingPair(
                site_name="サイトA", field="breed", latest_missing_rate=1.0, sample_size=10
            )
        ]

    def test_declared_not_provided_is_excluded(self):
        provided = {"サイトA": {"breed": False}}
        drift_state = {
            "サイトA": {
                "breed": {
                    "history": [{"missing_rate": 1.0, "sample_size": 10}],
                }
            }
        }
        assert find_undeclared_full_missing(provided, drift_state) == []

    def test_below_threshold_not_flagged(self):
        provided = {}
        drift_state = {
            "サイトA": {
                "breed": {
                    "history": [{"missing_rate": 0.5, "sample_size": 10}],
                }
            }
        }
        assert find_undeclared_full_missing(provided, drift_state) == []

    def test_uses_latest_history_entry_only(self):
        provided = {}
        drift_state = {
            "サイトA": {
                "breed": {
                    "history": [
                        {"missing_rate": 1.0, "sample_size": 10},
                        {"missing_rate": 0.0, "sample_size": 10},
                    ],
                }
            }
        }
        # 最新 (2件目) は 0% なので対象外
        assert find_undeclared_full_missing(provided, drift_state) == []

    def test_no_history_is_skipped(self):
        provided = {}
        drift_state = {"サイトA": {"breed": {"history": []}}}
        assert find_undeclared_full_missing(provided, drift_state) == []

    def test_custom_threshold(self):
        provided = {}
        drift_state = {
            "サイトA": {
                "breed": {
                    "history": [{"missing_rate": 0.9, "sample_size": 10}],
                }
            }
        }
        assert find_undeclared_full_missing(provided, drift_state, threshold=1.0) == []
        pairs = find_undeclared_full_missing(provided, drift_state, threshold=0.9)
        assert len(pairs) == 1


class TestLoadDriftState:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        assert load_drift_state(tmp_path / "does_not_exist.yaml") == {}

    def test_loads_yaml_dict(self, tmp_path: Path):
        path = tmp_path / "drift.yaml"
        path.write_text(
            "サイトA:\n  breed:\n    history:\n      - missing_rate: 1.0\n        sample_size: 5\n",
            encoding="utf-8",
        )
        state = load_drift_state(path)
        assert state["サイトA"]["breed"]["history"][0]["missing_rate"] == 1.0

    def test_non_dict_yaml_returns_empty_dict(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("just a string", encoding="utf-8")
        assert load_drift_state(path) == {}
