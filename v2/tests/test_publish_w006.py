"""W006 T610（原子的公開・manifest）・T623（promote）。"""

import json

import pytest
from collector import publish as pub


def _day(date: str, n: int = 1, held: bool = False) -> dict:
    return {"run_id": "r", "date": date, "animals": [{"id": i} for i in range(n)], "held": held}


def test_publish_places_all_and_cleans_tmp(tmp_path):
    pub.publish(tmp_path, "r1", "2026-10-09", {"animals-2026-10-09.json": _day("2026-10-09"), "latest.json": _day("2026-10-09")})
    assert json.loads((tmp_path / "latest.json").read_text())["date"] == "2026-10-09"
    assert not list(tmp_path.glob(".tmp-*"))


def test_publish_validation_failure_moves_nothing(tmp_path):
    (tmp_path / "latest.json").write_text('{"date": "2026-10-08", "animals": []}', encoding="utf-8")
    with pytest.raises(pub.PublishError):
        pub.publish(tmp_path, "r1", "2026-10-09", {"animals-2026-10-09.json": _day("2026-10-09"), "latest.json": _day("2026-10-01")})
    assert json.loads((tmp_path / "latest.json").read_text())["date"] == "2026-10-08"
    assert not (tmp_path / "animals-2026-10-09.json").exists() and not list(tmp_path.glob(".tmp-*"))
    with pytest.raises(pub.PublishError):
        pub.publish(tmp_path, "r2", "2026-10-09", {"latest.json": {"date": "2026-10-09", "animals": "x"}})


def test_run_writes_manifest_and_holds(tmp_path, monkeypatch):
    from collector import run as run_mod
    from collector.fetch import FakeFetcher
    from collector.registry import Source

    s = Source(slug="a", name="a", municipality="a", prefecture="東京都", url="https://a.jp/", kind="stray", species="dog")
    monkeypatch.setattr(run_mod, "collect_one", lambda s, f: run_mod.Collected("empty"))
    run_mod.run([s], "2026-10-09", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    m = json.loads((tmp_path / "manifest-2026-10-09.json").read_text())
    assert set(m) == {"run_id", "date", "code_sha", "recipe_sha", "registry_sha", "animals_count", "sources_ok", "sources_failed", "held"}
    assert m["sources_ok"] == 1 and m["sources_failed"] == 0 and m["held"] is False and m["registry_sha"]
    assert (tmp_path / "manifest-latest.json").exists()


def test_manifest_shas_change_with_content(tmp_path):
    (tmp_path / "recipes").mkdir()
    reg = tmp_path / "sources.yaml"
    reg.write_text("a", encoding="utf-8")
    (tmp_path / "recipes" / "x.yaml").write_text("1", encoding="utf-8")
    m1 = pub.build_manifest("r", "2026-10-09", [], 0, False, root=tmp_path, registry_path=reg)
    (tmp_path / "recipes" / "x.yaml").write_text("2", encoding="utf-8")
    m2 = pub.build_manifest("r", "2026-10-09", [], 0, False, root=tmp_path, registry_path=reg)
    assert m1["recipe_sha"] != m2["recipe_sha"] and m1["registry_sha"] == m2["registry_sha"] and m1["code_sha"] is None


def test_promote_restores_held_day(tmp_path):
    (tmp_path / "latest.json").write_text('{"date": "2026-10-03", "animals": []}', encoding="utf-8")
    (tmp_path / "animals-2026-10-04.json").write_text(json.dumps(_day("2026-10-04", 3, held=True)), encoding="utf-8")
    (tmp_path / "manifest-2026-10-04.json").write_text(json.dumps({"run_id": "r", "date": "2026-10-04", "held": True}), encoding="utf-8")
    assert pub.promote("2026-10-04", tmp_path) == 0
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["date"] == "2026-10-04" and len(latest["animals"]) == 3 and latest["held"] is False
    assert json.loads((tmp_path / "manifest-latest.json").read_text())["held"] is False
    assert pub.promote("2026-10-05", tmp_path) == 2
