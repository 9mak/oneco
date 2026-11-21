"""夜間の修復エージェントに渡す slug を選ぶ（W006 T645）。固定のスクリプトで、LLM は判断しない。

入力はその日の report・state・台帳・作業用クローンの未マージの repair/<slug> ブランチ。呼ばない条件は repair_gate（T635・T656）をそのまま使い、
エージェント実行に固有の条件（link_only・enabled:false・既に未マージのブランチがある・1 日 1 回・同じ slug が続けて直らない）を足す。
選んだ理由・外した理由は data/repair-plan-<日付>.json に残す。
"""

from __future__ import annotations

import json
import os
from datetime import date as date_cls
from datetime import timedelta
from pathlib import Path
from typing import Any

from . import repair_gate
from .errors import host_of
from .propose import StepError, _ensure_clone, _git, _run, clone_dir
from .registry import Source
from .run import _is_trip_failure

DEFAULT_MAX = 5
QUARANTINE_FAILS = 3          # 同じ slug がこの回数、直近 QUARANTINE_DAYS 日の夜に直せなかったら、人に回す
QUARANTINE_DAYS = 7
ATTEMPTS_DIRNAME = "repair-attempts"

NOTES = {
    "unknown_slug": "台帳に無い slug",
    "disabled": "台帳で enabled: false",
    "link_only": "台帳で mode: link_only（レシピで読まない掲載元）",
    "not_recipe": "台帳の mode がレシピ方式でない",
    "breaker": "ホスト遮断中（サイト側の障害）",
    "site_side": "接続系の失敗か HTTP 5xx（サイト側。レシピでは直せない）",
    "maintenance_page": "保守ページ（サイト側）",
    "branch_open": "作業用クローンに未マージの repair/<slug> ブランチがある（先にそれを人が見る）",
    "once_a_day": "今日はもう試した（1 日 1 回まで）",
    "quarantined": f"直近 {QUARANTINE_DAYS} 日の夜に {QUARANTINE_FAILS} 回直せなかった（人に回す）",
    "over_limit": "1 晩の上限を超えた（次の晩へ）",
}


def max_per_night() -> int:
    try:
        return max(int(os.environ.get("ONECO_REPAIR_MAX", DEFAULT_MAX)), 0)
    except ValueError:
        return DEFAULT_MAX


def _attempt_files(attempts_root: Path | None, slug: str) -> list[tuple[str, Path]]:
    if attempts_root is None or not attempts_root.is_dir():
        return []
    return [(d.name, d / f"{slug}.json") for d in sorted(attempts_root.iterdir()) if (d / f"{slug}.json").is_file()]


def _outcome(path: Path) -> str | None:
    try:
        v = json.loads(path.read_text(encoding="utf-8")).get("outcome")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) else None


def _recent_failures(attempts_root: Path | None, slug: str, date: str) -> int:
    try:
        today = date_cls.fromisoformat(date)
    except ValueError:
        return 0
    n = 0
    for name, path in _attempt_files(attempts_root, slug):
        try:
            d = date_cls.fromisoformat(name)
        except ValueError:
            continue
        if today - timedelta(days=QUARANTINE_DAYS) <= d < today and _outcome(path) == "failed":
            n += 1
    return n


def unmerged_repair_branches() -> tuple[set[str], str | None]:
    """作業用クローンの origin/repair/* のうち main に入っていないものの slug。(slug の集合, 取れなかったときの理由)。
    取れなかったら空集合を返して理由を残す（push 先は repair-night の最後の push が force-with-lease で守る）。"""
    clone = clone_dir()
    try:
        _ensure_clone(clone)
        c = str(clone)
        _run(_git("-C", c, "fetch", "--prune", "origin"))
        out = _run(["git", "-C", c, "branch", "-r", "--no-merged", "origin/main", "--list", "origin/repair/*"])
    except (StepError, OSError) as e:
        return set(), str(e)
    return {line.strip().removeprefix("origin/repair/") for line in out.splitlines() if line.strip()}, None


def select(
    report: list[dict[str, Any]],
    sources: list[Source],
    state: dict[str, Any],
    date: str,
    *,
    unmerged: set[str],
    attempts_root: Path | None,
    limit: int,
) -> dict[str, Any]:
    """report の failed のうち、エージェントに渡す slug と、外した理由。state の repair_hosts は今日の report で更新する（呼び出し側が保存する）。"""
    by_slug = {s.slug: s for s in sources}
    repair_gate.refresh_hosts(
        state,
        [{"slug": r["slug"], "host": host_of(by_slug[r["slug"]].url) if r["slug"] in by_slug else None, "status": r["status"]}
         for r in report],
        date,
    )
    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    def out(slug: str, reason: str, note: str | None = None) -> None:
        excluded.append({"slug": slug, "reason": reason, "note": note or NOTES.get(reason, reason)})

    for r in report:
        if r.get("status") != "failed":
            continue
        slug = r["slug"]
        s = by_slug.get(slug)
        info = r.get("error_info") or {}
        if s is None:
            out(slug, "unknown_slug")
        elif not s.enabled:
            out(slug, "disabled")
        elif s.mode == "link_only":
            out(slug, "link_only")
        elif s.mode != "recipe":
            out(slug, "not_recipe")
        elif info.get("breaker"):
            out(slug, "breaker")
        elif _is_trip_failure(info):
            out(slug, "site_side")
        elif info.get("kind") == "content":
            out(slug, "maintenance_page")
        else:
            kind, http = info.get("kind"), info.get("status")
            reason = repair_gate.skip_reason(state, slug, host_of(s.url), date, info, s.url, kind, http, None, "")
            if reason:
                out(slug, reason, repair_gate.skip_note(reason, http))
            elif slug in unmerged:
                out(slug, "branch_open")
            elif attempts_root is not None and (attempts_root / date / f"{slug}.json").exists():
                out(slug, "once_a_day")
            elif _recent_failures(attempts_root, slug, date) >= QUARANTINE_FAILS:
                out(slug, "quarantined")
            elif len(selected) >= limit:
                out(slug, "over_limit")
            else:
                selected.append({"slug": slug, "name": s.name, "url": s.url, "kind": s.kind, "species": s.species,
                                 "error": r.get("error"), "error_kind": kind, "http_status": http})
    return {"date": date, "limit": limit, "selected": selected, "excluded": excluded}


def write_plan(plan: dict[str, Any], data_dir: Path, date: str) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = data_dir / f"repair-plan-{date}.json"
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
