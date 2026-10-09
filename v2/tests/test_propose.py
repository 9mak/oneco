"""propose のテスト。git / gh / Discord は subprocess.run と httpx.post の差し替えで検証し、本物は呼ばない。"""

from pathlib import Path

import pytest
from collector import propose as pr

HEADER = "# proposal: run の日付 2026-10-09・元の失敗理由 0 頭で empty_text も無い・取れた頭数 7・採用条件はまだ通していない\n# agy note: 表の行を 1 頭とした\n"
BODY = "rows: \"table.list tr\"\nfields:\n  sex: \"td\"\n"


class _P:
    def __init__(self, out="", code=0, err=""):
        self.stdout, self.returncode, self.stderr = out, code, err


class Recorder:
    def __init__(self, fail_on: str | None = None, open_pr: str = ""):
        self.calls: list[list[str]] = []
        self.fail_on, self.open_pr = fail_on, open_pr

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        if cmd[:2] == ["git", "-C"] and cmd[3] == "remote":
            return _P("https://example.test/repo.git\n")
        if self.fail_on and self.fail_on in cmd:
            return _P("", 1, "boom")
        if cmd[:3] == ["gh", "pr", "list"]:
            return _P(self.open_pr)
        if cmd[:3] == ["gh", "pr", "create"]:
            return _P("https://github.test/pr/9\n")
        if cmd[:2] == ["git", "clone"]:
            Path(cmd[-1], ".git").mkdir(parents=True)
        return _P()


@pytest.fixture
def env(tmp_path, monkeypatch):
    pdir = tmp_path / "proposals"
    pdir.mkdir()
    clone = tmp_path / "clone"
    monkeypatch.setenv("ONECO_REPAIR_CLONE", str(clone))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(pr, "load_sources", lambda: [])
    sent: list[dict] = []
    monkeypatch.setattr(pr.httpx, "post", lambda url, json, timeout: sent.append(json) or _R())
    return pdir, clone, sent


class _R:
    def raise_for_status(self):
        pass


def _add(pdir: Path, slug: str, body: str = BODY) -> Path:
    f = pdir / f"{slug}.yaml"
    f.write_text(HEADER + body, encoding="utf-8")
    return f


def test_creates_draft_pr_and_moves_proposal(env, monkeypatch):
    pdir, clone, sent = env
    _add(pdir, "city_a")
    rec = Recorder()
    monkeypatch.setattr(pr.subprocess, "run", rec)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/hook")
    assert pr.propose(proposals_dir=pdir, today="20261010") == 0
    cmds = [" ".join(c) for c in rec.calls]
    assert any(c.startswith("git clone --quiet https://example.test/repo.git") for c in cmds)
    assert any("checkout -B repair/city_a-20261010 origin/main" in c for c in cmds)
    assert any("push -u origin repair/city_a-20261010" in c for c in cmds)
    assert not any(c[:3] == ["gh", "pr", "merge"] for c in rec.calls)
    create = next(c for c in rec.calls if c[:3] == ["gh", "pr", "create"])
    assert "--draft" in create
    body = create[create.index("--body") + 1]
    assert "city_a" in body and "0 頭で empty_text も無い" in body and "7" in body and "表の行を 1 頭とした" in body
    assert "merge すれば翌日の収集から本番に入る" in body
    copied = (clone / "v2" / "recipes" / "city_a.yaml").read_text(encoding="utf-8")
    assert copied.startswith("# proposal:")   # 手がかりのコメントを消さない
    assert not (pdir / "city_a.yaml").exists() and (pdir / "done" / "city_a-20261010.yaml").exists()
    assert sent == [{"content": "レシピ案 PR: https://github.test/pr/9（city_a）"}]


def test_skips_open_pr_and_same_content(env, monkeypatch):
    pdir, _, _ = env
    _add(pdir, "city_a")
    rec = Recorder(open_pr="https://github.test/pr/1\n")
    monkeypatch.setattr(pr.subprocess, "run", rec)
    assert pr.propose(proposals_dir=pdir, today="20261010") == 0
    assert not any(c[:3] == ["gh", "pr", "create"] for c in rec.calls)
    assert (pdir / "city_a.yaml").exists()   # 作っていないので移さない
    # 本番レシピと同じ中身（コメントだけ違う）なら飛ばす
    fake_root = pdir.parent / "v2"
    (fake_root / "recipes").mkdir(parents=True)
    (fake_root / "recipes" / "zz_same.yaml").write_text(BODY, encoding="utf-8")
    monkeypatch.setattr(pr, "ROOT", fake_root)
    _add(pdir, "zz_same")
    rec2 = Recorder()
    monkeypatch.setattr(pr.subprocess, "run", rec2)
    pr.propose(proposals_dir=pdir, today="20261010")
    assert not any("zz_same" in " ".join(c) for c in rec2.calls)


def test_max_five_and_failure_does_not_stop(env, monkeypatch):
    pdir, _, _ = env
    for i in range(8):
        _add(pdir, f"city_{i}")
    rec = Recorder(fail_on="repair/city_0-20261010")   # 最初の 1 件の checkout が失敗
    monkeypatch.setattr(pr.subprocess, "run", rec)
    assert pr.propose(proposals_dir=pdir, today="20261010") == 1
    creates = [c for c in rec.calls if c[:3] == ["gh", "pr", "create"]]
    assert len(creates) == pr.MAX_PR_PER_RUN
    assert (pdir / "city_0.yaml").exists()   # 失敗した案は残す
    assert len(list((pdir / "done").glob("*.yaml"))) == 5


def test_dry_run_runs_nothing(env, monkeypatch):
    pdir, _, _ = env
    _add(pdir, "city_a")
    monkeypatch.setattr(pr.subprocess, "run", lambda *a, **k: pytest.fail("dry-run は何も呼ばない"))
    assert pr.propose(dry_run=True, proposals_dir=pdir, today="20261010") == 0
    assert (pdir / "city_a.yaml").exists()
