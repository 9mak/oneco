"""CLI: show / fetch / run / discover / notify / repair"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ai_repair import DEFAULT_MODEL
from .fetch import FetchError, Fetcher
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
        res = build(s, recipe, docs)
        print(f"   文書 {res.docs}・行 {res.rows}・動物 {len(res.animals)}・捨てた {len(res.dropped)}"
              + ("・empty_text あり" if res.empty_confirmed else ""))
        for a in res.animals[: args.limit]:
            shown = {k: v for k, v in a.items() if v and k not in ("municipality", "prefecture", "phone", "address", "kind")}
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

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    date = args.date or datetime.now(JST).strftime("%Y-%m-%d")
    sources = select(load_sources(), args.only)
    out = run(sources, date, fetcher=Fetcher(respect_robots=not args.no_robots),
              enabled=False if args.no_ai_repair else None)
    st = {}
    for s in out["sources"]:
        st[s["status"]] = st.get(s["status"], 0) + 1
    print(f"date={date} animals={len(out['animals'])} {st} seconds={out['generated_seconds']}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    from .discover import discover

    return discover(json_out=args.json)


def cmd_notify(args: argparse.Namespace) -> int:
    from .notify import notify

    return notify(dry_run=args.dry_run)


def cmd_repair(args: argparse.Namespace) -> int:
    """読めなくなった slug のレシピを Claude に書き直させる。0=保存した 1=失敗 2=未設定/slug 無し"""
    from .ai_repair import repair
    from .run import collect_one

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 未設定")
        return 2
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
    r = repair(s, fetcher=fetcher, model=args.model, error=error, save=not args.dry_run)
    if r.recipe_text and (args.show or r.status != "ok"):
        print("---- Claude が返したレシピ ----")
        print(r.recipe_text.rstrip())
        print("-------------------------------")
    if r.status == "ok":
        print(f"{s.slug}: 新レシピで {r.count} 頭。" + (f"保存した: {s.recipe_path}" if r.saved else "（--dry-run なので保存しない）"))
        return 0
    if r.status == "no_key":
        print("ANTHROPIC_API_KEY 未設定")
        return 2
    print(f"{s.slug}: 修復できなかった。{r.error}（レシピは元のまま）")
    return 1


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
    a = sub.add_parser("discover", help="環境省リンク集と台帳の差分")
    a.add_argument("--json", action="store_true")
    a.set_defaults(fn=cmd_discover)
    a = sub.add_parser("notify", help="直近 report の異常を Discord へ")
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(fn=cmd_notify)
    a = sub.add_parser("repair", help="読めなくなった slug のレシピを Claude に書き直させる（ANTHROPIC_API_KEY 必須）")
    a.add_argument("slug", help="台帳の slug（完全一致）")
    a.add_argument("--model", help=f"既定は環境変数 ONECO_AI_MODEL か {DEFAULT_MODEL}")
    a.add_argument("--dry-run", action="store_true", help="レシピを作って試すだけで保存しない")
    a.add_argument("--force", action="store_true", help="今読めていても書き直す")
    a.add_argument("--show", action="store_true", help="成功時も返ったレシピを表示")
    a.add_argument("--no-robots", action="store_true")
    a.set_defaults(fn=cmd_repair)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
