"""W006 T605: ambiguous_empty（0 頭に見えるが肯定的な証拠が無い）の slug は、前日の latest.json にあったその slug の子を
そのまま保持し、各レコードと report に stale_since（最後に成功した日）を付ける。確定した 0 頭（empty）は保持しない。"""

import json

from collector import run as run_mod
from collector.extract import Result
from collector.fetch import FakeFetcher
from collector.registry import Source


def _sources(n: int) -> list[Source]:
    return [Source(slug=f"s{i}", name=f"市{i}", municipality=f"市{i}", prefecture="東京都", url=f"https://h{i}.jp/{i}",
                   kind="stray", species="dog") for i in range(n)]


def _fake_collect(ambiguous: set[str], empty: set[str]):
    def collect_one(s, fetcher):
        res = Result(docs=1)
        if s.slug in ambiguous:
            res.ambiguous_empty = True
            res.ambiguous_reason = "全行除外だが見出しの項目名が一致しない"
            return run_mod.Collected("ambiguous_empty", res, "0 頭だが確定できない", [], {"kind": "ambiguous_empty"})
        if s.slug in empty:
            res.empty_confirmed = True
            return run_mod.Collected("empty", res)
        res.animals.append({"id": f"{s.slug}-today", "source": s.slug})
        return run_mod.Collected("ok", res)
    return collect_one


def _yesterday(tmp_path, slugs: list[str]) -> None:
    prev = {"date": "2026-10-08", "animals": [{"id": f"{s}-{i}", "source": s} for s in slugs for i in range(2)]}
    (tmp_path / "latest.json").write_text(json.dumps(prev), encoding="utf-8")


def test_ambiguous_keeps_yesterday_animals_with_stale_since(tmp_path, monkeypatch):
    _yesterday(tmp_path, ["s0", "s1", "s2"])
    monkeypatch.setattr(run_mod, "collect_one", _fake_collect(ambiguous={"s1"}, empty={"s2"}))
    out = run_mod.run(_sources(3), "2026-10-09", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    by = {}
    for a in out["animals"]:
        by.setdefault(a["source"], []).append(a)
    assert [a["id"] for a in by["s0"]] == ["s0-today"]                 # 今日読めた slug は今日の分
    assert sorted(a["id"] for a in by["s1"]) == ["s1-0", "s1-1"]       # ambiguous は前日の 2 頭を保持
    assert all(a["stale_since"] == "2026-10-08" for a in by["s1"])
    assert "s2" not in by                                               # 確定した 0 頭は保持しない
    row = next(r for r in out["sources"] if r["slug"] == "s1")
    assert row["status"] == "ambiguous_empty" and row["count"] == 2 and row["stale_since"] == "2026-10-08"
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["date"] == "2026-10-09" and sum(a["source"] == "s1" for a in latest["animals"]) == 2


def test_ambiguous_without_previous_data_keeps_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "collect_one", _fake_collect(ambiguous={"s1"}, empty=set()))
    out = run_mod.run(_sources(2), "2026-10-09", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    assert all(a["source"] != "s1" for a in out["animals"])
    row = next(r for r in out["sources"] if r["slug"] == "s1")
    assert row["status"] == "ambiguous_empty" and row["count"] == 0 and row.get("stale_since") is None


def test_stale_since_survives_two_ambiguous_days(tmp_path, monkeypatch):
    """2 日続けて ambiguous でも stale_since は最初に保持した元の日付（最後に成功した日）のまま。"""
    _yesterday(tmp_path, ["s0"])
    monkeypatch.setattr(run_mod, "collect_one", _fake_collect(ambiguous={"s0"}, empty=set()))
    run_mod.run(_sources(1), "2026-10-09", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    out = run_mod.run(_sources(1), "2026-10-10", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    assert len(out["animals"]) == 2 and all(a["stale_since"] == "2026-10-08" for a in out["animals"])
