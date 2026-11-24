"""CLI: show / fetch / run / discover（--pages あり） / notify / promote / repair / propose / repair-plan / repair-agent / repair-check / repair-night"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .fetch import Fetcher, FetchError
from .registry import load_sources, select

JST = timezone(timedelta(hours=9))


def cmd_show(args: argparse.Namespace) -> int:
    from .extract import build
    from .recipe import Executor, Recipe, RecipeError

    sources = select(load_sources(), args.slug)
    if not sources:
        print(f"台帳に無い slug: {args.slug}")
        return 2
    fetcher = Fetcher(respect_robots=not args.no_robots)
    rc = 0
    for s in sources:
        print(f"== {s.slug}  {s.name}  kind={s.kind} species={s.species} mode={s.mode}")
        print(f"   url: {s.url}")
        if s.mode != "recipe":
            continue
        if not s.recipe_path.exists():
            print(f"   レシピが無い: {s.recipe_path}")
            rc = 1
            continue
        try:
            recipe = Recipe.load(s.recipe_path)
            ex = Executor(fetcher, recipe)
            docs = ex.resolve(s.url)
        except (FetchError, RecipeError) as e:
            print(f"   失敗: {e}")
            rc = 1
            continue
        for t in ex.trace:
            print(f"   {t}")
        if args.html:
            for i, d in enumerate(docs):
                p = Path(os.environ.get("TMPDIR", "/tmp")) / f"{s.slug}-{i}.html"
                p.write_text(d.html or d.pdf_text or "", encoding="utf-8")
                print(f"   保存: {p}")
        res = build(s, recipe, docs, getattr(ex, "visited", None))
        print(f"   文書 {res.docs}・行 {res.rows}・動物 {len(res.animals)}・捨てた {len(res.dropped)}"
              + ("・empty_text あり" if res.empty_confirmed else ""))
        for a in res.animals[: args.limit]:
            shown = {k: v for k, v in a.items() if v and k not in ("municipality", "prefecture", "phone", "address", "contact_scope", "kind")}
            print("   ", json.dumps(shown, ensure_ascii=False))
        if len(res.animals) > args.limit:
            print(f"    … 他 {len(res.animals) - args.limit} 頭")
        for d in res.dropped[: args.limit]:
            print(f"   捨てた[{d.reason}]: {d.text}")
        if len(res.dropped) > args.limit:
            print(f"    … 他 {len(res.dropped) - args.limit} 行")
        if not res.animals and not res.empty_confirmed:
            rc = 1
    return rc


def cmd_fetch(args: argparse.Namespace) -> int:
    from bs4 import BeautifulSoup

    fetcher = Fetcher(respect_robots=not args.no_robots)
    try:
        page = fetcher.render(args.url) if args.render else fetcher.get(args.url, encoding=args.encoding)
    except FetchError as e:
        print(f"失敗: {e}")
        return 1
    print(f"# {page.final_url}  HTTP {page.status}  {page.content_type}  {len(page.content)} bytes")
    if page.html is None:
        print("(PDF などテキストでない)")
        return 0
    soup = BeautifulSoup(page.html, "lxml")
    if args.text:
        print(soup.get_text("\n", strip=True)[: args.limit])
    elif args.selectors:
        for name in ("table", "ul", "ol", "dl", "article", "section", "iframe"):
            els = soup.find_all(name)
            for el in els[:15]:
                ident = f"{name}" + (f"#{el.get('id')}" if el.get("id") else "") + (("." + ".".join(el.get("class"))) if el.get("class") else "")
                extra = f" src={el.get('src')}" if name == "iframe" else f" 子要素 {len(el.find_all(recursive=False))}・文字 {len(el.get_text(strip=True))}"
                print(f"{ident}{extra}")
        print("-- img (先頭 20)")
        for img in soup.find_all("img")[:20]:
            print(f"  {img.get('src')}  alt={img.get('alt')}")
        print("-- a (.pdf / 詳細っぽいもの 先頭 20)")
        n = 0
        for a in soup.find_all("a", href=True):
            t = a.get_text(" ", strip=True)
            if a["href"].lower().endswith(".pdf") or any(w in t for w in ("詳細", "詳しく", "PDF", "一覧", "情報", "収容", "譲渡", "保護")):
                print(f"  {a['href']}  | {t[:40]}")
                n += 1
                if n >= 20:
                    break
    else:
        print(page.html[: args.limit])
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .run import run
    from .state import AlreadyRunningError

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    date = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    sources = select(load_sources(), args.only)
    try:
        out = run(sources, date, fetcher=Fetcher(respect_robots=not args.no_robots),
                  enabled=False if args.no_ai_repair else None)
    except AlreadyRunningError as e:
        print(f"{e}（state/collect.lock）。何もせず終わる")
        return 3
    st = {}
    for s in out["sources"]:
        st[s["status"]] = st.get(s["status"], 0) + 1
    print(f"date={date} animals={len(out['animals'])} {st} seconds={out['generated_seconds']}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    if args.pages:
        from .discover_pages import discover_pages

        return discover_pages(depth=args.depth, notify=args.notify, out=Path(args.out) if args.out else None)
    from .discover import discover

    return discover(json_out=args.json, notify=args.notify)


def cmd_notify(args: argparse.Namespace) -> int:
    from .notify import notify

    return notify(dry_run=args.dry_run, date=args.date)


def cmd_promote(args: argparse.Namespace) -> int:
    """据え置かれた日の animals-<date>.json を latest.json に戻す（T623）。0=戻した 2=できない"""
    from .publish import promote
    from .run import DATA_DIR

    return promote(args.date, DATA_DIR)


def cmd_repair(args: argparse.Namespace) -> int:
    """読めなくなった slug のレシピ案を agy に書かせる。0=保存した 1=失敗 2=agy 無し/slug 無し"""
    from .ai_repair import repair
    from .run import collect_one

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sources = [s for s in load_sources() if s.slug == args.slug]
    if not sources:
        print(f"台帳に無い slug: {args.slug}")
        return 2
    s = sources[0]
    fetcher = Fetcher(respect_robots=not args.no_robots)
    error = None
    if not args.force:
        status, res, error, _ = collect_one(s, fetcher)
        if status in ("ok", "empty"):
            print(f"{s.slug}: 今は読めている（{status}・{len(res.animals) if res else 0} 頭）。--force で強制的に書き直す")
            return 0
        print(f"{s.slug}: {status} {error or ''}")
    from .state import load_state

    r = repair(s, fetcher=fetcher, error=error, save=not args.dry_run,
               last_ok_count=load_state()["sources"].get(s.slug, {}).get("last_ok_count"))
    if r.recipe_text and (args.show or r.status != "ok"):
        print("---- agy が返したレシピ ----")
        print(r.recipe_text.rstrip())
        print("-------------------------------")
    if r.status == "ok":
        print(f"{s.slug}: 新レシピで {r.count} 頭。" + (f"案を保存した: {r.proposal_path}（recipes/ は変えていない）。`python -m collector propose` で PR にする" if r.saved else "（--dry-run なので保存しない）"))
        return 0
    if r.status == "no_key":
        print(r.error)
        return 2
    print(f"{s.slug}: 修復できなかった。{r.error}（レシピは元のまま）")
    return 1


def cmd_propose(args: argparse.Namespace) -> int:
    """data/proposals の案を draft PR にする。merge はオーナー。"""
    from .propose import propose

    return propose(dry_run=args.dry_run)


def _today() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def cmd_repair_plan(args: argparse.Namespace) -> int:
    """その日の report から、修復エージェントに渡す slug を選んで data/repair-plan-<日付>.json に書く（W006 T645）。"""
    from .repair_plan import (
        ATTEMPTS_DIRNAME,
        max_per_night,
        select,
        unmerged_repair_branches,
        write_plan,
    )
    from .run import DATA_DIR
    from .state import load_state, save_state

    date = args.date or _today()
    report_path = DATA_DIR / f"report-{date}.json"
    if not report_path.exists():
        print(f"{report_path.name} が無い")
        return 2
    unmerged, err = unmerged_repair_branches()
    state = load_state()
    plan = select(json.loads(report_path.read_text(encoding="utf-8")), load_sources(), state, date, unmerged=unmerged,
                  attempts_root=DATA_DIR / ATTEMPTS_DIRNAME, limit=max_per_night())
    plan["unmerged_check_error"] = err
    if not args.dry_run:
        save_state(state)
        print(f"書いた: {write_plan(plan, DATA_DIR, date)}")
    print(f"対象 {len(plan['selected'])} 件: " + " ".join(s["slug"] for s in plan["selected"]))
    for e in plan["excluded"]:
        print(f"  外した {e['slug']}: {e['reason']}")
    return 0


def cmd_repair_agent(args: argparse.Namespace) -> int:
    """1 slug を、作業 worktree でエージェントに直させ → 検査 → 通れば push・draft PR（--dry-run なら push しない）。0=通った 1=通らなかった"""
    from .repair_agent import NIGHT_BUDGET_S
    from .repair_flow import Budget, process_slug
    from .run import DATA_DIR

    date = args.date or _today()
    sel = {"slug": args.slug, "name": args.slug, "url": None, "error": None, "error_kind": None, "http_status": None}
    report_path = DATA_DIR / f"report-{date}.json"
    if report_path.exists():
        for row in json.loads(report_path.read_text(encoding="utf-8")):
            if row.get("slug") == args.slug:
                sel.update(name=row.get("name") or args.slug, error=row.get("error"),
                           error_kind=(row.get("error_info") or {}).get("kind"))
    r = process_slug(sel, date, DATA_DIR, Budget(NIGHT_BUDGET_S), runners=[args.runner] if args.runner else None, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in r.items() if k != "details"} | {"details": r.get("details")}, ensure_ascii=False, indent=1, default=str))
    return 0 if r["outcome"] in ("pr_created", "dry_run_ok") else 1


def cmd_repair_check(args: argparse.Namespace) -> int:
    """作業 worktree の修復を固定の基準で検査する。0=通った 1=通らなかった"""
    from .propose import clone_dir
    from .repair_agent import worktree_path
    from .repair_check import check

    wt = Path(args.worktree) if args.worktree else worktree_path(args.slug, clone_dir())
    res = check(args.slug, wt, run_full=not args.fast)
    print(json.dumps(res.details, ensure_ascii=False, indent=1, default=str))
    for p in res.problems:
        print(f"NG: {p}")
    print("OK" if res.ok else "NG")
    return 0 if res.ok else 1


def cmd_repair_night(args: argparse.Namespace) -> int:
    """夜間の修復（選別 → エージェント → 検査 → draft PR → AI レビュー → Discord）。収集・公開を止めないので、常に 0（W006 T645）"""
    from .repair_flow import night

    return night(args.date or _today())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="collector")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("show", help="1 ページ（slug 前方一致）を読んで結果を表示")
    a.add_argument("slug")
    a.add_argument("--html", action="store_true", help="最終 HTML を保存")
    a.add_argument("--limit", type=int, default=10)
    a.add_argument("--no-robots", action="store_true")
    a.set_defaults(fn=cmd_show)
    a = sub.add_parser("fetch", help="URL を取って表示")
    a.add_argument("url")
    a.add_argument("--text", action="store_true")
    a.add_argument("--selectors", action="store_true")
    a.add_argument("--render", action="store_true")
    a.add_argument("--encoding")
    a.add_argument("--limit", type=int, default=6000)
    a.add_argument("--no-robots", action="store_true")
    a.set_defaults(fn=cmd_fetch)
    a = sub.add_parser("run", help="全ページ収集")
    a.add_argument("--date")
    a.add_argument("--only")
    a.add_argument("--no-robots", action="store_true")
    a.add_argument("--no-ai-repair", action="store_true", help="読めないページの AI 修復をしない（既定は環境変数 ONECO_AI_REPAIR=1 のとき有効）")
    a.set_defaults(fn=cmd_run)
    a = sub.add_parser("discover", help="環境省リンク集と台帳の差分（確認済みは registry/discover_known.yaml）")
    a.add_argument("--json", action="store_true")
    a.add_argument("--notify", action="store_true", help="確認済み一覧に無い差分があれば Discord へ 1 通（DISCORD_WEBHOOK_URL が無ければ表示だけ）")
    a.add_argument("--pages", action="store_true",
                   help="台帳のページ・親ディレクトリ・環境省リンク集のリンク先から 1〜2 段たどり、同じ自治体の別ページの掲載漏れと台帳のリンク切れを探す（月 1 回。T641）")
    a.add_argument("--depth", type=int, choices=(1, 2), default=1, help="--pages: 何段たどるか（2 は候補ページからもう 1 段）")
    a.add_argument("--out", help="--pages: 全件の JSON の出力先（既定は ONECO_LOG_DIR か v2/logs の discover-pages-<日付>.json）")
    a.set_defaults(fn=cmd_discover)
    a = sub.add_parser("notify", help="今日（JST）の report の異常を Discord へ。今日の report が無ければ送らず 1 で終わる")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--date", help="YYYY-MM-DD（既定は JST の今日。run に --date を渡した日の通知をやり直すとき）")
    a.set_defaults(fn=cmd_notify)
    a = sub.add_parser("promote", help="animals-<date>.json を latest.json に戻す（回線断などで据え置かれた日を確認のうえ公開）")
    a.add_argument("--date", required=True, help="YYYY-MM-DD")
    a.set_defaults(fn=cmd_promote)
    a = sub.add_parser("repair", help="読めなくなった slug のレシピ案を agy に書かせて data/proposals/ に保存する（PATH に agy が必要）")
    a.add_argument("slug", help="台帳の slug（完全一致）")
    a.add_argument("--dry-run", action="store_true", help="レシピを作って試すだけで保存しない")
    a.add_argument("--force", action="store_true", help="今読めていても書き直す")
    a.add_argument("--show", action="store_true", help="成功時も返ったレシピを表示")
    a.add_argument("--no-robots", action="store_true")
    a.set_defaults(fn=cmd_repair)
    a = sub.add_parser("propose", help="data/proposals の案を draft PR にする（作業用 clone から。merge はオーナー）")
    a.add_argument("--dry-run", action="store_true", help="PR にする予定の案を表示するだけ")
    a.set_defaults(fn=cmd_propose)
    a = sub.add_parser("repair-plan", help="その日の report から修復エージェントに渡す slug を選ぶ（data/repair-plan-<日付>.json）")
    a.add_argument("--date", help="YYYY-MM-DD（既定は JST の今日）")
    a.add_argument("--dry-run", action="store_true", help="state とファイルを書かず、選別だけ表示")
    a.set_defaults(fn=cmd_repair_plan)
    a = sub.add_parser("repair-agent", help="1 slug をエージェントに直させ、検査して、通れば draft PR（作業用 clone の worktree）")
    a.add_argument("slug")
    a.add_argument("--runner", choices=("agy", "claude"), help="この runner だけを使う（既定は agy、ONECO_REPAIR_CLAUDE=1 なら失敗時に claude）")
    a.add_argument("--dry-run", action="store_true", help="エージェントと検査までやり、push・PR はしない")
    a.add_argument("--date", help="YYYY-MM-DD（既定は JST の今日。失敗理由を読む report の日付）")
    a.set_defaults(fn=cmd_repair_agent)
    a = sub.add_parser("repair-check", help="作業 worktree の修復を固定の基準で検査する")
    a.add_argument("slug")
    a.add_argument("--worktree", help="既定は <作業用 clone>/../.repair-wt/<slug>")
    a.add_argument("--fast", action="store_true", help="v2 全体の pytest を飛ばす（手元の確認用。PR にする前の検査では使わない）")
    a.set_defaults(fn=cmd_repair_check)
    a = sub.add_parser("repair-night", help="夜間の修復（collect.sh から。ONECO_REPAIR_AGENT=1）")
    a.add_argument("--date", help="YYYY-MM-DD（既定は JST の今日）")
    a.set_defaults(fn=cmd_repair_night)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
