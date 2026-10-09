"""W006 T603（breaker・回線断）・T607（state）・T609（排他・run_id）・T615（events）。"""

import fcntl
import json

import pytest
from collector import run as run_mod
from collector.errors import ErrorInfo
from collector.extract import Result
from collector.fetch import FakeFetcher
from collector.registry import Source
from collector.state import AlreadyRunningError, load_state, save_state


def _src(slug: str, host: str) -> Source:
    return Source(slug=slug, name=slug, municipality=slug, prefecture="東京都", url=f"https://{host}/{slug}",
                  kind="stray", species="dog")


def _ok() -> run_mod.Collected:
    res = Result(docs=1, rows=1)
    res.animals.append({"id": "a"})
    return run_mod.Collected("ok", res)


def _fail(kind: str, host: str, status: int | None = None) -> run_mod.Collected:
    return run_mod.Collected("failed", None, f"{kind} {host}", error_info=ErrorInfo(kind, status=status, host=host).to_dict())


def _fake(plan: dict[str, run_mod.Collected], calls: list[str]):
    def collect_one(s, fetcher):
        calls.append(s.slug)
        return plan.get(s.slug) or _ok()
    return collect_one


def _run(srcs, date, tmp_path, **kw):
    return run_mod.run(srcs, date, out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False, **kw)


def test_breaker_trips_and_skips_rest_of_host(tmp_path, monkeypatch):
    srcs = [_src(f"a{i}", "a.jp") for i in range(5)] + [_src("b0", "b.jp")]
    calls: list[str] = []
    monkeypatch.setattr(run_mod, "collect_one", _fake({f"a{i}": _fail("timeout", "a.jp") for i in range(5)}, calls))
    out = _run(srcs, "2026-10-09", tmp_path)
    assert calls == ["a0", "a1", "a2", "b0"]    # 3 件連続で遮断。a3・a4 は取りに行かない
    rows = {r["slug"]: r for r in out["sources"]}
    assert rows["a3"]["status"] == "failed" and "ホスト遮断中（a.jp・3 件連続失敗）" in rows["a3"]["error"]
    assert rows["a3"]["error_info"]["kind"] == "timeout" and rows["a3"]["error_info"]["breaker"] is True
    assert rows["b0"]["status"] == "ok"
    assert load_state(tmp_path / "state")["breaker"]["a.jp"] == {"opened": "2026-10-09", "failures": 3}


def test_breaker_counts_5xx_but_not_4xx_or_parser(tmp_path, monkeypatch):
    srcs = [_src(f"a{i}", "a.jp") for i in range(4)]
    calls: list[str] = []
    plan = {"a0": _fail("http", "a.jp", 404), "a1": _fail("parser", "a.jp"), "a2": _fail("http", "a.jp", 503), "a3": _fail("http", "a.jp", 503)}
    monkeypatch.setattr(run_mod, "collect_one", _fake(plan, calls))
    _run(srcs, "2026-10-09", tmp_path)
    assert calls == ["a0", "a1", "a2", "a3"] and load_state(tmp_path / "state")["breaker"] == {}


def test_breaker_streak_resets_on_success(tmp_path, monkeypatch):
    srcs = [_src(f"a{i}", "a.jp") for i in range(5)]
    calls: list[str] = []
    plan = {"a0": _fail("dns", "a.jp"), "a1": _fail("dns", "a.jp"), "a3": _fail("dns", "a.jp"), "a4": _fail("dns", "a.jp")}
    monkeypatch.setattr(run_mod, "collect_one", _fake(plan, calls))
    _run(srcs, "2026-10-09", tmp_path)
    assert len(calls) == 5     # 間に成功（a2）が挟まるので連続 3 にならない


def test_next_day_probes_one_slug_then_closes_or_keeps(tmp_path, monkeypatch):
    save_state({"sources": {}, "breaker": {"a.jp": {"opened": "2026-10-09", "failures": 3}}}, tmp_path / "state")
    srcs = [_src(f"a{i}", "a.jp") for i in range(4)]
    calls: list[str] = []
    monkeypatch.setattr(run_mod, "collect_one", _fake({"a0": _fail("connect", "a.jp")}, calls))
    _run(srcs, "2026-10-10", tmp_path)
    assert calls == ["a0"]                                              # probe は最初の 1 slug だけ
    assert load_state(tmp_path / "state")["breaker"]["a.jp"]["opened"] == "2026-10-09"   # 失敗なら開いたまま
    calls.clear()
    monkeypatch.setattr(run_mod, "collect_one", _fake({}, calls))
    _run(srcs, "2026-10-11", tmp_path)
    assert calls == ["a0", "a1", "a2", "a3"] and load_state(tmp_path / "state")["breaker"] == {}   # 成功で閉じて通常どおり


def _outage_report(kind: str, hosts: int, per_host: int, ok: int) -> list[dict]:
    rep = [{"slug": f"h{h}-{i}", "status": "failed", "error_info": {"kind": kind, "host": f"h{h}.jp"}} for h in range(hosts) for i in range(per_host)]
    return rep + [{"slug": f"ok{i}", "status": "ok"} for i in range(ok)]


def test_outage_needs_three_hosts_and_ten_percent():
    assert run_mod.outage(_outage_report("dns", 3, 1, 27)) is True       # 3 ホスト・3/30 = 10%
    assert run_mod.outage(_outage_report("dns", 2, 10, 20)) is False     # 2 ホストだけ（1 サイトの障害）
    assert run_mod.outage(_outage_report("dns", 3, 1, 28)) is False      # 3/31 < 10%
    assert run_mod.outage(_outage_report("parser", 20, 1, 5)) is False   # parser がいくら多くても回線断ではない
    assert run_mod.outage(_outage_report("http", 20, 1, 5)) is False


def test_state_tracks_failures_and_recovery(tmp_path, monkeypatch):
    srcs = [_src("a", "a.jp")]
    monkeypatch.setattr(run_mod, "collect_one", _fake({}, []))
    _run(srcs, "2026-10-08", tmp_path)
    monkeypatch.setattr(run_mod, "collect_one", _fake({"a": _fail("parser", "a.jp")}, []))
    _run(srcs, "2026-10-09", tmp_path)
    _run(srcs, "2026-10-09", tmp_path)       # 同じ日の再実行は二重に数えない
    st = load_state(tmp_path / "state")["sources"]["a"]
    assert (st["last_ok"], st["last_ok_count"], st["consecutive_failures"], st["first_failed"]) == ("2026-10-08", 1, 1, "2026-10-09")
    assert st["last_status"] == "failed" and st["last_error_kind"] == "parser" and st["last_host"] == "a.jp"
    _run(srcs, "2026-10-10", tmp_path)
    assert load_state(tmp_path / "state")["sources"]["a"]["consecutive_failures"] == 2
    monkeypatch.setattr(run_mod, "collect_one", _fake({}, []))
    _run(srcs, "2026-10-11", tmp_path)
    st = load_state(tmp_path / "state")["sources"]["a"]
    assert st["consecutive_failures"] == 0 and st["prev_status"] == "failed" and st["first_failed"] is None


def test_corrupt_state_starts_empty(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "sources.json").write_text("{not json", encoding="utf-8")
    assert load_state(tmp_path / "state") == {"sources": {}, "breaker": {}}


def test_lock_blocks_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "collect_one", _fake({}, []))
    (tmp_path / "state").mkdir()
    with (tmp_path / "state" / "collect.lock").open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(AlreadyRunningError):
            _run([_src("a", "a.jp")], "2026-10-09", tmp_path)
    _run([_src("a", "a.jp")], "2026-10-09", tmp_path)     # 解放後は走れる


def test_cli_run_exits_3_when_locked(tmp_path, monkeypatch):
    from collector import __main__ as cli

    def busy(*a, **k):
        raise AlreadyRunningError("他の収集が動いている")
    monkeypatch.setattr(run_mod, "run", busy)
    monkeypatch.setattr(cli, "load_sources", lambda: [])
    assert cli.main(["run", "--no-ai-repair"]) == 3


def test_run_id_everywhere_and_events(tmp_path, monkeypatch):
    from datetime import datetime

    from collector.state import JST

    monkeypatch.setattr(run_mod, "collect_one", _fake({"b": _fail("http", "b.jp", 503)}, []))
    out = _run([_src("a", "a.jp"), _src("b", "b.jp")], "2026-10-09", tmp_path,
               now=datetime(2026, 10, 9, 0, 5, 7, tzinfo=JST))
    assert out["run_id"] == "2026-10-09T000507"
    for name in ("animals-2026-10-09.json", "latest.json", "manifest-2026-10-09.json", "manifest-latest.json"):
        assert json.loads((tmp_path / name).read_text())["run_id"] == "2026-10-09T000507"
    assert all(r["run_id"] == "2026-10-09T000507" for r in json.loads((tmp_path / "report-2026-10-09.json").read_text()))
    lines = [json.loads(x) for x in (tmp_path / "logs" / "events-2026-10-09.jsonl").read_text().splitlines()]
    assert [x["slug"] for x in lines] == ["a", "b"] and lines[1]["kind"] == "http" and lines[1]["http_status"] == 503
    assert set(lines[0]) == {"run_id", "slug", "host", "status", "kind", "http_status", "seconds", "attempt", "count", "dropped", "rows", "breaker"}


def test_ambiguous_empty_status(monkeypatch):
    """Result.ambiguous_empty が立っていれば failed(parser) でなく ambiguous_empty。"""
    from collector import extract

    res = Result(docs=1, rows=0)
    res.ambiguous_empty = True  # type: ignore[attr-defined]
    res.ambiguous_reason = "empty_text なし"  # type: ignore[attr-defined]
    monkeypatch.setattr(extract, "build", lambda *a, **k: res)
    monkeypatch.setattr(run_mod, "build", lambda *a, **k: res)

    class _Ex:
        trace: list[str] = []

        def __init__(self, *a, **k): ...
        def resolve(self, url): return []

    monkeypatch.setattr(run_mod, "Executor", _Ex)
    monkeypatch.setattr(run_mod.Recipe, "load", staticmethod(lambda p: object()))
    s = _src("a", "a.jp")
    monkeypatch.setattr(Source, "recipe_path", property(lambda self: __import__("pathlib").Path(__file__)))
    c = run_mod.collect_one(s, FakeFetcher({}))
    assert c.status == "ambiguous_empty" and c.error_info["kind"] == "ambiguous_empty" and c.error_info["phase"] == "parse"
