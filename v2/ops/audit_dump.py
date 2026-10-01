"""監査用ダンプ: 台帳の全ページについて「台帳・レシピ・辿った文書の本文と画像・取れた行・捨てた行」を 1 slug 1 JSON に書く。

  python ops/audit_dump.py --out data/audit-2026-09-30 [--only pref_saga]

Workflow の監査エージェントはネットワークに出ず、このダンプだけを読んで
「台帳の kind とページの実態が合っているか」「飼い主募集・迷子告知・返還済み・譲渡決定が混ざっていないか」
「頭数の取りこぼしが無いか」「写真が行と対応しているか」を判定する（T512 / T513）。

link_only のページも入口を 1 回だけ取って本文を残す（動物が載っているのにリンクだけになっていないかを見るため）。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collector.extract import build  # noqa: E402
from collector.fetch import FetchError, Fetcher  # noqa: E402
from collector.recipe import Doc, Executor, Recipe, RecipeError  # noqa: E402
from collector.registry import REGISTRY_PATH, load_sources, select  # noqa: E402


def load_notes() -> dict[str, str | None]:
    """台帳の note（Source dataclass には載らない）を slug → note で返す。"""
    import yaml

    raw = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {r["slug"]: r.get("note") for r in raw["sources"]}

TEXT_FULL = 9000      # 先頭 3 文書はここまで
TEXT_SHORT = 2000     # それ以降の文書（個体ページなど）はここまで
MAX_DOCS = 80
MAX_IMGS = 200
MAX_HEADINGS = 80


def doc_dump(d: Doc, i: int) -> dict[str, Any]:
    cap = TEXT_FULL if i < 3 else TEXT_SHORT
    text = d.text()
    out: dict[str, Any] = {
        "url": d.url,
        "is_pdf": d.is_pdf,
        "rendered": d.rendered,
        "text_len": len(text),
        "text": text[:cap],
    }
    if d.soup is not None:
        t = d.soup.find("title")
        out["title"] = t.get_text(" ", strip=True) if t else None
        out["headings"] = [h.get_text(" ", strip=True)[:120] for h in d.soup.find_all(["h1", "h2", "h3", "h4"])][:MAX_HEADINGS]
        imgs = []
        for img in d.soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if src:
                imgs.append({"src": src, "alt": (img.get("alt") or "")[:80]})
        out["img_count"] = len(imgs)
        out["imgs"] = imgs[:MAX_IMGS]
    if d.pdf_tables is not None:
        out["pdf_tables"] = len(d.pdf_tables)
        out["pdf_table_head"] = [t[:3] for t in d.pdf_tables[:5]]
    return out


def dump_one(s, fetcher: Fetcher, note: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "registry": {
            "slug": s.slug, "name": s.name, "municipality": s.municipality, "prefecture": s.prefecture,
            "url": s.url, "kind": s.kind, "species": s.species, "mode": s.mode, "enabled": s.enabled,
            "note": note,
        },
        "recipe_text": None, "status": None, "error": None, "trace": [], "docs": [], "docs_total": 0,
        "rows": 0, "animals": [], "dropped": [], "empty_confirmed": False,
    }
    if not s.enabled:
        entry["status"] = "disabled"
        return entry
    if s.mode == "link_only":
        entry["status"] = "link_only"
        try:
            page = fetcher.get(s.url)
            if page.html is not None:
                from collector.recipe import _make_doc
                entry["docs"] = [doc_dump(_make_doc(page.final_url, page.html), 0)]
                entry["docs_total"] = 1
        except FetchError as e:
            entry["error"] = str(e)
        return entry
    if not s.recipe_path.exists():
        entry["status"] = "failed"
        entry["error"] = f"レシピが無い: {s.recipe_path.name}"
        return entry
    entry["recipe_text"] = s.recipe_path.read_text(encoding="utf-8")
    try:
        recipe = Recipe.load(s.recipe_path)
        ex = Executor(fetcher, recipe)
        docs = ex.resolve(s.url)
        entry["trace"] = list(ex.trace)
        visited = list(getattr(ex, "visited", []) or [])
        res = build(s, recipe, docs, visited)
    except (FetchError, RecipeError) as e:
        entry["status"] = "failed"
        entry["error"] = str(e)
        return entry
    except Exception as e:  # noqa: BLE001
        entry["status"] = "failed"
        entry["error"] = f"{type(e).__name__}: {e}"
        entry["traceback"] = traceback.format_exc()[-2000:]
        return entry
    pool = list(visited) + [d for d in docs if d not in visited]
    entry["docs_total"] = len(pool)
    entry["docs"] = [doc_dump(d, i) for i, d in enumerate(pool[:MAX_DOCS])]
    entry["rows"] = res.rows
    entry["animals"] = res.animals
    entry["dropped"] = [{"reason": d.reason, "text": d.text} for d in res.dropped]
    entry["empty_confirmed"] = res.empty_confirmed
    if res.animals:
        entry["status"] = "ok"
    elif res.empty_confirmed:
        entry["status"] = "empty"
    else:
        entry["status"] = "failed"
        entry["error"] = f"0 頭で empty_text も無い（行 {res.rows}・捨てた {len(res.dropped)}）"
    return entry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only", help="slug の前方一致で絞る")
    ap.add_argument("--slugs", help="カンマ区切りの slug（完全一致）。既存の _index.json にはこの分だけ上書きで混ぜる")
    ap.add_argument("--no-robots", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    sources = select(load_sources(), a.only)
    if a.slugs:
        wanted = {s.strip() for s in a.slugs.split(",") if s.strip()}
        sources = [s for s in sources if s.slug in wanted]
    notes = load_notes()
    fetcher = Fetcher(respect_robots=not a.no_robots)
    index = []
    t0 = time.monotonic()
    for i, s in enumerate(sources, 1):
        t = time.monotonic()
        try:
            e = dump_one(s, fetcher, notes.get(s.slug))
        except Exception as ex:  # noqa: BLE001 — 1 ページで全体を止めない
            e = {"registry": {"slug": s.slug, "name": s.name, "prefecture": s.prefecture, "kind": s.kind,
                              "species": s.species, "mode": s.mode, "url": s.url},
                 "status": "failed", "error": f"dump: {type(ex).__name__}: {ex}", "animals": [], "dropped": [], "docs": []}
        e["seconds"] = round(time.monotonic() - t, 1)
        (a.out / f"{s.slug}.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        row = {"slug": s.slug, "name": s.name, "prefecture": s.prefecture, "kind": s.kind, "species": s.species,
               "mode": s.mode, "status": e["status"], "count": len(e["animals"]), "dropped": len(e["dropped"]),
               "docs": e.get("docs_total", 0), "error": e.get("error")}
        index.append(row)
        print(f"[{i}/{len(sources)}] {s.slug:32} {row['status']:9} {row['count']:4} 頭 捨て {row['dropped']:3} 文書 {row['docs']:3} {e['seconds']}s {row['error'] or ''}", flush=True)
    index_path = a.out / "_index.json"
    if index_path.exists():
        # 既存の index に今回の分を混ぜる（台帳の並び順を保つ）
        old = {r["slug"]: r for r in json.loads(index_path.read_text(encoding="utf-8"))}
        old.update({r["slug"]: r for r in index})
        order = {s.slug: i for i, s in enumerate(load_sources())}
        index = sorted(old.values(), key=lambda r: order.get(r["slug"], 9999))
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done {len(sources)} sources in {round(time.monotonic() - t0)}s → {a.out}（index {len(index)} 件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
