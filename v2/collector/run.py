"""全ページ収集 → 日次 JSON と report。"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import TRANSPORT_KINDS, ErrorInfo, error_to_dict, host_of
from .extract import Result, build
from .fetch import Fetcher, FetchError
from .publish import build_manifest, publish
from .recipe import Executor, Recipe, RecipeError
from .registry import ROOT, Source
from .state import FAILING, JST, STATE_DIR, RunLock, load_state, save_state, update_sources

log = logging.getLogger("collector")
DATA_DIR = ROOT / "data"
LOG_DIR = Path(os.environ.get("ONECO_LOG_DIR") or ROOT / "logs")

# 回線断の判定（T603）: 接続系エラー（dns/connect/tls/timeout）の failed が、異なるホスト 3 つ以上かつ試行数の 10% 以上。
# 2026-10-04 の回線断は 119/229 ページ・多数のホスト。平常日の接続系 failed は 0〜2 件・1〜2 ホスト（サイト側の一時障害）。
# parser / content / http の失敗は何件あっても回線断にしない（レシピ破損やサイト改修は回線の問題ではない）。
OUTAGE_MIN_HOSTS = 3
OUTAGE_MIN_RATIO = 0.10
# 同一ホストで接続系エラーか 5xx が連続この件数に達したら、その run の残りの同ホストを取りに行かない（T603）。
# 落ちているサイトに 1 ホスト数十件のリクエストを送り続けて遅くなる・迷惑をかけるのを避ける。
BREAKER_TRIP = 3


def outage(report: list[dict[str, Any]]) -> bool:
    """回線断か（link_only・disabled は分母に入れない）。"""
    tried = [r for r in report if r["status"] in ("ok", "empty", "failed", "ambiguous_empty")]
    transport = [r for r in tried if r["status"] == "failed" and (r.get("error_info") or {}).get("kind") in TRANSPORT_KINDS]
    hosts = {(r["error_info"] or {}).get("host") for r in transport} - {None}
    return bool(tried) and len(hosts) >= OUTAGE_MIN_HOSTS and len(transport) >= OUTAGE_MIN_RATIO * len(tried)


@dataclass
class Collected:
    """collect_one の結果。status: ok | empty | failed | link_only | disabled。
    error は表示用の文字列、error_info は判定用（kind / status / host / phase）。"""

    status: str
    result: Result | None = None
    error: str | None = None
    trace: list[str] = field(default_factory=list)
    error_info: dict[str, Any] | None = None

    def __iter__(self):
        return iter((self.status, self.result, self.error, self.trace))


def _as_collected(c: Any) -> Collected:
    """テストが collect_one を (status, result, error, trace) のタプルで差し替えても扱えるようにする。"""
    if isinstance(c, Collected):
        return c
    status, res, err, trace = c
    return Collected(status, res, err, list(trace), ErrorInfo("other").to_dict() if status == "failed" else None)


def collect_one(source: Source, fetcher: Fetcher) -> Collected:
    if not source.enabled:
        return Collected("disabled")
    if source.mode == "link_only":
        return Collected("link_only")
    if not source.recipe_path.exists():
        return Collected("failed", error=f"レシピが無い: {source.recipe_path.name}", error_info=ErrorInfo("recipe", phase="parse").to_dict())
    try:
        recipe = Recipe.load(source.recipe_path)
        ex = Executor(fetcher, recipe)
        docs = ex.resolve(source.url)
        res = build(source, recipe, docs, getattr(ex, "visited", None))
    except (FetchError, RecipeError) as e:
        return Collected("failed", error=str(e), error_info=error_to_dict(e))
    except Exception as e:
        log.exception("%s", source.slug)
        return Collected("failed", error=f"{type(e).__name__}: {e}", error_info=ErrorInfo("other", phase="parse").to_dict())
    if res.animals:
        return Collected("ok", res, trace=ex.trace)
    if res.empty_confirmed:
        return Collected("empty", res, trace=ex.trace)
    host = host_of(source.url)
    msg = f"0 頭で empty_text も無い（行 {res.rows}・捨てた {len(res.dropped)}）"
    if getattr(res, "ambiguous_empty", False):   # 0 頭に見えるが肯定的な証拠が無い（extract 側が判定）
        reason = getattr(res, "ambiguous_reason", None)
        return Collected("ambiguous_empty", res, f"{msg}。{reason}" if reason else msg, ex.trace,
                         ErrorInfo("ambiguous_empty", phase="parse", host=host).to_dict())
    return Collected("failed", res, msg, ex.trace, ErrorInfo("parser", phase="parse", host=host).to_dict())


def ai_repair_enabled() -> bool:
    """環境変数 ONECO_AI_REPAIR=1 のときだけ、読めなかったページのレシピ案を agy に書かせる（案は data/proposals/ に置くだけ。本番は PR の merge で入る）。"""
    return os.environ.get("ONECO_AI_REPAIR", "") == "1"


def _is_trip_failure(info: dict[str, Any] | None) -> bool:
    """ホスト breaker の数え対象: 接続系エラーか 5xx。"""
    if not info:
        return False
    return info.get("kind") in TRANSPORT_KINDS or (info.get("kind") == "http" and (info.get("status") or 0) >= 500)


def _events(log_dir: Path, date: str, rows: list[dict[str, Any]]) -> None:
    """slug ごと 1 行の構造化ログ（T615）。落ちても収集は止めない。"""
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / f"events-{date}.jsonl").open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except OSError as e:
        log.warning("events ログを書けない: %s", e)


def run(sources: list[Source], date: str, out_dir: Path = DATA_DIR, fetcher: Fetcher | None = None,
        enabled: bool | None = None, state_dir: Path | None = None, log_dir: Path | None = None,
        now: datetime | None = None) -> dict[str, Any]:
    """全ページ収集。enabled は AI 修復の有無（None なら環境変数 ONECO_AI_REPAIR=1 で判定）。
    state_dir / log_dir の既定は本番の v2/state・v2/logs。out_dir を差し替えたときは out_dir の下に置く（テストが本番を汚さない）。
    別の収集が動いていれば AlreadyRunningError。"""
    default_out = out_dir == DATA_DIR
    state_dir = state_dir or (STATE_DIR if default_out else out_dir / "state")
    log_dir = log_dir or (LOG_DIR if default_out else out_dir / "logs")
    with RunLock(state_dir):
        return _run_locked(sources, date, out_dir, fetcher, enabled, state_dir, log_dir, now or datetime.now(JST))


def _run_locked(sources: list[Source], date: str, out_dir: Path, fetcher: Fetcher | None, enabled: bool | None,
                state_dir: Path, log_dir: Path, now: datetime) -> dict[str, Any]:
    if enabled is None:
        enabled = ai_repair_enabled()
    fetcher = fetcher or Fetcher()
    run_id = f"{date}T{now.strftime('%H%M%S')}"
    state = load_state(state_dir)
    breaker: dict[str, Any] = state["breaker"]
    probing = set(breaker)        # 前日までに開いていて、今日まだ試していないホスト
    streak: dict[str, int] = {}   # ホストごとの連続失敗（接続系・5xx）
    tripped: dict[str, dict[str, Any]] = {}   # 今日の残りを取りに行かないホスト → 直前の失敗の error_info
    animals: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    t0 = time.monotonic()
    for s in sources:
        t = time.monotonic()
        host = host_of(s.url)
        counted = bool(host) and s.enabled and s.mode == "recipe"
        skipped_by_breaker = counted and host in tripped
        repair_note: str | None = None
        if skipped_by_breaker:
            last = tripped[host]
            c = Collected("failed", error=f"ホスト遮断中（{host}・{streak.get(host, BREAKER_TRIP)} 件連続失敗）",
                          error_info={**last, "breaker": True})
        else:
            c = _as_collected(collect_one(s, fetcher))
        status, res, err, trace = c
        info = dict(c.error_info) if (c.error_info and status in FAILING) else None
        if info is not None and not info.get("host"):
            info["host"] = host
        if counted and not skipped_by_breaker:
            failed_trip = status == "failed" and _is_trip_failure(info)
            if host in probing:   # 翌日以降の probe: 接続系・5xx 以外なら「サイトは生きている」ので閉じる（reviewer M3）
                probing.discard(host)
                if not failed_trip:
                    breaker.pop(host, None)
                else:
                    streak[host] = BREAKER_TRIP
                    tripped[host] = info or {}
                    breaker[host] = {"opened": breaker[host].get("opened", date), "failures": BREAKER_TRIP}
            elif failed_trip:
                streak[host] = streak.get(host, 0) + 1
                if streak[host] >= BREAKER_TRIP:
                    tripped[host] = info or {}
                    breaker[host] = {"opened": breaker.get(host, {}).get("opened", date), "failures": streak[host]}
            else:
                streak[host] = 0
        # 接続系・遮断中・保守ページ（content）は読めない原因がサイト側なので、レシピの AI 修復はしない
        if status == "failed" and enabled and s.enabled and s.mode == "recipe" and not _is_trip_failure(info) \
                and not skipped_by_breaker and (info or {}).get("kind") != "content":
            from .ai_repair import repair

            r = repair(s, fetcher=fetcher, error=err)
            if r.status == "ok":
                repair_note = f"AI がレシピ案を書いた（{r.count} 頭・{getattr(r, 'proposal_path', None)}）"
            elif r.status == "no_key":
                repair_note = "AI 修復: 未設定"
                enabled = False   # 以降のページでも同じなので試さない
            else:
                repair_note = f"AI 修復に失敗: {r.error}"
            log.info("%-28s %s", s.slug, repair_note)
        n = len(res.animals) if (res and status != "ambiguous_empty") else 0
        secs = round(time.monotonic() - t, 1)
        row = {"slug": s.slug, "name": s.name, "status": status, "count": n, "error": err,
               "error_info": info, "run_id": run_id,
               "dropped": len(res.dropped) if res else 0, "seconds": secs,
               "repair": repair_note,
               # skip_errors で捨てた子（「URL: 理由」）。通知には出さないが、黙って頭数が減ったのを後から追える
               "skipped": [t.removeprefix("skip ") for t in trace if t.startswith("skip ")]}
        report.append(row)
        events.append({"run_id": run_id, "slug": s.slug, "host": (info or {}).get("host") or host, "status": status,
                       "kind": (info or {}).get("kind"), "http_status": (info or {}).get("status"), "seconds": secs,
                       "attempt": (info or {}).get("attempt"), "count": n, "dropped": row["dropped"],
                       "rows": res.rows if res else 0, "breaker": bool(skipped_by_breaker)})
        log.info("%-28s %-9s %4d %s", s.slug, status, n, err or "")
        if res and status != "ambiguous_empty":
            animals.extend(res.animals)
    held = outage(report)
    by_slug = {r["slug"]: r for r in report}
    out = {"run_id": run_id, "date": date, "generated_seconds": round(time.monotonic() - t0), "animals": animals,
           "held": held,
           "sources": [{**{k: v for k, v in asdict(s).items() if k != "legacy"}, **by_slug[s.slug]} for s in sources]}
    if held:
        log.warning("接続系の失敗が複数ホストに広がったので回線断とみなし、latest.json を書き換えない（サイトは前日のまま）")
    manifest = build_manifest(run_id, date, report, len(animals), held)
    files: dict[str, Any] = {f"animals-{date}.json": out, f"report-{date}.json": report, f"manifest-{date}.json": manifest}
    if not held:
        files["latest.json"] = out
        files["manifest-latest.json"] = manifest
    publish(out_dir, run_id, date, files)
    _events(log_dir, date, events)
    update_sources(state, report, date)
    save_state(state, state_dir)
    return out
