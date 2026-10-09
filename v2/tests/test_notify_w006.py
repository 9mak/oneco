"""W006 T608: 通知の dedup（初回・3 日継続・復旧の 3 種だけ）。"""

import json

from collector import notify as nt
from collector.state import load_state, save_state, update_sources


def _row(status="failed", kind="parser", host="a.jp", slug="a", count=0, err="0 頭で empty_text も無い"):
    info = {"kind": kind, "status": None, "host": host} if status in ("failed", "ambiguous_empty") else None
    return {"slug": slug, "name": "A市", "status": status, "count": count, "error": err, "error_info": info, "repair": None}


def _day(state, date, rows):
    update_sources(state, rows, date)
    return nt.build_message(rows, state, date), nt.decide(rows, state)


def _sent(state, events, date):
    nt._mark_notified(state, events, date)


def test_first_then_silent_then_day3_then_every_7(tmp_path):
    state = {"sources": {}, "breaker": {}}
    ok = _row("ok", count=5)
    _day(state, "2026-10-01", [ok])
    got = []
    for d in range(2, 20):
        date = f"2026-10-{d:02d}"
        msg, ev = _day(state, date, [_row()])
        if msg:
            got.append((date, state["sources"]["a"]["consecutive_failures"]))
            _sent(state, ev, date)
    assert got == [("2026-10-02", 1), ("2026-10-04", 3), ("2026-10-11", 10), ("2026-10-18", 17)]


def test_message_has_elapsed_and_last_success(tmp_path):
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row("ok", count=12)])
    msg, _ = _day(state, "2026-10-02", [_row()])
    assert "経過 1 日" in msg and "最後に成功 2026-10-01（12 頭）" in msg


def test_ambiguous_empty_wording():
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row("ok", count=12)])
    msg, _ = _day(state, "2026-10-02", [_row("ambiguous_empty", kind="ambiguous_empty", err="根拠なし")])
    assert "0 頭に見えるが確定できないので前日分 12 頭を保持（stale_since 2026-10-02）" in msg


def test_fingerprint_change_notifies_again():
    state = {"sources": {}, "breaker": {}}
    msg, ev = _day(state, "2026-10-01", [_row()])
    _sent(state, ev, "2026-10-01")
    msg, _ = _day(state, "2026-10-02", [_row()])
    assert msg is None
    msg, _ = _day(state, "2026-10-03", [_row(kind="dns", err="dns")])
    assert msg is not None


def test_recovery_notified_once():
    state = {"sources": {}, "breaker": {}}
    _, ev = _day(state, "2026-10-01", [_row()])
    _sent(state, ev, "2026-10-01")
    msg, ev = _day(state, "2026-10-02", [_row("ok", count=7)])
    assert msg is not None and "復旧" in msg and ev[0]["type"] == "recovered"
    _sent(state, ev, "2026-10-02")
    assert state["sources"]["a"]["notified"] is None
    msg, _ = _day(state, "2026-10-03", [_row("ok", count=7)])
    assert msg is None


def test_notify_writes_state_only_when_sent(tmp_path, monkeypatch):
    data, sd = tmp_path / "data", tmp_path / "state"
    data.mkdir()
    rows = [_row()]
    (data / "report-2026-10-02.json").write_text(json.dumps(rows), encoding="utf-8")
    st = {"sources": {}, "breaker": {}}
    update_sources(st, rows, "2026-10-02")
    save_state(st, sd)
    assert nt.notify(dry_run=True, data_dir=data, state_dir=sd) == 0
    assert load_state(sd)["sources"]["a"].get("notified") is None           # dry-run は書かない
    posted = []
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")

    class _R:
        def raise_for_status(self): ...
    monkeypatch.setattr(nt.httpx, "post", lambda url, json, timeout: posted.append(json) or _R())
    assert nt.notify(data_dir=data, state_dir=sd) == 0
    assert len(posted) == 1 and load_state(sd)["sources"]["a"]["notified"]["last_at"] == "2026-10-02"
    assert nt.notify(data_dir=data, state_dir=sd) == 0 and len(posted) == 1   # 2 回目は送らない


def test_outage_line_comes_first():
    rep = [_row(kind="dns", host=f"h{i}.jp", slug=f"s{i}") for i in range(3)] + [_row("ok", slug="o", count=1)]
    msg = nt.build_message(rep, {"sources": {}}, "2026-10-04")
    assert msg is not None and msg.startswith("接続できなかったページが")
