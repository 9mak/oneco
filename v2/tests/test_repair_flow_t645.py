"""W006 T645: 修復の 1 晩の流れ（選別 → エージェント → 検査 → PR → AI レビュー → 通知）。
本物の agy・claude・git・gh・Discord は呼ばない（すべて差し替え）。"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from collector import repair_agent as ra
from collector import repair_check as rcheck
from collector import repair_flow as flow
from collector.registry import Source

DATE = "2026-11-21"


def _src(slug: str) -> Source:
    return Source(slug=slug, name=f"{slug}市", municipality="A市", prefecture="P県", url=f"https://{slug}.example/", kind="adoption")


def _sel(slug: str) -> dict:
    return {"slug": slug, "name": f"{slug}市", "url": f"https://{slug}.example/", "kind": "adoption", "species": "dog",
            "error": "0 頭で empty_text も無い", "error_kind": "parser", "http_status": None}


class Env:
    """flow が呼ぶ外部を全部差し替える。"""

    def __init__(self, monkeypatch, tmp_path: Path, agent_ok: dict[str, bool] | None = None, key: str | None = "sk-key") -> None:
        self.tmp = tmp_path
        self.calls: list[tuple] = []
        self.agent_ok = agent_ok or {}
        self.published: list[dict] = []
        self.reviews: list[tuple[str, str]] = []
        self.sent: list[str] = []
        clone = tmp_path / "clone"
        monkeypatch.setenv("ONECO_REPAIR_CLONE", str(clone))
        monkeypatch.delenv("ONECO_REPAIR_CLAUDE", raising=False)
        monkeypatch.setattr(flow, "load_sources", lambda *a, **k: [_src(s) for s in ("a", "b", "c")])
        monkeypatch.setattr(ra, "prepare_worktree", lambda slug, clone: self._wt(slug))
        monkeypatch.setattr(ra, "remove_worktree", lambda slug, clone: self.calls.append(("remove", slug)))
        monkeypatch.setattr(ra, "read_api_key", lambda *a, **k: key)
        monkeypatch.setattr(ra, "run_agent", self._agent)
        monkeypatch.setattr(rcheck, "check", self._check)
        monkeypatch.setattr(flow, "publish_pr", self._publish)
        monkeypatch.setattr(flow, "ai_review", lambda url, wt, writer: self.reviews.append((url, writer)) or f"reviewed by other than {writer}")
        monkeypatch.setattr(flow, "_notify", lambda msg: self.sent.append(msg))
        monkeypatch.setattr(flow, "manual_text", lambda: "MANUAL")

    def _wt(self, slug: str) -> Path:
        p = self.tmp / "wt" / slug
        p.mkdir(parents=True, exist_ok=True)
        self.calls.append(("prepare", slug))
        return p

    def _agent(self, runner, prompt, wt, env, remaining_s, run=None):
        self.calls.append(("agent", runner, wt.name, remaining_s, dict(env)))
        return {"runner": runner, "cmd": [runner], "env_keys": sorted(env), "returncode": 0, "timed_out": False,
                "stdout": "{}", "stderr": "", "error": None, "seconds": 100.0, "summary": f"{runner} が直した"}

    def _check(self, slug, wt, **kw):
        runner = next(c[1] for c in reversed(self.calls) if c[0] == "agent")
        ok = self.agent_ok.get(f"{slug}:{runner}", self.agent_ok.get(slug, True))
        self.calls.append(("check", slug, runner))
        details = {"before_count": 0, "after_count": 3, "tests_added": 4, "tests_total": 4052, "regression_compared": 1,
                   "changed_files": ["v2/recipes/x.yaml"]}
        return rcheck.CheckResult(ok, [] if ok else ["退行: 過去の fixture で頭数 2→0"], details)

    def _publish(self, **kw):
        self.published.append(kw)
        return f"https://github.test/pr/{kw['slug']}"

    def process(self, slug="a", **kw):
        return flow.process_slug(_sel(slug), DATE, self.tmp / "data", flow.Budget(3600), **kw)


@pytest.fixture
def env(monkeypatch, tmp_path):
    return Env(monkeypatch, tmp_path)


def _record(env: Env, slug: str = "a", name: str | None = None) -> dict:
    return json.loads((env.tmp / "data" / "repair-attempts" / DATE / f"{name or slug}.json").read_text(encoding="utf-8"))


def test_agy_success_creates_pr_reviews_with_other_runner_and_records(env):
    r = env.process("a")
    assert r["outcome"] == "pr_created" and r["pr_url"] == "https://github.test/pr/a" and r["runner"] == "agy"
    assert [c[1] for c in env.calls if c[0] == "agent"] == ["agy"]
    assert env.reviews == [("https://github.test/pr/a", "agy")]
    pub = env.published[0]
    assert pub["runner"] == "agy" and pub["details"]["after_count"] == 3 and pub["fallback_from"] is None
    rec = _record(env)
    assert rec["outcome"] == "pr_created" and rec["pr_url"] and rec["attempts"][0]["runner"] == "agy"
    assert ("remove", "a") in env.calls


def test_agent_env_given_to_agent_has_no_secret(env, monkeypatch):
    monkeypatch.setenv("ONECO_GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.invalid/h")
    env.process("a")
    given = next(c[4] for c in env.calls if c[0] == "agent")
    assert "ONECO_GITHUB_TOKEN" not in given and "DISCORD_WEBHOOK_URL" not in given


def test_agy_fails_check_and_claude_is_not_used_without_opt_in(env):
    env.agent_ok = {"a": False}
    r = env.process("a")
    assert r["outcome"] == "failed" and "退行" in r["reason"]
    assert [c[1] for c in env.calls if c[0] == "agent"] == ["agy"]
    assert env.published == []


def test_claude_fallback_passes_and_is_named_in_pr(env, monkeypatch):
    monkeypatch.setenv("ONECO_REPAIR_CLAUDE", "1")
    env.agent_ok = {"a:agy": False, "a:claude": True}
    r = env.process("a")
    assert r["outcome"] == "pr_created" and r["runner"] == "claude"
    assert [c[1] for c in env.calls if c[0] == "agent"] == ["agy", "claude"]
    pub = env.published[0]
    assert pub["runner"] == "claude" and "退行" in pub["fallback_from"]
    assert env.reviews == [("https://github.test/pr/a", "claude")]
    # claude にだけ key が渡る
    envs = {c[1]: c[4] for c in env.calls if c[0] == "agent"}
    assert envs["claude"].get("ANTHROPIC_API_KEY") == "sk-key" and "ANTHROPIC_API_KEY" not in envs["agy"]
    # 2 回目の worktree は切り直す
    assert [c for c in env.calls if c[0] == "prepare"] == [("prepare", "a"), ("prepare", "a")]


def test_claude_not_used_without_keychain_key(monkeypatch, tmp_path):
    e = Env(monkeypatch, tmp_path, key=None)
    monkeypatch.setenv("ONECO_REPAIR_CLAUDE", "1")
    e.agent_ok = {"a": False}
    r = e.process("a")
    assert r["outcome"] == "failed" and [c[1] for c in e.calls if c[0] == "agent"] == ["agy"]


def test_runner_option_runs_only_that_runner(env):
    env.process("a", runners=["claude"])
    assert [c[1] for c in env.calls if c[0] == "agent"] == ["claude"]


def test_dry_run_does_not_publish_and_writes_separate_record(env):
    r = env.process("a", dry_run=True)
    assert r["outcome"] == "dry_run_ok" and env.published == [] and env.reviews == []
    assert _record(env, name="a.dry-run")["outcome"] == "dry_run_ok"
    assert not (env.tmp / "data" / "repair-attempts" / DATE / "a.json").exists()   # 今夜の本番の試行を止めない


def test_budget_exhausted_skips_agent_without_record(env):
    b = flow.Budget(3600)
    b.spent = 3600 - 60
    r = flow.process_slug(_sel("a"), DATE, env.tmp / "data", b)
    assert r["outcome"] == "skipped" and "予算" in r["reason"] and not any(c[0] == "agent" for c in env.calls)
    assert not (env.tmp / "data" / "repair-attempts" / DATE / "a.json").exists()


def test_budget_is_spent_by_agent_seconds(env):
    b = flow.Budget(3600)
    flow.process_slug(_sel("a"), DATE, env.tmp / "data", b)
    assert b.spent == 100.0 and b.remaining() == 3500


def test_process_survives_unexpected_error(env, monkeypatch):
    def boom(slug, clone):
        raise flow.StepError("git が失敗")

    monkeypatch.setattr(ra, "prepare_worktree", boom)
    r = env.process("a")
    assert r["outcome"] == "failed" and "git が失敗" in r["reason"]


def test_agent_crash_or_timeout_is_named_in_the_reason(env, monkeypatch):
    env.agent_ok = {"a": False}
    orig = env._agent

    def crashed(runner, prompt, wt, e, remaining_s, run=None):
        return {**orig(runner, prompt, wt, e, remaining_s), "returncode": 1, "summary": "authentication failed or timed out"}

    monkeypatch.setattr(ra, "run_agent", crashed)
    r = env.process("a")
    assert r["outcome"] == "failed" and "異常終了（exit 1）" in r["reason"] and "authentication failed" in r["reason"]


def test_pr_body_has_numbers_runner_and_manual_version():
    body = flow.pr_body(_sel("a"), "agy", 321.4, {"before_count": 0, "after_count": 3, "tests_added": 4, "tests_total": 4052,
                                                    "regression_compared": 2}, "abcd1234", "agy の要約", None)
    for s in ("slug: a", "A市" if False else "a市", "0 頭で empty_text も無い", "直す前 0 頭", "直した後 3 頭", "4 本", "4052 本",
              "agy", "321", "abcd1234", "agy の要約", "draft", "merge"):
        assert s in body
    fb = flow.pr_body(_sel("a"), "claude", 10, {}, "abcd1234", "x", "退行: 過去の fixture で頭数 2→0")
    assert "agy では通らず" in fb and "claude で通った" in fb and "退行" in fb


def test_review_runner_is_the_other_one(monkeypatch):
    monkeypatch.setattr(ra, "read_api_key", lambda *a, **k: "k")
    monkeypatch.delenv("ONECO_REPAIR_CLAUDE", raising=False)
    assert flow.review_runner("agy") is None            # claude は ONECO_REPAIR_CLAUDE=1 のときだけ（API の費用）
    monkeypatch.setenv("ONECO_REPAIR_CLAUDE", "1")
    assert flow.review_runner("agy") == "claude" and flow.review_runner("claude") == "agy"
    monkeypatch.setattr(ra, "read_api_key", lambda *a, **k: None)
    assert flow.review_runner("agy") is None and flow.review_runner("claude") == "agy"


class _P:
    def __init__(self, out="", code=0, err=""):
        self.stdout, self.returncode, self.stderr = out, code, err


def test_publish_pr_commits_pushes_branch_and_creates_draft(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake(cmd, **kw):
        calls.append(list(cmd))
        if cmd[:3] == ["gh", "pr", "create"]:
            return _P("https://github.test/pull/9\n")
        return _P()

    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.delenv("ONECO_GITHUB_TOKEN", raising=False)
    url = flow.publish_pr(slug="a", name="a市", wt=tmp_path, sel=_sel("a"), runner="agy", seconds=5, details={}, manual_ver="m",
                          summary="s", fallback_from=None)
    assert url == "https://github.test/pull/9"
    flat = [" ".join(c) for c in calls]
    assert any("add -A" in c for c in flat) and any("commit" in c for c in flat)
    push = next(c for c in flat if " push " in c)
    assert "--force-with-lease" in push and push.endswith("origin repair/a")
    create = next(c for c in calls if c[:3] == ["gh", "pr", "create"])
    assert "--draft" in create and "--head" in create and create[create.index("--head") + 1] == "repair/a"


def test_publish_pr_skips_when_open_pr_exists(monkeypatch, tmp_path):
    def fake(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "list"]:
            return _P("https://github.test/pull/3\n")
        return _P()

    monkeypatch.setattr(subprocess, "run", fake)
    with pytest.raises(flow.StepError, match="open な PR"):
        flow.publish_pr(slug="a", name="a市", wt=tmp_path, sel=_sel("a"), runner="agy", seconds=5, details={}, manual_ver="m",
                        summary="s", fallback_from=None)


def test_review_commands_are_read_only():
    a = ra.review_command("agy", "P")
    assert a[a.index("--mode") + 1] == "plan" and "auto" not in a
    c = ra.review_command("claude", "P")
    assert c[c.index("--permission-mode") + 1] == "plan" and "Edit" not in c[c.index("--allowedTools") + 1]


def test_night_message_counts_and_reasons():
    msg = flow.night_message(DATE, [
        {"slug": "a", "outcome": "pr_created", "pr_url": "https://github.test/pr/a"},
        {"slug": "b", "outcome": "failed", "reason": "退行: 過去の fixture で頭数 2→0"},
        {"slug": "c", "outcome": "skipped", "reason": "1 晩の予算（60 分）を使い切った"},
    ])
    assert "直した PR 1 件" in msg and "直せなかった slug 2 件" in msg and "https://github.test/pr/a" in msg
    assert "b（退行" in msg and "c（1 晩の予算" in msg


def _night_env(env: Env, monkeypatch, tmp_path: Path, slugs: list[str]) -> Path:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / f"report-{DATE}.json").write_text(json.dumps([
        {"slug": s, "name": s, "status": "failed", "count": 0, "error": "0 頭で empty_text も無い",
         "error_info": {"kind": "parser", "status": None, "host": f"{s}.example", "url": None}} for s in slugs]), encoding="utf-8")
    monkeypatch.setattr(flow, "unmerged_repair_branches", lambda: (set(), None))
    monkeypatch.setattr(flow, "load_state", lambda *a, **k: {"sources": {}, "repair_hosts": {}})
    monkeypatch.setattr(flow, "save_state", lambda *a, **k: None)
    return data


def test_night_runs_each_selected_slug_and_sends_one_message(env, monkeypatch, tmp_path):
    data = _night_env(env, monkeypatch, tmp_path, ["a", "b", "c"])
    env.agent_ok = {"b": False}
    assert flow.night(DATE, data_dir=data) == 0
    assert (data / f"repair-plan-{DATE}.json").exists()
    assert [p["slug"] for p in env.published] == ["a", "c"]
    assert len(env.sent) == 1 and "直した PR 2 件" in env.sent[0] and "直せなかった slug 1 件" in env.sent[0]


def test_night_sends_nothing_when_nothing_selected(env, monkeypatch, tmp_path):
    data = _night_env(env, monkeypatch, tmp_path, [])
    assert flow.night(DATE, data_dir=data) == 0 and env.sent == []


def test_night_without_report_returns_0_and_does_nothing(env, monkeypatch, tmp_path):
    monkeypatch.setattr(flow, "unmerged_repair_branches", lambda: (set(), None))
    assert flow.night(DATE, data_dir=tmp_path / "empty") == 0 and env.sent == []


def test_night_stops_new_slugs_when_night_budget_is_gone(env, monkeypatch, tmp_path):
    data = _night_env(env, monkeypatch, tmp_path, ["a", "b", "c"])
    monkeypatch.setattr(ra, "NIGHT_BUDGET_S", 150)
    flow.night(DATE, data_dir=data)
    agents = [c for c in env.calls if c[0] == "agent"]
    assert len(agents) == 1      # 150 秒の予算で、1 件目が 100 秒使うと残り 50 秒（猶予 30 秒を引くと足りない）
    assert "予算" in env.sent[0]


# --- collect.sh の分岐 ---------------------------------------------------------
COLLECT = Path(__file__).resolve().parent.parent / "ops" / "collect.sh"


def _run_collect(tmp_path: Path, **extra: str) -> str:
    fake = tmp_path / "py"
    log = tmp_path / "args.log"
    fake.write_text(f'#!/bin/bash\necho "$@" >> {log}\nexit 0\n', encoding="utf-8")
    fake.chmod(0o755)
    base = {k: v for k, v in os.environ.items() if not k.startswith(("ONECO_", "DISCORD", "HEALTHCHECK", "CLOUDFLARE"))}
    env = {**base, "ONECO_V2_DIR": str(tmp_path / "v2"), "ONECO_PY": str(fake), "ONECO_LOG_DIR": str(tmp_path / "logs"), **extra}
    (tmp_path / "v2").mkdir(exist_ok=True)
    p = subprocess.run(["bash", str(COLLECT)], env=env, capture_output=True, text=True, timeout=60, check=False)
    assert p.returncode == 0, p.stdout + p.stderr
    return log.read_text(encoding="utf-8")


def test_collect_sh_agent_mode_skips_old_repair_and_propose(tmp_path):
    out = _run_collect(tmp_path, ONECO_REPAIR_AGENT="1", ONECO_AI_REPAIR="1")
    assert "-m collector run --no-ai-repair" in out
    assert "-m collector repair-night" in out
    assert "-m collector propose" not in out
    # 順序: notify の後、build の前
    assert out.index("collector notify") < out.index("repair-night") < out.index("build.py")


def test_collect_sh_old_mode_without_agent_flag(tmp_path):
    out = _run_collect(tmp_path, ONECO_AI_REPAIR="1")
    assert "-m collector run\n" in out and "--no-ai-repair" not in out
    assert "-m collector propose" in out and "repair-night" not in out


def test_collect_sh_neither(tmp_path):
    out = _run_collect(tmp_path)
    assert "repair-night" not in out and "-m collector propose" not in out


def test_collect_sh_repair_failure_does_not_stop_build_or_fail_the_day(tmp_path):
    fake = tmp_path / "py"
    log = tmp_path / "args.log"
    fake.write_text(f'#!/bin/bash\necho "$@" >> {log}\ncase "$*" in *repair-night*) exit 5;; esac\nexit 0\n', encoding="utf-8")
    fake.chmod(0o755)
    base = {k: v for k, v in os.environ.items() if not k.startswith(("ONECO_", "DISCORD", "HEALTHCHECK", "CLOUDFLARE"))}
    (tmp_path / "v2").mkdir(exist_ok=True)
    env = {**base, "ONECO_V2_DIR": str(tmp_path / "v2"), "ONECO_PY": str(fake), "ONECO_LOG_DIR": str(tmp_path / "logs"),
           "ONECO_REPAIR_AGENT": "1"}
    p = subprocess.run(["bash", str(COLLECT)], env=env, capture_output=True, text=True, timeout=60, check=False)
    assert p.returncode == 0, p.stdout
    assert "build.py" in log.read_text(encoding="utf-8")
