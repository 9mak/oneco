"""通知は「読めない slug の顔ぶれが前日と変わった日」だけ（回線断の日は例外で送る）。"""

import json

from collector import notify as nt
from collector.state import save_state, update_sources


def _row(status="failed", kind="parser", host="a.jp", slug="a", count=0, err="0 頭で empty_text も無い", name="A市"):
    info = {"kind": kind, "status": None, "host": host} if status in ("failed", "ambiguous_empty") else None
    return {"slug": slug, "name": name, "status": status, "count": count, "error": err, "error_info": info, "repair": None}


def _day(state, date, rows):
    update_sources(state, rows, date)
    return nt.build_message(rows, state)


def test_new_failure_sends_then_same_set_is_silent():
    state = {"sources": {}, "breaker": {}}
    assert _day(state, "2026-10-01", [_row("ok", count=5)]) is None
    msg = _day(state, "2026-10-02", [_row()])
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg and "- A市: 0 頭で empty_text も無い" in msg
    for d in range(3, 12):   # 同じ顔ぶれの 2 日目以降は何日続いても送らない
        assert _day(state, f"2026-10-{d:02d}", [_row()]) is None


def test_first_run_without_record_counts_as_new_failure():
    msg = nt.build_message([_row()], None)
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg


def test_recovery_sends_with_count_and_only_once():
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row()])
    msg = _day(state, "2026-10-02", [_row("ok", count=7)])
    assert msg is not None and "読めるようになった自治体 1 件" in msg and "- A市（7 頭）" in msg
    assert _day(state, "2026-10-03", [_row("ok", count=7)]) is None


def test_ambiguous_empty_counts_as_failing_both_ways():
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row("ok", count=12)])
    msg = _day(state, "2026-10-02", [_row("ambiguous_empty", kind="ambiguous_empty", err="根拠なし")])
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg and "- A市: 根拠なし" in msg
    # failed への切り替わりは「読めない」のまま = 顔ぶれが変わらないので送らない
    assert _day(state, "2026-10-03", [_row()]) is None
    msg = _day(state, "2026-10-04", [_row("empty")])
    assert msg is not None and "読めるようになった自治体 1 件" in msg


def test_still_failing_is_count_only():
    state = {"sources": {}, "breaker": {}}
    both = lambda b: [_row(slug="a", name="A市"), b]   # noqa: E731
    _day(state, "2026-10-01", both(_row("ok", slug="b", name="B市", count=1)))
    msg = _day(state, "2026-10-02", both(_row(slug="b", name="B市")))
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg
    assert "引き続き読めない 1 件" in msg and "- A市" not in msg


def test_repair_note_in_parentheses_and_footer():
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row("ok", count=3), _row("ok", slug="o", name="O市", count=4)])
    rows = [{**_row(), "repair": "AI がレシピ案を書いた"}, _row("ok", slug="o", name="O市", count=4)]
    msg = _day(state, "2026-10-02", rows)
    assert "- A市: 0 頭で empty_text も無い（AI がレシピ案を書いた）" in msg and msg.endswith("（公開 4 頭・成功 1 ページ）")


def test_notify_reads_state_but_never_writes(tmp_path, monkeypatch):
    data, sd = tmp_path / "data", tmp_path / "state"
    data.mkdir()
    rows = [_row()]
    (data / "report-2026-10-02.json").write_text(json.dumps(rows), encoding="utf-8")
    st = {"sources": {}, "breaker": {}}
    update_sources(st, rows, "2026-10-02")
    save_state(st, sd)
    before = (sd / "sources.json").read_text(encoding="utf-8")
    posted = []
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")

    class _R:
        def raise_for_status(self): ...
    monkeypatch.setattr(nt.httpx, "post", lambda url, json, timeout: posted.append(json) or _R())
    assert nt.notify(dry_run=True, data_dir=data, state_dir=sd) == 0 and not posted
    assert nt.notify(data_dir=data, state_dir=sd) == 0 and len(posted) == 1
    assert (sd / "sources.json").read_text(encoding="utf-8") == before


def test_outage_line_comes_first_and_sends_even_without_change():
    rep = [_row(kind="dns", host=f"h{i}.jp", slug=f"s{i}") for i in range(3)] + [_row("ok", slug="o", count=1)]
    state = {"sources": {}, "breaker": {}}
    update_sources(state, rep, "2026-10-03")
    update_sources(state, rep, "2026-10-04")   # 顔ぶれは前日と同じ
    msg = nt.build_message(rep, state)
    assert msg is not None and msg.startswith("接続できなかったページが")
