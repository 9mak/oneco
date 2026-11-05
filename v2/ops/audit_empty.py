"""0 頭の根拠が「子のいた日」にも成立してしまうレシピの監査（W006 T631）。

  python ops/audit_empty.py [--data v2/data] [--slug PREFIX] [--json] [--notify]

empty は ok と同じ扱いで、通知も AI 修復も止まる。子のいる日に 0 頭の根拠（empty_text など）が当たるレシピは、
行の読み方が崩れた日に通知なしで「本日は 0 頭」と出る。そこで data/last_ok/<slug>/ の保存ページ（収集が ok だった最後の日）に
今のレシピを当て、1 頭以上取れる（=子がいた日）のに 0 頭の根拠が成立する slug を挙げる。
照合の範囲と判定は build と同じ関数（collector.extract.empty_hits）を使う。別実装はしない。
empty_container と全行除外の根拠は、行が取れている日には成立しないので対象外。

--notify: 当たる slug の集合が前回（data/audit_empty_state.json）と変わった日だけ Discord に 1 通。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from collector.extract import build, empty_hits
from collector.last_ok import load_replay
from collector.notify import send_discord
from collector.recipe import Executor, Recipe
from collector.registry import Source, load_sources

STATE_NAME = "audit_empty_state.json"
JST = timezone(timedelta(hours=9))


@dataclass
class Finding:
    slug: str
    kind: str  # empty_selector / empty_absent / empty_text / empty_text_all
    detail: str  # 当たった文言かセレクタ
    url: str  # 当たった文書の URL（複数あれば最初。全部は docs 件数で示す）
    count: int  # 出現回数
    docs: int = 1  # 当たった文書の数


@dataclass
class AuditResult:
    findings: list[Finding]
    scanned: int = 0  # 保存ページがあり、今のレシピを当てられた slug
    child_days: int = 0  # うち 1 頭以上取れた（=子がいた日）slug
    skipped: dict[str, str] | None = None  # slug → 当てられなかった理由


def audit(data_dir: Path, items: list[tuple[Source, Recipe]]) -> AuditResult:
    last_ok = data_dir / "last_ok"
    out = AuditResult([], skipped={})
    for source, recipe in items:
        replay = load_replay(last_ok, source.slug)
        if replay is None:
            out.skipped[source.slug] = "保存ページなし"  # type: ignore[index]
            continue
        try:
            ex = Executor(replay, recipe)
            docs = ex.resolve(source.url)
            visited = getattr(ex, "visited", None)
            res = build(source, recipe, docs, visited)
        except Exception as e:  # 保存ページに今のレシピが当たらない（辿る URL が保存に無い等）。他の slug の監査は続ける
            out.skipped[source.slug] = f"{type(e).__name__}: {e}"[:120]  # type: ignore[index]
            continue
        out.scanned += 1
        if not res.animals:
            continue  # 子がいた日ではない
        out.child_days += 1
        pool = list(docs) + [d for d in (visited or []) if d not in docs]
        for h in empty_hits(recipe, pool):
            out.findings.append(
                Finding(
                    source.slug, h.kind, h.detail, h.urls[0] if h.urls else "", h.count, len(h.urls)
                )
            )
    return out


def run_audit(data_dir: Path, items: list[tuple[Source, Recipe]]) -> list[Finding]:
    return audit(data_dir, items).findings


def load_items(slug_prefix: str | None = None) -> list[tuple[Source, Recipe]]:
    items = []
    for s in load_sources():
        if s.mode != "recipe" or not s.enabled or not s.recipe_path.exists():
            continue
        if slug_prefix and not s.slug.startswith(slug_prefix):
            continue
        items.append((s, Recipe.load(s.recipe_path)))
    return items


# --- 通知 --------------------------------------------------------------------
def _load_prev(state_path: Path) -> set[str]:
    try:
        return set(json.loads(state_path.read_text(encoding="utf-8")).get("slugs") or [])
    except (OSError, ValueError, AttributeError):
        return set()


def notify_if_changed(
    findings: list[Finding], state_path: Path, send: Callable[[str], None]
) -> bool:
    """当たる slug の集合が前回と変わったときだけ send を呼ぶ。送れなかった（send が例外）日は state を書かない。"""
    now = {f.slug for f in findings}
    prev = _load_prev(state_path)
    if now != prev:
        added, removed = sorted(now - prev), sorted(prev - now)
        lines = [
            f"oneco 0 頭の根拠の監査: 子のいた日の保存ページにも 0 頭の根拠が当たる slug が {len(now)} 件"
            f"（前回 {len(prev)} 件・増 {len(added)}・減 {len(removed)}）。行の読み方が崩れても通知なしで「本日は 0 頭」になる"
        ]
        if added:
            lines.append("増えた: " + "・".join(added))
        if removed:
            lines.append("解消: " + "・".join(removed))
        seen: set[str] = set()
        for f in findings:  # 現在当たっている slug を 1 行ずつ（最初の根拠だけ）
            if f.slug not in seen:
                seen.add(f.slug)
                lines.append(f"- {f.slug}: {f.kind}「{f.detail[:40]}」×{f.count}")
        send("\n".join(lines)[:1900])
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {"date": datetime.now(JST).strftime("%Y-%m-%d"), "slugs": sorted(now)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return now != prev


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--data", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    ap.add_argument("--slug", help="この接頭辞の slug だけ")
    ap.add_argument("--json", action="store_true", help="結果を JSON で出す")
    ap.add_argument(
        "--notify",
        action="store_true",
        help="当たる slug の集合が前回と変わったときだけ Discord に送る",
    )
    a = ap.parse_args(argv)
    res = audit(a.data, load_items(a.slug))
    slugs = sorted({f.slug for f in res.findings})
    if a.json:
        print(
            json.dumps(
                {
                    "scanned": res.scanned,
                    "child_days": res.child_days,
                    "slugs": slugs,
                    "findings": [f.__dict__ for f in res.findings],
                    "skipped": res.skipped,
                },
                ensure_ascii=False,
                indent=1,
            )
        )
    else:
        for f in res.findings:
            print(f"{f.slug}\t{f.kind}\t{f.detail}\t×{f.count}\t文書 {f.docs}\t{f.url}")
        print(
            f"-- 保存ページに当てられた {res.scanned} slug・うち子がいた日 {res.child_days}・"
            f"根拠が当たる {len(slugs)} slug（当てられず飛ばした {len(res.skipped or {})}）",
            file=sys.stderr,
        )
    if a.notify:
        try:
            sent = notify_if_changed(res.findings, a.data / STATE_NAME, send_discord)
        except (RuntimeError, httpx.HTTPError, OSError) as e:
            print(f"通知できなかった（state は更新しない）: {e}", file=sys.stderr)
            return 1
        print("通知した" if sent else "前回と同じ。送らない", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
