"""通知は「読めない slug が 1 件でもある日は毎日 1 通」（POLICY.md 方針 25）。読めない slug が無く、ほかに知らせることも無い日は送らない。"""

import json

from collector import notify as nt
from collector.state import save_state, update_sources


def _row(status="failed", kind="parser", host="a.jp", slug="a", count=0, err="0 頭で empty_text も無い", name="A市"):
    info = {"kind": kind, "status": None, "host": host} if status in ("failed", "ambiguous_empty") else None
    return {"slug": slug, "name": name, "status": status, "count": count, "error": err, "error_info": info, "repair": None}


def _day(state, date, rows):
    update_sources(state, rows, date)
    return nt.build_message(rows, state)


def test_new_failure_sends_and_same_set_sends_every_day():
    state = {"sources": {}, "breaker": {}}
    assert _day(state, "2026-10-01", [_row("ok", count=5)]) is None
    msg = _day(state, "2026-10-02", [_row()])
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg and "- A市: 0 頭で empty_text も無い" in msg
    for d in range(3, 12):   # 同じ顔ぶれでも毎日送る。続いているものも名前を出す
        m = _day(state, f"2026-10-{d:02d}", [_row()])
        assert m is not None and "新たに読めなくなった" not in m
        assert "引き続き読めない 1 件" in m and "- A市: 0 頭で empty_text も無い" in m


def test_first_run_without_record_counts_as_new_failure():
    msg = nt.build_message([_row()], None)
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg


def test_recovery_sends_with_count_and_only_once():
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row()])
    msg = _day(state, "2026-10-02", [_row("ok", count=7)])
    assert msg is not None and "読めるようになった自治体 1 件" in msg and "- A市（7 頭）" in msg
    assert _day(state, "2026-10-03", [_row("ok", count=7)]) is None   # 読めない掲載元が 0 件に戻れば送らない


def test_ambiguous_empty_counts_as_failing_both_ways():
    state = {"sources": {}, "breaker": {}}
    _day(state, "2026-10-01", [_row("ok", count=12)])
    msg = _day(state, "2026-10-02", [_row("ambiguous_empty", kind="ambiguous_empty", err="根拠なし")])
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg and "- A市: 根拠なし" in msg
    # failed への切り替わりは「読めない」のまま = 新規ではなく引き続き（ただし毎日送る）
    m = _day(state, "2026-10-03", [_row()])
    assert m is not None and "引き続き読めない 1 件" in m and "新たに読めなくなった" not in m
    msg = _day(state, "2026-10-04", [_row("empty")])
    assert msg is not None and "読めるようになった自治体 1 件" in msg


def test_still_failing_lists_names():
    state = {"sources": {}, "breaker": {}}
    both = lambda b: [_row(slug="a", name="A市"), b]   # noqa: E731
    _day(state, "2026-10-01", both(_row("ok", slug="b", name="B市", count=1)))
    msg = _day(state, "2026-10-02", both(_row(slug="b", name="B市")))
    assert msg is not None and "新たに読めなくなった自治体 1 件" in msg
    assert "引き続き読めない 1 件" in msg and "- A市: 0 頭で empty_text も無い" in msg
    assert msg.index("新たに読めなくなった") < msg.index("- B市") < msg.index("引き続き読めない") < msg.index("- A市")


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
    assert nt.notify(dry_run=True, data_dir=data, state_dir=sd, date="2026-10-02") == 0 and not posted
    assert nt.notify(data_dir=data, state_dir=sd, date="2026-10-02") == 0 and len(posted) == 1
    assert (sd / "sources.json").read_text(encoding="utf-8") == before


def test_outage_line_comes_first_and_sends_even_without_change():
    rep = [_row(kind="dns", host=f"h{i}.jp", slug=f"s{i}") for i in range(3)] + [_row("ok", slug="o", count=1)]
    state = {"sources": {}, "breaker": {}}
    update_sources(state, rep, "2026-10-03")
    update_sources(state, rep, "2026-10-04")   # 顔ぶれは前日と同じ
    msg = nt.build_message(rep, state)
    assert msg is not None and msg.startswith("接続できなかったページが")


def test_total_outage_day_sends_every_failing_source():
    """収集が全滅した日（全 slug が failed）。回線断の行の下に、続いているものも全部名前が出る。"""
    rep = [_row(kind="dns", host=f"h{i}.jp", slug=f"s{i}", name=f"N{i}市") for i in range(4)]
    state = {"sources": {}, "breaker": {}}
    update_sources(state, rep, "2026-10-03")
    update_sources(state, rep, "2026-10-04")
    msg = nt.build_message(rep, state)
    assert msg is not None and msg.startswith("接続できなかったページが") and "引き続き読めない 4 件" in msg
    assert all(f"- N{i}市" in msg for i in range(4))


def test_ok_only_and_empty_only_days_stay_silent():
    state = {"sources": {}, "breaker": {}}
    rows = [_row("ok", count=3), _row("empty", slug="e", name="E市")]
    assert _day(state, "2026-10-01", rows) is None
    assert _day(state, "2026-10-02", rows) is None
