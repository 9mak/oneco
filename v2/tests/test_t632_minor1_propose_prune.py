"""W006 T632 の小さな直し (1) propose: fetch --prune。ネットワークなし。"""

from __future__ import annotations

from collector import propose as pr
from test_propose import BODY, HEADER, Recorder


# --- (1) propose: fetch --prune ----------------------------------------------------
def test_propose_prunes_remote_tracking_refs_before_the_lease_push(tmp_path, monkeypatch):
    """close した PR のブランチをリモートで消すと、手元に残った origin/repair/<slug> が古い情報になり、
    --force-with-lease が stale info で失敗する（2026-11-06 pref_hiroshima-1）。push の前に fetch --prune で掃除する。"""
    pdir = tmp_path / "proposals"
    pdir.mkdir()
    (pdir / "city_a.yaml").write_text(HEADER + BODY, encoding="utf-8")
    monkeypatch.setenv("ONECO_REPAIR_CLONE", str(tmp_path / "clone"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(pr, "load_sources", lambda: [])
    rec = Recorder()
    monkeypatch.setattr(pr.subprocess, "run", rec)
    assert pr.propose(proposals_dir=pdir, today="20261106") == 0
    names = [" ".join(c) for c in rec.calls]
    fetch = next(i for i, c in enumerate(names) if " fetch " in f" {c} " and "--prune" in c)
    push = next(i for i, c in enumerate(names) if " push " in f" {c} ")
    assert fetch < push


