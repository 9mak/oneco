"""W006 T645: 夜間の修復エージェントに渡す slug の選別（repair-plan。固定のスクリプトで、LLM は判断しない）。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from collector import repair_plan as rp
from collector.registry import Source

DATE = "2026-11-21"


def _src(slug: str, n: int = 1, **kw) -> Source:
    base = {"slug": slug, "name": f"{slug}市", "municipality": "A市", "prefecture": "P県",
            "url": f"https://h{n}.example/list.html", "kind": "adoption", **kw}
    return Source(**base)


def _row(slug: str, n: int = 1, kind: str = "parser", status: int | None = None, url: str | None = None,
         st: str = "failed", **info_extra) -> dict:
    info = {"kind": kind, "status": status, "host": f"h{n}.example", "url": url, **info_extra}
    return {"slug": slug, "name": slug, "status": st, "count": 0, "error": "0 頭で empty_text も無い",
            "error_info": info if st == "failed" else None, "repair": None}


def _plan(rows, sources, unmerged=frozenset(), state=None, attempts=None, limit=5):
    return rp.select(rows, sources, state if state is not None else {"sources": {}, "repair_hosts": {}}, DATE,
                     unmerged=set(unmerged), attempts_root=attempts, limit=limit)


def _reasons(plan) -> dict[str, str]:
    return {e["slug"]: e["reason"] for e in plan["excluded"]}


def test_parser_failure_is_selected_with_context():
    plan = _plan([_row("a")], [_src("a")])
    assert [s["slug"] for s in plan["selected"]] == ["a"]
    s = plan["selected"][0]
    assert s["url"] == "https://h1.example/list.html" and s["error_kind"] == "parser" and s["name"] == "a市"
    assert plan["excluded"] == []


def test_ok_and_empty_rows_are_not_candidates():
    plan = _plan([_row("a", st="ok"), _row("b", n=2, st="empty")], [_src("a"), _src("b", 2)])
    assert plan["selected"] == [] and plan["excluded"] == []


def test_entry_404_and_401_403_and_children_gone_are_excluded():
    rows = [
        _row("gone", 1, "http", 404, url="https://h1.example/list.html"),
        _row("b401", 2, "http", 401, url="https://h2.example/list.html"),
        _row("b403", 3, "http", 403, url="https://h3.example/list.html"),
        _row("kids", 4, "http", 404, children_gone=True),
    ]
    plan = _plan(rows, [_src("gone", 1), _src("b401", 2), _src("b403", 3), _src("kids", 4)])
    assert plan["selected"] == []
    assert _reasons(plan) == {"gone": "entry_gone", "b401": "entry_blocked", "b403": "entry_blocked", "kids": "children_gone"}


def test_child_404_that_is_not_all_children_is_still_a_candidate():
    # 入口ではなく子の 404（children_gone の印なし）は、レシピ（skip_errors）で直せる
    plan = _plan([_row("a", 1, "http", 404, url="https://h1.example/other.html")], [_src("a")])
    assert [s["slug"] for s in plan["selected"]] == ["a"]


def test_host_suspect_when_two_slugs_on_same_host_newly_fail():
    rows = [_row("a", 1), _row("b", 1)]
    plan = _plan(rows, [_src("a", 1), _src("b", 1)])
    assert plan["selected"] == [] and _reasons(plan) == {"a": "host_suspect", "b": "host_suspect"}


def test_host_suspect_is_written_back_to_state():
    state = {"sources": {}, "repair_hosts": {}}
    _plan([_row("a", 1), _row("b", 1)], [_src("a", 1), _src("b", 1)], state=state)
    assert "h1.example" in state["repair_hosts"]


def test_link_only_disabled_and_unknown_slug_are_excluded():
    rows = [_row("lo", 1), _row("off", 2), _row("ghost", 3)]
    plan = _plan(rows, [_src("lo", 1, mode="link_only"), _src("off", 2, enabled=False)])
    assert plan["selected"] == []
    assert _reasons(plan) == {"lo": "link_only", "off": "disabled", "ghost": "unknown_slug"}


def test_site_side_failures_are_excluded():
    rows = [_row("tcp", 1, "timeout"), _row("s503", 2, "http", 503, url="https://h2.example/list.html"),
            _row("mnt", 3, "content"), _row("brk", 4, "http", 503, breaker=True)]
    plan = _plan(rows, [_src("tcp", 1), _src("s503", 2), _src("mnt", 3), _src("brk", 4)])
    assert plan["selected"] == []
    assert _reasons(plan) == {"tcp": "site_side", "s503": "site_side", "mnt": "maintenance_page", "brk": "breaker"}


def test_unmerged_repair_branch_is_excluded():
    plan = _plan([_row("a", 1), _row("b", 2)], [_src("a", 1), _src("b", 2)], unmerged={"a"})
    assert [s["slug"] for s in plan["selected"]] == ["b"] and _reasons(plan) == {"a": "branch_open"}


def test_limit_is_five_per_night_and_rest_is_over_limit():
    slugs = [f"s{i}" for i in range(7)]
    plan = _plan([_row(s, i) for i, s in enumerate(slugs)], [_src(s, i) for i, s in enumerate(slugs)])
    assert [s["slug"] for s in plan["selected"]] == slugs[:5]
    assert _reasons(plan) == {"s5": "over_limit", "s6": "over_limit"}


def test_limit_from_environment(monkeypatch):
    monkeypatch.setenv("ONECO_REPAIR_MAX", "2")
    assert rp.max_per_night() == 2
    monkeypatch.setenv("ONECO_REPAIR_MAX", "x")
    assert rp.max_per_night() == 5
    monkeypatch.delenv("ONECO_REPAIR_MAX")
    assert rp.max_per_night() == 5


def _attempt(root: Path, date: str, slug: str, outcome: str) -> None:
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps({"slug": slug, "outcome": outcome}), encoding="utf-8")


def test_once_a_day_when_attempt_record_exists_today(tmp_path):
    _attempt(tmp_path, DATE, "a", "failed")
    plan = _plan([_row("a", 1)], [_src("a", 1)], attempts=tmp_path)
    assert _reasons(plan) == {"a": "once_a_day"}


def test_quarantined_after_three_failed_nights_in_a_week(tmp_path):
    for d in ("2026-11-15", "2026-11-17", "2026-11-19"):
        _attempt(tmp_path, d, "a", "failed")
    _attempt(tmp_path, "2026-11-10", "b", "failed")   # 7 日より前は数えない
    _attempt(tmp_path, "2026-11-19", "b", "pr_created")
    plan = _plan([_row("a", 1), _row("b", 2)], [_src("a", 1), _src("b", 2)], attempts=tmp_path)
    assert _reasons(plan) == {"a": "quarantined"} and [s["slug"] for s in plan["selected"]] == ["b"]


def test_write_plan_file(tmp_path):
    plan = _plan([_row("a", 1)], [_src("a", 1)])
    p = rp.write_plan(plan, tmp_path, DATE)
    assert p == tmp_path / f"repair-plan-{DATE}.json"
    assert json.loads(p.read_text(encoding="utf-8"))["selected"][0]["slug"] == "a"


def test_unmerged_branches_parses_git_output_and_survives_failure(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    class P:
        returncode = 0
        stdout = "  origin/repair/a\n  origin/repair/b-1\n"
        stderr = ""

    def fake(cmd, **kw):
        calls.append(cmd)
        return P()

    monkeypatch.setattr(subprocess, "run", fake)
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("ONECO_REPAIR_CLONE", str(tmp_path))
    slugs, err = rp.unmerged_repair_branches()
    assert slugs == {"a", "b-1"} and err is None
    assert any("--no-merged" in c for c in calls)

    class Bad(P):
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: Bad())
    slugs, err = rp.unmerged_repair_branches()
    assert slugs == set() and "boom" in err
