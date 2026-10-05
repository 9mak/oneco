"""全ページ収集 → 日次 JSON と report。"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .extract import Result, build
from .fetch import FetchError, Fetcher
from .recipe import Recipe, RecipeError, Executor
from .registry import ROOT, Source

log = logging.getLogger("collector")
DATA_DIR = ROOT / "data"
# 読めないページがこの割合を超えた日は回線断などとみなし、latest.json を書き換えない（サイトは前日のまま出続ける）。
# 平常日の failed は多くて 1 割未満（2026-09〜10 の実績で最大 14/229）。2026-10-04 の回線断では 119/229
MAX_FAILED_RATIO = 0.2


def outage(report: list[dict[str, Any]]) -> bool:
    """読めないページが多すぎる日か（link_only・disabled は分母に入れない）。"""
    tried = [r for r in report if r["status"] in ("ok", "empty", "failed")]
    failed = sum(1 for r in tried if r["status"] == "failed")
    return bool(tried) and failed > MAX_FAILED_RATIO * len(tried)


def collect_one(source: Source, fetcher: Fetcher) -> tuple[str, Result | None, str | None, list[str]]:
    """(status, result, error, trace)。status: ok | empty | failed | link_only | disabled"""
    if not source.enabled:
        return "disabled", None, None, []
    if source.mode == "link_only":
        return "link_only", None, None, []
    if not source.recipe_path.exists():
        return "failed", None, f"レシピが無い: {source.recipe_path.name}", []
    try:
        recipe = Recipe.load(source.recipe_path)
        ex = Executor(fetcher, recipe)
        docs = ex.resolve(source.url)
        res = build(source, recipe, docs, getattr(ex, "visited", None))
    except (FetchError, RecipeError) as e:
        return "failed", None, str(e), []
    except Exception as e:  # noqa: BLE001 — 1 ページの失敗で全体を止めない
        log.exception("%s", source.slug)
        return "failed", None, f"{type(e).__name__}: {e}", []
    if res.animals:
        return "ok", res, None, ex.trace
    if res.empty_confirmed:
        return "empty", res, None, ex.trace
    return "failed", res, f"0 頭で empty_text も無い（行 {res.rows}・捨てた {len(res.dropped)}）", ex.trace


def ai_repair_enabled() -> bool:
    """環境変数 ONECO_AI_REPAIR=1 のときだけ、読めなかったページのレシピを Claude に書き直させる。"""
    return os.environ.get("ONECO_AI_REPAIR", "") == "1"


def run(sources: list[Source], date: str, out_dir: Path = DATA_DIR, fetcher: Fetcher | None = None,
        enabled: bool | None = None) -> dict[str, Any]:
    """全ページ収集。enabled は AI 修復の有無（None なら環境変数 ONECO_AI_REPAIR=1 で判定）。"""
    if enabled is None:
        enabled = ai_repair_enabled()
    fetcher = fetcher or Fetcher()
    animals: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    t0 = time.monotonic()
    for s in sources:
        t = time.monotonic()
        status, res, err, trace = collect_one(s, fetcher)
        repair_note: str | None = None
        if status == "failed" and enabled and s.enabled and s.mode == "recipe":
            from .ai_repair import repair

            r = repair(s, fetcher=fetcher, error=err)
            if r.status == "ok":
                repair_note = f"AI がレシピを書き直した（{r.count} 頭）"
                status, res, err, trace = collect_one(s, fetcher)
            elif r.status == "no_key":
                repair_note = "AI 修復: ANTHROPIC_API_KEY 未設定"
                enabled = False   # 以降のページでも同じなので試さない
            else:
                repair_note = f"AI 修復に失敗: {r.error}"
            log.info("%-28s %s", s.slug, repair_note)
        n = len(res.animals) if res else 0
        report.append({"slug": s.slug, "name": s.name, "status": status, "count": n, "error": err,
                       "dropped": len(res.dropped) if res else 0, "seconds": round(time.monotonic() - t, 1),
                       "repair": repair_note,
                       # skip_errors で捨てた子（「URL: 理由」）。通知には出さないが、黙って頭数が減ったのを後から追える
                       "skipped": [t.removeprefix("skip ") for t in trace if t.startswith("skip ")]})
        log.info("%-28s %-9s %4d %s", s.slug, status, n, err or "")
        if res:
            animals.extend(res.animals)
    held = outage(report)
    out = {"date": date, "generated_seconds": round(time.monotonic() - t0), "animals": animals, "held": held,
           "sources": [{**{k: v for k, v in asdict(s).items() if k != "legacy"}, **next(r for r in report if r["slug"] == s.slug)} for s in sources]}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"animals-{date}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if held:
        log.warning("読めないページが %d%% を超えたので latest.json を書き換えない（サイトは前日のまま）", int(MAX_FAILED_RATIO * 100))
    else:
        (out_dir / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / f"report-{date}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
