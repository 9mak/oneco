"""W006 T632 の小さな直し (4) quarantine_started は公開データに出さない。ネットワークなし。"""

from __future__ import annotations

import json

from collector import ai_repair, repair_gate
from collector import run as run_mod
from collector.errors import ErrorInfo
from collector.fetch import FakeFetcher
from collector.registry import Source


# --- (4) quarantine_started は公開データに出さない -----------------------------------------
def test_quarantine_started_stays_out_of_the_public_latest_json(tmp_path, monkeypatch):
    src = Source(slug="a1", name="a1市", municipality="a1", prefecture="東京都", url="https://a.jp/a1", kind="stray", species="dog")
    fail = run_mod.Collected("failed", None, "x", error_info=ErrorInfo("parser", host="a.jp").to_dict())
    monkeypatch.setattr(run_mod, "collect_one", lambda s, f: fail)
    monkeypatch.setattr(repair_gate, "context_hash", lambda: "ctx")
    from collector.ai_repair import RepairResult

    def fake(source, attempt=None, **kw):
        attempt.update(reached="ran", entry={"url": source.url, "sha256": "x", "bytes": 1, "is_html": True})
        return RepairResult(source.slug, "failed", error="新レシピでも 0 頭")

    monkeypatch.setattr(ai_repair, "repair", fake)
    out = None
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        out = run_mod.run([src], d, out_dir=tmp_path / "data", fetcher=FakeFetcher({src.url: "<html></html>"}), enabled=True)
    assert out is not None
    report = json.loads((tmp_path / "data" / "report-2026-11-03.json").read_text(encoding="utf-8"))
    assert report[0]["quarantine_started"] is True   # 通知は report から読む
    latest = json.loads((tmp_path / "data" / "latest.json").read_text(encoding="utf-8"))
    assert "quarantine_started" not in latest["sources"][0]
    assert "quarantine_started" not in out["sources"][0]
    dated = json.loads((tmp_path / "data" / "animals-2026-11-03.json").read_text(encoding="utf-8"))
    assert "quarantine_started" not in dated["sources"][0]


