"""直す対象の無い日は AI 修復を呼ばない（W006 T635）。

AI 修復の試行 198 回（2026-10-16〜11-05 の実績）のうち、半分以上はレシピを直しても取れない日だった
（サイト停止・移転・掲載期限切れで個別ページだけ消える・同じ失敗の繰り返し）。呼ぶ回数を減らすだけで、公開データと
採用条件は変えない。状態は state/sources.json に持つ（T607）:

  repair_hosts[host] = {since, slugs}      ホスト障害の疑い。slugs のどれかが読めるようになるか、7 日たつまで、そのホストでは呼ばない
  sources[slug].repair = {date, tries, kind, status, body_sha, ctx, quarantined}
                                           最後に呼んだ日・同じ失敗の指紋で試した回数・隔離中か

呼ばない理由（decide / skip_reason の戻り値）:
  host_suspect    同じホストで同じ日に 2 slug 以上が新たに読めなくなった（サイト側の障害・改修）
  once_a_day      同じ slug は 1 日 1 回まで
  quarantined     同じ失敗の指紋で 3 回試して直らない。入口ページ・コード・RECIPE.md が変わるまで呼ばない
  entry_gone      入口 URL そのものが 404・410（レシピでは直せない）
  children_gone   follow_all / pdf_links で辿った子が全部 404（掲載期限切れで市が個別ページだけ消す日）
"""

from __future__ import annotations

import hashlib
from datetime import date as date_cls
from pathlib import Path
from typing import Any

from .registry import ROOT
from .state import FAILING, GOOD

RECIPE_DOC = ROOT / "docs" / "RECIPE.md"

# 同じホストで同じ日に新たに読めなくなった slug がこの数以上ならホスト障害の疑い。
# 2026-10-04〜11-01 の report で 12 ホスト日に当たり、12 件ともサイト側（503・401・接続・timeout・502・臨時ページ・公開停止・移転）。
# 本物の直す対象（長野市・いわき・群馬・前橋・熊本市・船橋・青森市・滋賀 sapca・広島県）が同じホスト日に重なった例は 0 件。
HOST_MIN_NEW_FAILURES = 2
# 疑いはこの日数で外す。slug の集合には限らない: 障害は日をまたいで同じホストの別 slug へ広がる（2026-10-22 は熊本・福岡・おおいたの
# 503/502 が朝まで続いた）ので、後から崩れた slug も障害の続きとして待つほうが正しい。ただし疑いは「どれかが読めるようになる」まで
# 外れないので、読めないまま残った slug のせいで同じホストの本物の崩れが永久に人へ回らないのを防ぐ。1 週間たっても直らない障害は
# 改修（作り直し）とみなし、AI にも直させる。外れたあと同じ日に 2 件以上が新たに崩れれば、また疑いを立て直す。
HOST_SUSPECT_DAYS = 7
# 同じ失敗の指紋でこの回数試して直らなければ隔離する。1 回は偶然の失敗、2 回で同じ結果ならまだ入力の揺れもあり得る、
# 3 回目で初めて「AI にはこの入力から直せない」と言える。
QUARANTINE_TRIES = 3
# 指紋の「コード」: 入力（プロンプト）と検査（schema・採用）と実行（エンジン）を決める部品。変わったら隔離を解く
_CODE_FILES = (
    "ai_repair.py",
    "extract.py",
    "recipe.py",
    "recipe_schema.py",
    "fetch.py",
    "repair_schema.json",
)

SKIP_NOTES = {
    "host_suspect": "AI 修復はしない（ホスト障害の疑い。同じホストで複数の自治体が同じ日に読めなくなった。サイト側の障害・改修）",
    "once_a_day": "AI 修復はしない（今日はもう試した。1 日 1 回まで）",
    "quarantined": "AI 修復はしない（同じ失敗で 3 回試して直らず隔離中。入口ページかコードが変わるまで呼ばない）",
    "entry_gone": "AI 修復はしない（入口ページが 404 で、レシピでは直せない）",
    "children_gone": "AI 修復はしない（辿った子ページがすべて 404。掲載期限切れなどで市が個別ページだけ消した日）",
}
QUARANTINE_NOTE = (
    "AI 修復を隔離した（同じ失敗で 3 回試して直らない。入口ページかコードが変わるまで呼ばない）"
)


def context_hash() -> str:
    """コード（上の _CODE_FILES）と docs/RECIPE.md の内容のハッシュ。"""
    h = hashlib.sha256()
    here = Path(__file__).parent
    for name in _CODE_FILES:
        h.update(name.encode())
        try:
            h.update((here / name).read_bytes())
        except OSError:
            h.update(b"?")
    try:
        h.update(RECIPE_DOC.read_bytes())
    except OSError:
        h.update(b"?")
    return h.hexdigest()[:16]


def _prev_status(st: dict[str, Any], date: str) -> str | None:
    """この run より前の状態（同じ日の再実行なら、その日より前）。"""
    return st.get("prev_status") if st.get("last_date") == date else st.get("last_status")


def _expired(since: str | None, date: str) -> bool:
    """疑いを立てた日から HOST_SUSPECT_DAYS 日たったか。日付が読めなければ期限切れ扱い（疑いを永久に残さない側に倒す）。"""
    try:
        return (date_cls.fromisoformat(date) - date_cls.fromisoformat(str(since))).days >= HOST_SUSPECT_DAYS
    except ValueError:
        return True


def refresh_hosts(state: dict[str, Any], rows: list[dict[str, Any]], date: str) -> None:
    """ホスト障害の疑いを更新する。rows は今日の {slug, host, status}。
    解除: 疑いの slug のどれかが読めるようになった、または疑いの slug がもう 1 つも読めない状態でない（台帳から外れた等）、
    または疑いを立てて HOST_SUSPECT_DAYS 日たった。
    新規: 今日新たに読めなくなった（前日は読めていた or 記録なし）slug が同じホストで HOST_MIN_NEW_FAILURES 以上。"""
    hosts: dict[str, Any] = state.setdefault("repair_hosts", {})
    status = {r["slug"]: r["status"] for r in rows}
    for host, h in list(hosts.items()):
        if (
            any(status.get(s) in GOOD for s in h["slugs"])
            or not any(status.get(s) in FAILING for s in h["slugs"])
            or _expired(h.get("since"), date)
        ):
            del hosts[host]
    sources = state.get("sources", {})
    new_by_host: dict[str, list[str]] = {}
    for r in rows:
        if (
            r["status"] in FAILING
            and r.get("host")
            and _prev_status(sources.get(r["slug"], {}), date) not in FAILING
        ):
            new_by_host.setdefault(r["host"], []).append(r["slug"])
    for host, slugs in new_by_host.items():
        if len(slugs) >= HOST_MIN_NEW_FAILURES:
            old = hosts.get(host, {})
            hosts[host] = {
                "since": old.get("since", date),
                "slugs": sorted(set(old.get("slugs", [])) | set(slugs)),
            }


def entry_gone(info: dict[str, Any] | None, entry_url: str) -> bool:
    """入口 URL 自身の 404・410。子ページの 404 は skip_errors で直せるので含めない。"""
    return (
        bool(info)
        and info.get("kind") == "http"
        and info.get("status") in (404, 410)
        and info.get("url") == entry_url
    )


def skip_reason(
    state: dict[str, Any],
    slug: str,
    host: str | None,
    date: str,
    info: dict[str, Any] | None,
    entry_url: str,
    kind: str | None,
    status: int | None,
    body_sha: str | None,
    ctx: str,
) -> str | None:
    """呼ばない理由。呼ぶなら None。body_sha が None（入口が取れない）なら指紋の判定はしない（repair は agy を呼ばずに終わる）。"""
    if info and info.get("children_gone"):
        return "children_gone"
    if entry_gone(info, entry_url):
        return "entry_gone"
    if host and host in state.get("repair_hosts", {}):
        return "host_suspect"
    r = state.get("sources", {}).get(slug, {}).get("repair")
    if not r or body_sha is None:
        return None
    if r.get("quarantined") and _same(r, kind, status, body_sha, ctx):
        return "quarantined"
    if r.get("date") == date:
        return "once_a_day"
    return None


def _same(
    r: dict[str, Any], kind: str | None, status: int | None, body_sha: str | None, ctx: str
) -> bool:
    return (r.get("kind"), r.get("status"), r.get("body_sha"), r.get("ctx")) == (
        kind,
        status,
        body_sha,
        ctx,
    )


def record_attempt(
    state: dict[str, Any],
    slug: str,
    date: str,
    kind: str | None,
    status: int | None,
    body_sha: str,
    ctx: str,
    counted: bool,
) -> bool:
    """呼んだ後に記録する。counted=False（agy が答えなかった）は日付だけ残し、試した回数に数えない。
    戻り値は「この呼び出しで新たに隔離した」か。"""
    st = state.setdefault("sources", {}).setdefault(slug, {})
    r = st.get("repair") or {}
    same = _same(r, kind, status, body_sha, ctx)
    tries = (r.get("tries", 0) if same else 0) + (1 if counted else 0)
    quarantined = tries >= QUARANTINE_TRIES
    st["repair"] = {
        "date": date,
        "tries": tries,
        "kind": kind,
        "status": status,
        "body_sha": body_sha,
        "ctx": ctx,
        "quarantined": quarantined,
    }
    return quarantined and not (same and r.get("quarantined"))
