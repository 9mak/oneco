"""異常のある日だけ Discord に 1 通。平常時は何も送らない。

同じ失敗を毎日送らない（W006 T608）。通知するのは 3 種だけ:
  初回      その slug の失敗の fingerprint（slug:kind:status:host）が前回通知したものと違う
  3 日継続  連続失敗が 3 日目、以降 7 日ごと（10・17・24 日目…）
  復旧      前回 failed / ambiguous_empty で、今回 ok / empty
回線断の日は従来どおり先頭に 1 行。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from .run import DATA_DIR, outage
from .state import FAILING, GOOD, STATE_DIR, load_state, save_state

REPEAT_FIRST = 3    # 継続通知の 1 回目（連続失敗の日数）
REPEAT_EVERY = 7    # 以降の間隔（日）


def fingerprint(r: dict[str, Any]) -> str:
    info = r.get("error_info") or {}
    return f"{r['slug']}:{info.get('kind')}:{info.get('status') or ''}:{info.get('host') or ''}"


def decide(report: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """通知する行を決める。[{type: first|continuing|recovered, row, fp, days, st}]"""
    sources = state.get("sources", {})
    out = []
    for r in report:
        st = sources.get(r["slug"], {})
        if r["status"] in FAILING:
            fp, days = fingerprint(r), max(st.get("consecutive_failures", 1), 1)
            n = st.get("notified") or {}
            if n.get("fingerprint") != fp:
                typ = "first"
            elif days >= REPEAT_FIRST and (days - REPEAT_FIRST) % REPEAT_EVERY == 0 and n.get("days") != days:
                typ = "continuing"
            else:
                continue
            out.append({"type": typ, "row": r, "fp": fp, "days": days, "st": st})
        elif r["status"] in GOOD and st.get("prev_status") in FAILING:
            out.append({"type": "recovered", "row": r, "fp": None, "days": 0, "st": st})
    return out


def _since(st: dict[str, Any]) -> str:
    ok = st.get("last_ok")
    return f"最後に成功 {ok}（{st.get('last_ok_count', 0)} 頭）" if ok else "成功の記録なし"


def _line(e: dict[str, Any]) -> str:
    r, st = e["row"], e["st"]
    if e["type"] == "recovered":
        return f"- {r['name']}: 復旧（{r['count']} 頭）"
    if r["status"] == "ambiguous_empty":
        stale = r.get("stale_since") or st.get("last_ok") or "不明"
        text = (f"0 頭に見えるが確定できないので前日分 {r.get('count', 0)} 頭を保持（stale_since {stale}）。"
                f"{r['error']}")
    else:
        text = r["error"]
    line = f"- {r['name']}: {text}（経過 {e['days']} 日・{_since(st)}）"
    if r.get("repair"):
        line += f"（{r['repair']}）"
    return line


def build_message(report: list[dict[str, Any]], state: dict[str, Any] | None = None, today: str = "") -> str | None:
    """通知する内容が無ければ None。state が None なら状態なしとして全部を初回扱いにする。"""
    events = decide(report, state or {})
    held = outage(report)
    if not events and not held:
        return None
    lines = []
    if held:
        tr = sum(1 for r in report if (r.get("error_info") or {}).get("kind") in {"dns", "connect", "tls", "timeout"})
        lines.append(f"接続できなかったページが複数のサイトにまたがって多い（{tr} 件）。回線断などとみなし、"
                     "サイトは前日のまま。収集サーバーの回線を確かめて、直ったら手で収集し直す")
    for title, typ in (("読めなかった自治体", None), ("復旧した自治体", "recovered")):
        sel = [e for e in events if (e["type"] == "recovered") == (typ == "recovered")]
        if sel:
            lines.append(f"{title} {len(sel)} 件")
            lines.extend(_line(e) for e in sel)
    ok = sum(r["count"] for r in report if r["status"] == "ok")
    lines.append(f"（公開 {ok} 頭・成功 {sum(1 for r in report if r['status'] in GOOD)} ページ）")
    return "\n".join(lines)[:1900]


def _mark_notified(state: dict[str, Any], events: list[dict[str, Any]], today: str) -> None:
    for e in events:
        st = state.setdefault("sources", {}).setdefault(e["row"]["slug"], {})
        if e["type"] == "recovered":
            st["notified"] = None
            continue
        prev = st.get("notified") or {}
        first_at = prev.get("first_at") if prev.get("fingerprint") == e["fp"] else None
        st["notified"] = {"fingerprint": e["fp"], "first_at": first_at or today, "last_at": today,
                          "days": e["days"], "stage": e["type"]}


def notify(dry_run: bool = False, data_dir: Path = DATA_DIR, state_dir: Path = STATE_DIR) -> int:
    reports = sorted(data_dir.glob("report-20??-??-??.json"))
    if not reports:
        print("report が無い")
        return 1
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    today = reports[-1].stem.removeprefix("report-")
    state = load_state(state_dir)
    events = decide(report, state)
    msg = build_message(report, state, today)
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
    _mark_notified(state, events, today)
    save_state(state, state_dir)
    return 0
