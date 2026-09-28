"""deploy-collector.yml が宣言する Cloud Run Job の env の回帰テスト (T432)。

`gcloud run jobs update --set-env-vars` は既存 env を全置換する。挙動を変える
env をワークフローに書かず GCP 側で手で付けると、次のデプロイで消える。
T422 で有効化した ONECO_PRUNE_FULL_DELETE_ENABLED=true が翌日の T427 デプロイで
消え、5 run が dry-run に戻っていた (2026-09-20〜24) 事故の再発を止める。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deploy-collector.yml"


def _declared_env() -> dict[str, str]:
    """Update Cloud Run Job ステップの --set-env-vars を {name: value} に展開する"""
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["deploy"]["steps"]
    update_steps = [s for s in steps if "gcloud run jobs update" in (s.get("run") or "")]
    assert len(update_steps) == 1, "Update Cloud Run Job ステップは 1 つだけのはず"
    match = re.search(r'--set-env-vars\s+"([^"]+)"', update_steps[0]["run"])
    assert match, "--set-env-vars が見つからない"
    return dict(kv.split("=", 1) for kv in match.group(1).split(","))


def test_prune_full_delete_flag_is_declared_in_workflow():
    """T422 の完全削除フラグはワークフローに宣言されている (手変更は次デプロイで消える)"""
    env = _declared_env()
    assert env.get("ONECO_PRUNE_FULL_DELETE_ENABLED") == "true"


def test_declared_env_keeps_timeouts():
    """既存の宣言値を落としていない"""
    env = _declared_env()
    assert env["SITE_TIMEOUT_SEC"] == "120"
    assert env["SITE_TIMEOUT_JS_SEC"] == "180"
