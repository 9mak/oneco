"""W006 T645: 修復エージェントの起動（コマンドの組み立て・環境変数の絞り込み・worktree・予算）。本物の agy・claude は呼ばない。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from collector import repair_agent as ra
from collector.registry import Source

SECRETS = {
    "ONECO_GITHUB_TOKEN": "ghp_x", "CLOUDFLARE_API_TOKEN": "cf", "CLOUDFLARE_ACCOUNT_ID": "acc",
    "DISCORD_WEBHOOK_URL": "https://discord.invalid/hook", "HEALTHCHECK_URL": "https://hc.invalid/x",
    "ANTHROPIC_API_KEY": "sk-ant-x", "AWS_SECRET_ACCESS_KEY": "aws", "GH_TOKEN": "gh", "GITHUB_TOKEN": "gh2",
    "OPENAI_API_KEY": "oa",
}
BASE = {"PATH": "/usr/bin:/bin", "HOME": "/Users/x", "LANG": "ja_JP.UTF-8", "TERM": "xterm", **SECRETS}


def _src() -> Source:
    return Source(slug="city_a-1", name="A市", municipality="A市", prefecture="P県",
                  url="https://a.example/list.html", kind="adoption", species="dog")


def test_agent_env_is_an_allowlist_and_has_no_secret():
    env = ra.agent_env("agy", BASE)
    assert set(env) <= set(ra.ENV_ALLOW)
    for k in SECRETS:
        assert k not in env
    assert env["HOME"] == "/Users/x" and env["LANG"] == "ja_JP.UTF-8"


def test_agent_env_prepends_python_dir_to_path():
    env = ra.agent_env("agy", BASE, python_dir="/venv/bin")
    assert env["PATH"].split(":")[0] == "/venv/bin"


def test_claude_gets_only_the_api_key_it_was_given():
    env = ra.agent_env("claude", BASE, api_key="sk-keychain")
    assert env["ANTHROPIC_API_KEY"] == "sk-keychain"
    for k in SECRETS:
        if k != "ANTHROPIC_API_KEY":
            assert k not in env
    # agy には、key を渡されても入れない。claude でも key が無ければ（環境の値は使わず）入れない
    assert "ANTHROPIC_API_KEY" not in ra.agent_env("agy", BASE, api_key="sk-keychain")
    assert "ANTHROPIC_API_KEY" not in ra.agent_env("claude", BASE)


def test_agy_command():
    cmd = ra.agent_command("agy", "PROMPT", 900)
    assert cmd[:3] == ["agy", "-p", "PROMPT"]
    assert cmd[cmd.index("--mode") + 1] == "auto"
    assert "--sandbox" in cmd and "--add-dir" not in cmd
    assert cmd[cmd.index("--model") + 1] == "Gemini 4 Hydrogen (High)"
    assert cmd[cmd.index("--print-timeout") + 1] == "900s"
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_claude_command():
    cmd = ra.agent_command("claude", "PROMPT", 900)
    assert cmd[:3] == ["claude", "-p", "PROMPT"]
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    tools = cmd[cmd.index("--allowedTools") + 1]
    assert tools == "Read,Edit,Write,Bash(python*),Bash(curl*),Glob,Grep"
    assert cmd[cmd.index("--max-turns") + 1] == "60"
    assert cmd[cmd.index("--output-format") + 1] == "json"


def test_prompt_has_manual_slug_and_exact_file_names():
    p = ra.build_prompt("MANUAL TEXT", _src(), "0 頭で empty_text も無い", "20261121")
    assert "MANUAL TEXT" in p and "city_a-1" in p and "https://a.example/list.html" in p
    assert "v2/recipes/city_a-1.yaml" in p
    assert "v2/tests/test_repair_city_a-1_20261121.py" in p
    assert "v2/tests/fixtures/repair_city_a-1_20261121.html" in p
    assert "0 頭で empty_text も無い" in p
    assert "信頼できない" in p


def test_manual_version_is_short_hash(tmp_path):
    f = tmp_path / "m.md"
    f.write_text("abc", encoding="utf-8")
    v = ra.manual_version(f)
    assert len(v) == 8 and v == ra.manual_version(f)


class _P:
    def __init__(self, out="{}", code=0, err=""):
        self.stdout, self.returncode, self.stderr = out, code, err


def test_run_agent_runs_in_worktree_with_restricted_env_and_records(tmp_path):
    seen: dict = {}

    def fake(cmd, **kw):
        seen.update(kw, cmd=cmd)
        return _P('{"result": "直した"}')

    env = ra.agent_env("agy", BASE)
    rec = ra.run_agent("agy", "PROMPT", tmp_path, env, remaining_s=3600, run=fake)
    assert seen["cwd"] == tmp_path and seen["env"] == env and seen["timeout"] <= 930
    assert rec["runner"] == "agy" and rec["returncode"] == 0 and rec["timed_out"] is False
    assert rec["stdout"] == '{"result": "直した"}' and rec["summary"] == "直した"
    assert sorted(rec["env_keys"]) == sorted(env)
    assert "PROMPT" not in " ".join(rec["cmd"])     # 記録には指示文を入れない（長い）


def test_run_agent_caps_timeout_by_remaining_budget(tmp_path):
    seen: dict = {}

    def fake(cmd, **kw):
        seen.update(kw, cmd=cmd)
        return _P()

    ra.run_agent("agy", "P", tmp_path, {}, remaining_s=120, run=fake)
    assert seen["timeout"] <= 120 and seen["cmd"][seen["cmd"].index("--print-timeout") + 1] == "90s"


def test_run_agent_timeout(tmp_path):
    def fake(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1, output=b"partial", stderr=b"")

    rec = ra.run_agent("agy", "P", tmp_path, {}, remaining_s=3600, run=fake)
    assert rec["timed_out"] is True and rec["returncode"] is None and "partial" in rec["stdout"]


def test_run_agent_missing_binary(tmp_path):
    def fake(cmd, **kw):
        raise FileNotFoundError("agy")

    rec = ra.run_agent("agy", "P", tmp_path, {}, remaining_s=3600, run=fake)
    assert rec["returncode"] is None and "FileNotFoundError" in rec["error"]


def test_summary_falls_back_to_tail_of_stdout(tmp_path):
    rec = ra.run_agent("claude", "P", tmp_path, {}, remaining_s=3600, run=lambda c, **k: _P("x" * 5000))
    assert rec["summary"] == "x" * 1500


def test_read_api_key_from_keychain_or_none():
    got = ra.read_api_key(run=lambda cmd, **kw: _P("sk-ant-abc\n"))
    assert got == "sk-ant-abc"
    assert ra.read_api_key(run=lambda cmd, **kw: _P("", 44, "not found")) is None
    seen: list[list[str]] = []
    ra.read_api_key(run=lambda cmd, **kw: seen.append(cmd) or _P("k"))
    assert "oneco-anthropic-api-key" in seen[0] and seen[0][0] == "security"


def test_prepare_worktree_cuts_branch_from_origin_main_in_work_clone(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)

    def fake(cmd, **kw):
        calls.append(list(cmd))
        return _P()

    monkeypatch.setattr(subprocess, "run", fake)
    wt = ra.prepare_worktree("city_a-1", clone)
    assert wt == tmp_path / ".repair-wt" / "city_a-1"
    flat = [" ".join(c) for c in calls]
    assert any("fetch --prune origin" in c for c in flat)
    add = next(c for c in flat if "worktree add" in c)
    assert "-B repair/city_a-1" in add and str(wt) in add and add.endswith("origin/main")
    assert all(c.startswith("git ") for c in flat)


def test_attempt_record_is_written_under_data_dir(tmp_path):
    p = ra.write_attempt_record(tmp_path, "2026-11-21", "a", {"outcome": "failed", "x": 1})
    assert p == tmp_path / "repair-attempts" / "2026-11-21" / "a.json"
    assert '"outcome": "failed"' in p.read_text(encoding="utf-8")


def test_worktree_lives_outside_production_dir(tmp_path):
    clone = Path("/Users/k/oneco-collect/.repair-clone")
    assert str(ra.worktree_path("a", clone)) == "/Users/k/oneco-collect/.repair-wt/a"
