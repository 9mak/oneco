"""異常のある日だけ Discord に 1 通。平常時は何も送らない。

規則は 1 つ: 読めない slug の顔ぶれが前日と変わった日だけ送る（新たに読めなくなった／読めるようになった）。
回線断の日は先頭に 1 行足して必ず送る。state は読むだけで書かない。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .run import DATA_DIR, outage
from .state import FAILING, GOOD, STATE_DIR, load_state


def decide(report: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """読めない顔ぶれが前日から変わった行を返す。state の prev_status が前日（update_sources が run の最後に書く）。
    new_failing: 今日読めず、前日は読めていた or 記録なし / recovered: 今日読めて、前日は読めなかった /
    still_failing: 前日も今日も読めない（件数だけ出す）。"""
    sources = state.get("sources", {})
    out: dict[str, list[dict[str, Any]]] = {"new_failing": [], "recovered": [], "still_failing": []}
    for r in report:
        prev = sources.get(r["slug"], {}).get("prev_status")
        if r["status"] in FAILING:
            out["still_failing" if prev in FAILING else "new_failing"].append(r)
        elif r["status"] in GOOD and prev in FAILING:
            out["recovered"].append(r)
    return out


def build_message(report: list[dict[str, Any]], state: dict[str, Any] | None = None) -> str | None:
    """通知する内容が無ければ None。state が None なら記録なしとして、読めない slug を全部新規扱いにする。"""
    ev = decide(report, state or {})
    held = outage(report)
    if not ev["new_failing"] and not ev["recovered"] and not held:
        return None
    lines = []
    if held:
        tr = sum(1 for r in report if (r.get("error_info") or {}).get("kind") in {"dns", "connect", "tls", "timeout"})
        lines.append(f"接続できなかったページが複数のサイトにまたがって多い（{tr} 件）。回線断などとみなし、"
                     "サイトは前日のまま。収集サーバーの回線を確かめて、直ったら手で収集し直す")
    if ev["new_failing"]:
        lines.append(f"新たに読めなくなった自治体 {len(ev['new_failing'])} 件")
        for r in ev["new_failing"]:
            lines.append(f"- {r['name']}: {r['error']}" + (f"（{r['repair']}）" if r.get("repair") else ""))
    if ev["recovered"]:
        lines.append(f"読めるようになった自治体 {len(ev['recovered'])} 件")
        lines.extend(f"- {r['name']}（{r['count']} 頭）" for r in ev["recovered"])
    if ev["still_failing"]:
        lines.append(f"引き続き読めない {len(ev['still_failing'])} 件")
    ok = sum(r["count"] for r in report if r["status"] == "ok")
    lines.append(f"（公開 {ok} 頭・成功 {sum(1 for r in report if r['status'] in GOOD)} ページ）")
    return "\n".join(lines)[:1900]


def notify(dry_run: bool = False, data_dir: Path = DATA_DIR, state_dir: Path = STATE_DIR) -> int:
    reports = sorted(data_dir.glob("report-20??-??-??.json"))
    if not reports:
        print("report が無い")
        return 1
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    state = load_state(state_dir)
    msg = build_message(report, state)
    if msg is None:
        print(f"{reports[-1].name}: 通知するものなし。送らない")
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
