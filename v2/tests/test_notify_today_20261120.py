"""W006 T656 付随・項目 2: 収集が失敗した日に、前日の report を読んで同じ通知を再び送らない（2026-11-20）。

ops/collect.sh は run が失敗（二重起動の exit 3 を含む）しても notify を呼ぶ。notify は日付を見ず一番新しい report-*.json を
読んでいたので、今日の report が無い日は前日の内容を「今日の通知」として送り直していた。
今日（JST）の report が無いときは、Discord に何も送らず、理由を表示して非 0（1）で終わる。送らない理由: run の失敗は
collect.sh が末尾で「失敗した工程」を 1 通送り、公開サイトの日付が古いままなら v2-deadman.yml（02:00 JST）も送る。
ここでも送ると同じ日に 3 通になる。
"""

import json

from collector import notify as nt
from collector.state import save_state, update_sources


def _row(slug="a", status="failed"):
    info = {"kind": "parser", "status": None, "host": "a.jp"} if status == "failed" else None
    return {"slug": slug, "name": "A市", "status": status, "count": 0, "error": "0 頭で empty_text も無い", "error_info": info, "repair": None}


def _setup(tmp_path, monkeypatch, report_date="2026-11-19"):
    data, sd = tmp_path / "data", tmp_path / "state"
    data.mkdir()
    rows = [_row()]
    (data / f"report-{report_date}.json").write_text(json.dumps(rows), encoding="utf-8")
    st = {"sources": {}, "breaker": {}}
    save_state(st, sd)
    posted: list[dict] = []

    class _R:
        def raise_for_status(self): ...
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setattr(nt.httpx, "post", lambda url, json, timeout: posted.append(json) or _R())
    return data, sd, posted


def test_yesterdays_report_is_not_sent_again_when_today_has_none(tmp_path, monkeypatch, capsys):
    data, sd, posted = _setup(tmp_path, monkeypatch, "2026-11-19")
    rc = nt.notify(data_dir=data, state_dir=sd, date="2026-11-20")
    assert rc == 1 and not posted
    out = capsys.readouterr().out
    assert "2026-11-20" in out and "report" in out and "収集が途中で止まった可能性" in out
    assert "A市" not in out   # 前日の内容を出さない


def test_dry_run_also_reports_missing_today(tmp_path, monkeypatch):
    data, sd, posted = _setup(tmp_path, monkeypatch, "2026-11-19")
    assert nt.notify(dry_run=True, data_dir=data, state_dir=sd, date="2026-11-20") == 1 and not posted


def test_todays_report_is_sent_as_before(tmp_path, monkeypatch):
    data, sd, posted = _setup(tmp_path, monkeypatch, "2026-11-20")
    assert nt.notify(data_dir=data, state_dir=sd, date="2026-11-20") == 0
    assert len(posted) == 1 and "新たに読めなくなった自治体 1 件" in posted[0]["content"]


def test_default_date_is_today_in_jst(tmp_path, monkeypatch):
    data, sd, posted = _setup(tmp_path, monkeypatch, "2026-11-19")
    monkeypatch.setattr(nt, "_today_jst", lambda: "2026-11-20")
    assert nt.notify(data_dir=data, state_dir=sd) == 1 and not posted
    monkeypatch.setattr(nt, "_today_jst", lambda: "2026-11-19")
    assert nt.notify(data_dir=data, state_dir=sd) == 0 and len(posted) == 1


def test_no_report_at_all_is_still_one(tmp_path, monkeypatch):
    data, sd, posted = _setup(tmp_path, monkeypatch, "2026-11-19")
    (data / "report-2026-11-19.json").unlink()
    assert nt.notify(data_dir=data, state_dir=sd, date="2026-11-20") == 1 and not posted


def test_update_sources_is_untouched_by_notify(tmp_path, monkeypatch):
    data, sd, _ = _setup(tmp_path, monkeypatch, "2026-11-20")
    st = {"sources": {}, "breaker": {}}
    update_sources(st, [_row()], "2026-11-20")
    save_state(st, sd)
    before = (sd / "sources.json").read_text(encoding="utf-8")
    nt.notify(data_dir=data, state_dir=sd, date="2026-11-20")
    assert (sd / "sources.json").read_text(encoding="utf-8") == before
