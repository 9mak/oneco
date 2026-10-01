"""監査ダンプ（ops/audit_dump.py の出力）を 1 slug 分、人が読める形で表示する。

  python ops/audit_show.py --dir data/audit-2026-09-30 <slug> [--text 9000] [--imgs 60]

監査エージェントはこれだけを読んで判定する（ネットワークには出ない）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--text", type=int, default=6000, help="文書本文の表示上限（文字）")
    ap.add_argument("--imgs", type=int, default=40, help="文書ごとの img 表示上限")
    ap.add_argument("--docs", type=int, default=12, help="表示する文書数の上限")
    a = ap.parse_args()
    p = a.dir / f"{a.slug}.json"
    if not p.exists():
        print(f"無い: {p}")
        return 2
    e = json.loads(p.read_text(encoding="utf-8"))
    r = e["registry"]
    print("=" * 100)
    print(f"slug: {r['slug']}  name: {r['name']}")
    print(f"prefecture: {r['prefecture']}  municipality: {r.get('municipality')}  kind: {r['kind']}  species: {r['species']}  mode: {r['mode']}  enabled: {r.get('enabled')}")
    print(f"url: {r['url']}")
    if r.get("note"):
        print(f"note: {r['note']}")
    print(f"status: {e['status']}  error: {e.get('error')}  rows: {e.get('rows')}  animals: {len(e.get('animals') or [])}  dropped: {len(e.get('dropped') or [])}  docs: {e.get('docs_total')}  empty_confirmed: {e.get('empty_confirmed')}")
    if e.get("trace"):
        print("trace:")
        for t in e["trace"][:20]:
            print(f"  {t}")
    if e.get("recipe_text"):
        print("-" * 40 + " recipe")
        print(e["recipe_text"].rstrip())
    docs = e.get("docs") or []
    for i, d in enumerate(docs[: a.docs]):
        print("-" * 40 + f" doc[{i}] {d['url']}  pdf={d.get('is_pdf')} rendered={d.get('rendered')} text_len={d.get('text_len')} imgs={d.get('img_count')}")
        if d.get("title"):
            print(f"title: {d['title']}")
        if d.get("headings"):
            print("headings: " + " | ".join(d["headings"][:40]))
        if d.get("pdf_table_head"):
            print(f"pdf_tables: {d.get('pdf_tables')}  先頭行: {json.dumps(d['pdf_table_head'], ensure_ascii=False)[:600]}")
        imgs = d.get("imgs") or []
        if imgs:
            print(f"imgs（先頭 {min(len(imgs), a.imgs)} / {d.get('img_count')}）:")
            for im in imgs[: a.imgs]:
                print(f"  {im['src']}  alt={im.get('alt')!r}")
        print("text:")
        print((d.get("text") or "")[: a.text])
    if len(docs) > a.docs:
        print(f"… 他 {len(docs) - a.docs} 文書（--docs で増やせる）")
    print("-" * 40 + f" animals ({len(e.get('animals') or [])})")
    for an in e.get("animals") or []:
        shown = {k: v for k, v in an.items() if v not in (None, "") and k not in ("municipality", "prefecture", "phone", "address", "kind", "source")}
        print("  " + json.dumps(shown, ensure_ascii=False))
    print("-" * 40 + f" dropped ({len(e.get('dropped') or [])})")
    for dr in (e.get("dropped") or [])[:200]:
        print(f"  [{dr['reason']}] {dr['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
