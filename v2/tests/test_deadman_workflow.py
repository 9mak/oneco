"""v2-deadman.yml の Discord 送信（W006）: User-Agent が付く・HTTP 4xx/5xx で失敗する・test 入力で試験の文面になる。

ワークフローの run からヒアドキュメントの Python を取り出し、手元の HTTP サーバー（送信先の代わり）に向けて実際に動かす。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "v2-deadman.yml"


def _doc() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _send_script() -> str:
    step = next(s for s in _doc()["jobs"]["check"]["steps"] if "Discord" in s["name"])
    run: str = step["run"]
    start = run.index("python3 - <<'EOF'\n") + len("python3 - <<'EOF'\n")
    return run[start : run.index("\nEOF", start)]


class _Hook:
    def __init__(self, status: int) -> None:
        seen: list[dict[str, Any]] = []
        self.seen = seen

        class H(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                n = int(self.headers.get("Content-Length", 0))
                seen.append({"ua": self.headers.get("User-Agent"), "body": json.loads(self.rfile.read(n))["content"]})
                self.send_response(status)
                self.end_headers()

            def log_message(self, *a: Any) -> None: ...

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}/hook"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()


def _run(url: str, test: str = "false", stale: str = "true") -> subprocess.CompletedProcess[str]:
    env = {"WEBHOOK": url, "REASON": "公開サイトの日付が古い", "TEST": test, "STALE": stale}
    return subprocess.run([sys.executable, "-I", "-c", _send_script()], env=env, capture_output=True, text=True, timeout=30, check=False)


def test_workflow_dispatch_has_boolean_test_input() -> None:
    d = _doc()
    on = d.get(True) or d["on"]   # YAML 1.1 では on が True に読まれる
    assert on["workflow_dispatch"]["inputs"]["test"]["type"] == "boolean"
    step = next(s for s in d["jobs"]["check"]["steps"] if "Discord" in s["name"])
    assert "inputs.test" in step["if"]


def test_send_has_user_agent_and_succeeds_on_2xx() -> None:
    hook = _Hook(204)
    try:
        r = _run(hook.url)
    finally:
        hook.close()
    assert r.returncode == 0, r.stderr
    assert hook.seen[0]["ua"] and not hook.seen[0]["ua"].startswith("Python-urllib")
    assert "夜間収集が今日は走っていません" in hook.seen[0]["body"]


@pytest.mark.parametrize("status", [403, 500])
def test_http_error_fails_the_job(status: int) -> None:
    hook = _Hook(status)
    try:
        r = _run(hook.url)
    finally:
        hook.close()
    assert r.returncode == 1 and f"HTTP {status}" in r.stderr


def test_test_input_sends_a_clearly_marked_message() -> None:
    hook = _Hook(204)
    try:
        r = _run(hook.url, test="true", stale="false")
    finally:
        hook.close()
    assert r.returncode == 0, r.stderr
    assert "試験の送信です" in hook.seen[0]["body"] and "走っていません" not in hook.seen[0]["body"]
