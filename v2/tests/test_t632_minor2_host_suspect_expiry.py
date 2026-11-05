"""W006 T632 の小さな直し (2) repair_gate: ホスト障害の疑いの期限。ネットワークなし。"""

from __future__ import annotations

from collector import repair_gate


# --- (2) repair_gate: ホスト障害の疑いの期限 ---------------------------------------------
def test_host_suspect_expires_after_the_limit():
    state = {"sources": {}, "repair_hosts": {}}
    rows = [{"slug": s, "host": "a.jp", "status": "failed"} for s in ("a1", "a2")]
    repair_gate.refresh_hosts(state, rows, "2026-11-01")
    assert "a.jp" in state["repair_hosts"]
    # 期限の前日までは残る。新しく a3 が崩れても呼ばない（障害が広がっている最中）
    state["sources"] = {s: {"last_status": "failed", "last_date": "2026-11-07"} for s in ("a1", "a2")}
    rows3 = [*rows, {"slug": "a3", "host": "a.jp", "status": "failed"}]
    repair_gate.refresh_hosts(state, rows3, "2026-11-07")
    assert "a.jp" in state["repair_hosts"]
    # 期限の日には外れる。a1・a2 が読めないまま 1 週間たったなら障害ではなく作り直しなので、後から崩れた a3 も人に回る
    repair_gate.refresh_hosts(state, rows3, "2026-11-08")
    assert "a.jp" not in state["repair_hosts"]
    assert repair_gate.skip_reason(state, "a3", "a.jp", "2026-11-08", {"kind": "parser"}, "u", "parser", None, "sha", "ctx") is None


def test_host_suspect_is_set_again_by_a_new_simultaneous_failure_after_expiry():
    state = {"sources": {}, "repair_hosts": {"a.jp": {"since": "2026-11-01", "slugs": ["a1", "a2"]}}}
    rows = [{"slug": s, "host": "a.jp", "status": "failed"} for s in ("a1", "a2", "c1", "c2")]
    repair_gate.refresh_hosts(state, rows, "2026-11-09")
    assert state["repair_hosts"]["a.jp"]["since"] == "2026-11-09"   # 古い疑いは外れ、今日新たに 2 件で立て直す


