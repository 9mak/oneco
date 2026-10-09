"""PR #44 の reviewer 差し戻し（M1〜M3・S2）の回帰テスト。

M1 サイトが ambiguous_empty と stale_since を表示する
M2 ambiguous_empty の保持は MAX_STALE_DAYS で打ち切る
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


# ---------------------------------------------------------------- M2
def test_carry_over_expires_after_max_stale_days(tmp_path, monkeypatch):
    srcs = [_src("s0", "h.jp")]
    prev = {"date": "2026-10-01", "animals": [{"id": "s0-old", "source": "s0"}]}
    (tmp_path / "latest.json").write_text(json.dumps(prev), encoding="utf-8")
    limit = run_mod.MAX_STALE_DAYS
    # stale_since は 10-01。保持は 10-01 + limit 日まで
    last_ok_day = f"2026-10-{1 + limit:02d}"
    out = _run(tmp_path, last_ok_day, srcs, {"s0": _ambiguous}, monkeypatch)
    assert out["animals"] and out["animals"][0]["stale_since"] == "2026-10-01"
    out = _run(tmp_path, f"2026-10-{2 + limit:02d}", srcs, {"s0": _ambiguous}, monkeypatch)
    row = out["sources"][0]
    assert out["animals"] == [] and row["status"] == "failed" and row["count"] == 0
    assert row["error_info"]["kind"] == "ambiguous_empty" and "日を超えた" in row["error"]


# ---------------------------------------------------------------- M1
def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build_w006", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_site_shows_ambiguous_status_and_stale_since(tmp_path):
    mod = _load_build()
    data = {"date": "2026-10-09", "animals": [
        {"id": "x1", "source": "s0", "municipality": "A市", "prefecture": "東京都", "kind": "stray", "species": "dog",
         "name": "ポチ", "stale_since": "2026-10-07"},
        {"id": "x2", "source": "s1", "municipality": "B市", "prefecture": "東京都", "kind": "stray", "species": "dog", "name": "タマ"},
    ], "sources": [
        {"slug": "s0", "name": "A市", "municipality": "A市", "prefecture": "東京都", "url": "https://a.jp/", "kind": "stray",
         "species": "dog", "status": "ambiguous_empty", "count": 1, "stale_since": "2026-10-07"},
        {"slug": "s1", "name": "B市", "municipality": "B市", "prefecture": "東京都", "url": "https://b.jp/", "kind": "stray",
         "species": "dog", "status": "ok", "count": 1},
    ]}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    mod.build(p, out, {"site_name": "oneco", "base_url": "https://x.test", "affiliate": []})
    sources = (out / "sources" / "index.html").read_text(encoding="utf-8")
    assert ">ambiguous_empty<" not in sources   # 生の status 名が表示文言として出ない（CSS クラス st-… は可）
    assert "最終確認 2026年10月7日" in sources and "本日は確定できず" in sources
    assert "確定できず 1 件" in sources
    detail = (out / "animals" / "x1" / "index.html").read_text(encoding="utf-8")
    assert "最終確認 2026年10月7日" in detail
    detail2 = (out / "animals" / "x2" / "index.html").read_text(encoding="utf-8")
    assert "最終確認" not in detail2
    animals_json = json.loads((out / "animals.json").read_text(encoding="utf-8")) if (out / "animals.json").exists() else None
    if animals_json is not None:
        x1 = next(a for a in (animals_json if isinstance(animals_json, list) else animals_json["animals"]) if a["id"] == "x1")
        assert x1.get("stale_since") == "2026-10-07"


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
