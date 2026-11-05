"""W006 T635: 直す対象の無い日は AI を呼ばない。
(a) 同じホストで同じ日に 2 slug 以上が新たに失敗 = ホスト障害の疑い (b) 同じ slug は 1 日 1 回・同じ失敗の指紋で 3 回試したら隔離
(c) render の 404 を取得失敗にする (d) follow_all の子が全部 404 の日、および入口が 404 の日は呼ばない。"""

import json
import sys
import types

import pytest
from collector import ai_repair, repair_gate
from collector import run as run_mod
from collector.ai_repair import RepairResult
from collector.errors import ErrorInfo, host_of
from collector.extract import Result
from collector.fetch import FakeFetcher, Fetcher, FetchError
from collector.notify import build_message
from collector.registry import Source
from collector.state import load_state

PAGE = "<html><body><h2>保護犬</h2><p>ただいまの掲載はありません</p></body></html>"


def _src(slug: str, host: str = "a.jp", recipe: str | None = None) -> Source:
    return Source(
        slug=slug,
        name=f"{slug}市",
        municipality=slug,
        prefecture="東京都",
        url=f"https://{host}/{slug}",
        kind="stray",
        species="dog",
        recipe=recipe,
    )


def _fail(
    kind: str = "parser", status: int | None = None, url: str | None = None
) -> run_mod.Collected:
    info = ErrorInfo(kind, status=status, host="a.jp", url=url).to_dict()
    return run_mod.Collected("failed", None, f"{kind} 失敗", error_info=info)


def _ok() -> run_mod.Collected:
    res = Result(docs=1, rows=1)
    res.animals.append({"id": "a"})
    return run_mod.Collected("ok", res)


class Day:
    """collect_one と repair を差し替えて、日をまたいで run を回す。"""

    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        self.mp = monkeypatch
        self.calls: list[str] = []
        self.plan: dict[str, run_mod.Collected] = {}
        self.error_after_call = "新レシピでも 0 頭"
        monkeypatch.setattr(run_mod, "collect_one", lambda s, f: self.plan.get(s.slug) or _ok())
        monkeypatch.setattr(ai_repair, "repair", self._repair)
        monkeypatch.setattr(repair_gate, "context_hash", lambda: "ctx-1")

    def _repair(
        self,
        source,
        fetcher=None,
        error=None,
        last_ok_dir=None,
        last_ok_count=None,
        attempt=None,
        **kw,
    ):
        self.calls.append(source.slug)
        if attempt is not None:
            attempt.update(
                reached="ran", entry={"url": source.url, "sha256": "x", "bytes": 1, "is_html": True}
            )
        return RepairResult(source.slug, "failed", error=self.error_after_call)

    def run(self, srcs, date, body=PAGE, hms="00:05:00"):
        from datetime import datetime

        from collector.state import JST

        h, m, s = (int(x) for x in hms.split(":"))
        pages = {
            s_.url: (body if isinstance(body, str) else body.get(s_.slug, PAGE)) for s_ in srcs
        }
        self.calls.clear()
        out = run_mod.run(
            srcs,
            date,
            out_dir=self.tmp / "data",
            fetcher=FakeFetcher(pages),
            enabled=True,
            now=datetime(*map(int, date.split("-")), h, m, s, tzinfo=JST),
        )
        return {r["slug"]: r for r in out["sources"]}

    def state(self):
        return load_state(self.tmp / "data" / "state")


@pytest.fixture
def day(tmp_path, monkeypatch):
    return Day(tmp_path, monkeypatch)


# --- (a) ホスト障害の疑い --------------------------------------------------------
def test_a_two_new_failures_on_one_host_means_no_ai_for_that_host(day):
    srcs = [_src("a1"), _src("a2"), _src("a3"), _src("b1", "b.jp")]
    day.plan = {s.slug: _fail() for s in srcs}
    rows = day.run(srcs, "2026-11-01")
    assert day.calls == ["b1"]  # 同じホスト a.jp の 3 つは呼ばない。b.jp は 1 件だけなので呼ぶ
    assert "ホスト障害の疑い" in rows["a1"]["repair"] and rows["b1"]["repair"].startswith(
        "AI 修復に失敗"
    )


def test_a_one_new_failure_on_host_is_called(day):
    srcs = [_src("a1"), _src("a2")]
    day.plan = {"a1": _fail()}
    day.run(srcs, "2026-11-01")
    assert day.calls == ["a1"]


def test_a_failure_that_was_already_failing_does_not_count_as_new(day):
    srcs = [_src("a1"), _src("a2")]
    day.plan = {"a1": _fail()}
    day.run(srcs, "2026-11-01")
    day.plan = {"a1": _fail(), "a2": _fail()}  # a1 は昨日から。新たに失敗したのは a2 だけ
    day.run(srcs, "2026-11-02")
    assert day.calls == ["a1", "a2"]


def test_a_flag_stays_until_one_of_them_recovers(day):
    srcs = [_src("a1"), _src("a2"), _src("a3")]
    day.plan = {"a1": _fail(), "a2": _fail()}
    day.run(srcs, "2026-11-01")
    assert day.calls == [] and "a.jp" in day.state()["repair_hosts"]
    day.plan = {
        "a1": _fail(),
        "a2": _fail(),
        "a3": _fail(),
    }  # 翌日も戻っていない。新しく a3 が失敗しても呼ばない
    day.run(srcs, "2026-11-02")
    assert day.calls == [] and "a.jp" in day.state()["repair_hosts"]
    day.plan = {"a1": _fail(), "a3": _fail()}  # a2 が戻った → 解除。a1・a3 は呼ぶ
    day.run(srcs, "2026-11-03")
    assert day.calls == ["a1", "a3"] and day.state()["repair_hosts"] == {}


# --- (b) 1 日 1 回・同じ失敗の指紋で 3 回 → 隔離 ------------------------------------------
def test_b_once_a_day_even_if_run_twice(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail()}
    day.run(srcs, "2026-11-01", hms="00:05:00")
    rows = day.run(srcs, "2026-11-01", hms="16:04:00")
    assert day.calls == [] and "1 日 1 回" in rows["a1"]["repair"]


def test_b_third_try_with_same_fingerprint_quarantines_and_notifies_once(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail("parser")}
    r1 = day.run(srcs, "2026-11-01")
    r2 = day.run(srcs, "2026-11-02")
    r3 = day.run(srcs, "2026-11-03")
    assert not r1["a1"].get("quarantine_started") and not r2["a1"].get("quarantine_started")
    report = json.loads((day.tmp / "data" / "report-2026-11-03.json").read_text(encoding="utf-8"))
    # 隔離の印は通知のための内部の印。report には残し、公開側（run の戻り・latest.json の sources）には出さない（T632）
    assert report[0]["quarantine_started"] is True and "quarantine_started" not in r3["a1"]
    assert "隔離" in r3["a1"]["repair"]
    msg = build_message(report, load_state(day.tmp / "data" / "state"))
    assert msg is not None and "AI 修復を隔離" in msg and "a1市" in msg
    r4 = day.run(srcs, "2026-11-04")
    assert (
        day.calls == []
        and "隔離中" in r4["a1"]["repair"]
        and not r4["a1"].get("quarantine_started")
    )


def test_b_changed_entry_page_releases_quarantine(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail()}
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        day.run(srcs, d)
    day.run(srcs, "2026-11-04")
    assert day.calls == []
    day.run(srcs, "2026-11-05", body=PAGE + "<p>改修しました</p>")
    assert day.calls == ["a1"]


def test_b_changed_code_releases_quarantine(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail()}
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        day.run(srcs, d)
    day.mp.setattr(repair_gate, "context_hash", lambda: "ctx-2")  # コードか RECIPE.md が変わった
    day.run(srcs, "2026-11-04")
    assert day.calls == ["a1"]


def test_b_different_error_kind_is_a_different_fingerprint(day):
    srcs = [_src("a1")]
    for i, kind in enumerate(["parser", "recipe", "parser", "recipe"]):
        day.plan = {"a1": _fail(kind)}
        day.run(srcs, f"2026-11-0{i + 1}")
        assert day.calls == ["a1"]  # 指紋が毎回変わるので隔離されない


def test_b_recovery_resets_the_count(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail()}
    day.run(srcs, "2026-11-01")
    day.run(srcs, "2026-11-02")
    day.plan = {}
    day.run(srcs, "2026-11-03")  # 戻った
    assert "repair" not in day.state()["sources"]["a1"]
    day.plan = {"a1": _fail()}
    for d in ("2026-11-04", "2026-11-05"):
        day.run(srcs, d)
    assert day.calls == ["a1"] and day.state()["sources"]["a1"]["repair"]["tries"] == 2


def test_b_agy_failure_is_not_counted_toward_quarantine(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail()}

    def agy_down(source, attempt=None, **kw):
        day.calls.append(source.slug)
        attempt.update(
            reached="entry", entry={"url": source.url, "sha256": "x", "bytes": 1, "is_html": True}
        )
        return RepairResult(source.slug, "failed", error="agy を実行できない")

    day.mp.setattr(ai_repair, "repair", agy_down)
    for d in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"):
        day.run(srcs, d)
        assert day.calls == ["a1"]  # agy が落ちた日は試行に数えない = 隔離されない


# --- 入口が 404・子が全部 404 -------------------------------------------------------
def test_entry_404_does_not_call_ai(day):
    srcs = [_src("a1")]
    day.plan = {"a1": _fail("http", 404, url=srcs[0].url)}
    rows = day.run(srcs, "2026-11-01")
    assert day.calls == [] and "入口ページが 404" in rows["a1"]["repair"]


def test_child_404_without_skip_errors_still_calls_ai(day):
    srcs = [_src("a1")]
    day.plan = {
        "a1": _fail("http", 404, url="https://a.jp/a1/child1")
    }  # 入口ではなく子の 404 は skip_errors で直せるので呼ぶ
    day.run(srcs, "2026-11-01")
    assert day.calls == ["a1"]


LIST = '<html><body><a class="d" href="/c/1.html">1</a><a class="d" href="/c/2.html">2</a></body></html>'


def _follow_recipe(tmp_path) -> str:
    p = tmp_path / "f.yaml"
    p.write_text(
        'steps:\n  - follow_all: "a.d@href"\n    skip_errors: true\nrows: "body"\n',
        encoding="utf-8",
    )
    return str(p)


def test_d_all_children_404_is_flagged_and_not_repaired(tmp_path, monkeypatch):
    s = _src("f1", recipe=_follow_recipe(tmp_path))
    fetcher = FakeFetcher(
        {s.url: LIST, "https://a.jp/c/1.html": "x", "https://a.jp/c/2.html": "x"},
        status={"https://a.jp/c/1.html": 404, "https://a.jp/c/2.html": 404},
    )
    c = run_mod.collect_one(s, fetcher)
    assert c.status == "failed" and c.error_info["children_gone"] is True
    assert c.error_info["kind"] == "http" and c.error_info["status"] == 404
    called: list[str] = []
    monkeypatch.setattr(ai_repair, "repair", lambda *a, **k: called.append("x"))
    monkeypatch.setattr(run_mod, "collect_one", lambda *a: c)
    out = run_mod.run([s], "2026-11-05", out_dir=tmp_path / "data", fetcher=fetcher, enabled=True)
    assert called == [] and "子ページがすべて 404" in out["sources"][0]["repair"]


def test_d_some_children_ok_is_not_flagged(tmp_path):
    s = _src("f1", recipe=_follow_recipe(tmp_path))
    fetcher = FakeFetcher(
        {s.url: LIST, "https://a.jp/c/1.html": "<html><body>x</body></html>"},
        status={"https://a.jp/c/2.html": 404},
    )
    c = run_mod.collect_one(s, fetcher)
    assert not (c.error_info or {}).get("children_gone")


# --- (c) render の 404 ----------------------------------------------------------
def _fake_playwright(monkeypatch, status: int | None):
    class Resp:
        def __init__(self, st):
            self.status = st

    class Page:
        url = "https://a.jp/x"

        def goto(self, url, **kw):
            return None if status is None else Resp(status)

        def wait_for_selector(self, *a, **k): ...
        def wait_for_timeout(self, *a, **k): ...
        def content(self):
            return "<html><body>" + "<p>本文です</p>" * 80 + "</body></html>"

        def on(self, *a): ...

    class Browser:
        closed = False

        def new_page(self, **kw):
            return Page()

        def close(self):
            Browser.closed = True

    class PW:
        chromium = types.SimpleNamespace(launch=lambda: Browser())

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = lambda: PW()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    return Browser


def test_c_render_404_is_a_fetch_failure(monkeypatch):
    browser = _fake_playwright(monkeypatch, 404)
    f = Fetcher(delay=0, respect_robots=False)
    with pytest.raises(FetchError) as ei:
        f.render("https://a.jp/x")
    assert (
        ei.value.info.kind == "http"
        and ei.value.info.status == 404
        and ei.value.info.phase == "render"
    )
    assert ei.value.info.url == "https://a.jp/x" and ei.value.info.host == host_of("https://a.jp/x")
    assert browser.closed is True


def test_c_render_200_and_unknown_response_still_work(monkeypatch):
    for st in (200, None):
        _fake_playwright(monkeypatch, st)
        page = Fetcher(delay=0, respect_robots=False).render("https://a.jp/x")
        assert "本文です" in page.html


# --- 純関数 -----------------------------------------------------------------------
def test_context_hash_changes_with_recipe_doc(tmp_path, monkeypatch):
    doc = tmp_path / "RECIPE.md"
    doc.write_text("a", encoding="utf-8")
    monkeypatch.setattr(repair_gate, "RECIPE_DOC", doc)
    h1 = repair_gate.context_hash()
    doc.write_text("b", encoding="utf-8")
    assert repair_gate.context_hash() != h1
