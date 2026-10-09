"""PR #44 の reviewer 差し戻し（M1〜M3・S2）の回帰テスト。

簡素化: ambiguous_empty の日はその slug の子を載せず、サイトは「読めませんでした」と出す
M3 breaker の翌日 probe は接続系・5xx 以外の失敗を「成功」とみなして閉じる
S2 recipe_schema の regex 計測が数字入りのダミーでも遅いものを落とす
"""

import importlib.util
import json
from pathlib import Path

from collector import run as run_mod
from collector.extract import Result
from collector.fetch import FakeFetcher
from collector.recipe_schema import validate_recipe_dict
from collector.registry import Source

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- helpers
def _src(slug: str, host: str) -> Source:
    return Source(slug=slug, name=f"市{slug}", municipality=f"市{slug}", prefecture="東京都", url=f"https://{host}/{slug}",
                  kind="stray", species="dog")


def _ok(slug: str) -> run_mod.Collected:
    res = Result(docs=1)
    res.animals.append({"id": f"{slug}-today", "source": slug})
    return run_mod.Collected("ok", res)


def _failed(kind: str, status: int | None = None) -> run_mod.Collected:
    return run_mod.Collected("failed", None, f"{kind}", [], {"kind": kind, "status": status})


def _ambiguous() -> run_mod.Collected:
    res = Result(docs=1)
    res.ambiguous_empty = True
    return run_mod.Collected("ambiguous_empty", res, "0 頭だが確定できない", [], {"kind": "ambiguous_empty"})


def _run(tmp_path, date, sources, table, monkeypatch):
    monkeypatch.setattr(run_mod, "collect_one", lambda s, f: table[s.slug]() if callable(table[s.slug]) else table[s.slug])
    return run_mod.run(sources, date, out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)


# ---------------------------------------------------------------- M3
def test_probe_closes_breaker_on_non_transport_failure(tmp_path, monkeypatch):
    """同一ホスト 5 本。1 日目に 3 本 timeout で遮断。2 日目は a0 が parser 失敗・a1〜a4 は健全。
    parser 失敗は「サイトが落ちている」証拠ではないので breaker は閉じ、a1〜a4 は通常どおり読む。"""
    srcs = [_src(f"a{i}", "h.jp") for i in range(5)]
    day1 = {f"a{i}": (lambda: _failed("timeout")) for i in range(5)}
    out1 = _run(tmp_path, "2026-10-08", srcs, day1, monkeypatch)
    assert sum(r["status"] == "failed" for r in out1["sources"]) == 5
    day2 = {"a0": lambda: _failed("parser"), **{f"a{i}": (lambda i=i: _ok(f"a{i}")) for i in range(1, 5)}}
    out2 = _run(tmp_path, "2026-10-09", srcs, day2, monkeypatch)
    by = {r["slug"]: r for r in out2["sources"]}
    assert by["a0"]["status"] == "failed" and "遮断" not in (by["a0"]["error"] or "")
    assert all(by[f"a{i}"]["status"] == "ok" for i in range(1, 5))
    state = json.loads((tmp_path / "state" / "sources.json").read_text(encoding="utf-8"))
    assert "h.jp" not in state["breaker"]


def test_probe_keeps_breaker_on_transport_failure(tmp_path, monkeypatch):
    srcs = [_src(f"a{i}", "h.jp") for i in range(4)]
    day1 = {f"a{i}": (lambda: _failed("connect")) for i in range(4)}
    _run(tmp_path, "2026-10-08", srcs, day1, monkeypatch)
    day2 = {"a0": lambda: _failed("http", 503), **{f"a{i}": (lambda i=i: _ok(f"a{i}")) for i in range(1, 4)}}
    out2 = _run(tmp_path, "2026-10-09", srcs, day2, monkeypatch)
    by = {r["slug"]: r for r in out2["sources"]}
    assert all("遮断" in (by[f"a{i}"]["error"] or "") for i in range(1, 4))


# ---------------------------------------------------------------- 簡素化
def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build_w006", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_ambiguous_empty_drops_children_and_site_says_unreadable(tmp_path, monkeypatch):
    srcs = [_src("s0", "h.jp"), _src("s1", "g.jp")]
    # 前日に載っていた s0 の子は、ambiguous_empty の日に持ち越されない
    (tmp_path / "latest.json").write_text(
        json.dumps({"date": "2026-10-08", "animals": [{"id": "s0-old", "source": "s0"}]}), encoding="utf-8")
    out = _run(tmp_path, "2026-10-09", srcs, {"s0": _ambiguous, "s1": lambda: _ok("s1")}, monkeypatch)
    assert [a["source"] for a in out["animals"]] == ["s1"]
    row = next(r for r in out["sources"] if r["slug"] == "s0")
    assert row["status"] == "ambiguous_empty" and row["count"] == 0 and "stale_since" not in row

    mod = _load_build()
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    dist = tmp_path / "dist"
    mod.build(p, dist, {"site_name": "oneco", "base_url": "https://x.test", "affiliate": []})
    sources = (dist / "sources" / "index.html").read_text(encoding="utf-8")
    assert "本日は読めませんでした。自治体のページをご確認ください" in sources
    assert ">ambiguous_empty<" not in sources and "最終確認" not in sources and "前回確認分" not in sources
    assert "確認できず 1 件" in sources


# ---------------------------------------------------------------- S2
def test_schema_rejects_regex_slow_on_digits():
    raw = {"rows": "tr", "rows_regex": r"(\d+\s?)+$"}
    errs = validate_recipe_dict(raw, "https://a.jp/")
    assert any("正規表現" in e for e in errs), errs


def test_schema_limits_remaining_keys():
    raw = {"rows": "tr", "empty_container": "x" * 5000, "max_pages": 10**9, "steps": [{"render": {"wait_ms": 10**9}}]}
    errs = validate_recipe_dict(raw, "https://a.jp/")
    joined = "\n".join(errs)
    assert "empty_container" in joined and "max_pages" in joined and "wait_ms" in joined
