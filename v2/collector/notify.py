"""異常のある日だけ Discord に 1 通。平常時は何も送らない。"""

from __future__ import annotations

import json
import os

import httpx

from .run import DATA_DIR


def build_message(report: list[dict]) -> str | None:
    """異常（読めなかった / AI がレシピを書き直した）が無ければ None。"""
    failed = [r for r in report if r["status"] == "failed"]
    repaired = [r for r in report if r["status"] != "failed" and (r.get("repair") or "").startswith("AI がレシピを書き直した")]
    if not failed and not repaired:
        return None
    lines = []
    if failed:
        lines.append(f"読めなかった自治体 {len(failed)} 件")
        for r in failed:
            line = f"- {r['name']}: {r['error']}"
            if r.get("repair"):
                line += f"（{r['repair']}）"
            lines.append(line)
    if repaired:
        lines.append(f"AI がレシピを書き直した自治体 {len(repaired)} 件（recipes/<slug>.yaml が変わっている。中身を確認して repo に反映する）")
        for r in repaired:
            lines.append(f"- {r['name']}: {r['repair']}")
    ok = sum(r["count"] for r in report if r["status"] == "ok")
    lines.append(f"（公開 {ok} 頭・成功 {sum(1 for r in report if r['status'] in ('ok', 'empty'))} ページ）")
    return "\n".join(lines)[:1900]


def notify(dry_run: bool = False) -> int:
    reports = sorted(DATA_DIR.glob("report-*.json"))
    if not reports:
        print("report が無い")
        return 1
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    msg = build_message(report)
    if msg is None:
        print(f"{reports[-1].name}: 異常なし。送らない")
        return 0
    print(msg)
    if dry_run:
        return 0
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("DISCORD_WEBHOOK_URL が無いので送らない")
        return 1
    httpx.post(url, json={"content": msg}, timeout=15).raise_for_status()
    return 0
