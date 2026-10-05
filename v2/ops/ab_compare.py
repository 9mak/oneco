"""エンジン・レシピを変えたときの回帰確認: 同じ取得結果に 2 つの v2 を当て、slug ごとに結果を比べる。

  PY=/Users/k/Desktop/oneco/.venv/bin/python
  # 1) 基準の v2（例: origin/main を書き出したもの）で読む。取得結果は --cache に 1 URL 1 ファイルで残る
  $PY ops/ab_compare.py run --engine /path/to/base/v2 --cache $TMPDIR/ab-cache --out $TMPDIR/a.json
  # 2) 変更後の v2 で同じキャッシュを読む（キャッシュに無い URL だけ取りに行き、それも残す。--offline なら取りに行かない）
  $PY ops/ab_compare.py run --engine /path/to/new/v2 --cache $TMPDIR/ab-cache --out $TMPDIR/b.json
  # 3) 差分（頭数・状態・増えた子・消えた子・項目の変化）
  $PY ops/ab_compare.py diff $TMPDIR/a.json $TMPDIR/b.json

--engine に渡した v2 の collector・registry・recipes がそのまま使われる。エンジンだけの差を見たいときは、
旧 collector と新 recipes・registry を 1 つのディレクトリに並べて渡す。--only で slug の前方一致に絞れる。
取得の失敗（404・切断）も「同じ失敗」として残すので、2 回目以降は同じ入力で比べられる。
render を使うレシピ（Playwright）とネットワークはサンドボックスの外で動かす。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any


def caching_fetcher_class(base_cls: type, fetch_error: type, page_cls: type) -> type:
    """base_cls（collector.fetch.Fetcher か FakeFetcher）の get / render の結果をディスクに残すサブクラスを作る。

    エンジンの版ごとに Fetcher が違うので、読み込んだ版のクラスから作る。
    """

    class CachingFetcher(base_cls):  # type: ignore[misc, valid-type]
        def __init__(self, cache: Path, offline: bool = False, *args: Any, **kw: Any) -> None:
            super().__init__(*args, **kw)
            self.cache_dir = Path(cache)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.offline = offline
            self.hits = 0
            self.misses = 0

        def _path(self, key: list[Any]) -> Path:
            h = hashlib.sha1(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()
            return self.cache_dir / f"{h}.json"

        def _write(self, p: Path, rec: dict[str, Any]) -> None:
            fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
            os.replace(tmp, p)

        def _cached(self, key: list[Any], live: Any) -> Any:
            p = self._path(key)
            if p.exists():
                self.hits += 1
                rec = json.loads(p.read_text(encoding="utf-8"))
                if "error" in rec:
                    raise fetch_error(rec["error"])
                return page_cls(rec["url"], rec["final_url"], rec["status"], base64.b64decode(rec["content"]),
                                rec["html"], rec["content_type"], rec.get("captured") or [])
            if self.offline:
                raise fetch_error(f"キャッシュに無い: {key}")
            self.misses += 1
            try:
                page = live()
            except fetch_error as e:
                self._write(p, {"key": key, "error": str(e)})
                raise
            self._write(p, {"key": key, "url": page.url, "final_url": page.final_url, "status": page.status,
                            "content": base64.b64encode(page.content).decode("ascii"), "html": page.html,
                            "content_type": page.content_type, "captured": list(getattr(page, "captured", []) or [])})
            return page

        def get(self, url: str, encoding: str | None = None, **kw: Any) -> Any:
            return self._cached(["get", url, encoding], lambda: base_cls.get(self, url, encoding=encoding, **kw))

        def render(self, url: str, *args: Any, **kw: Any) -> Any:
            key = ["render", url, kw.get("capture"), kw.get("wait_for")]
            return self._cached(key, lambda: base_cls.render(self, url, *args, **kw))

    return CachingFetcher


# --- run ---------------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> int:
    engine = Path(args.engine).resolve()
    if not (engine / "collector").is_dir():
        print(f"collector が無い: {engine}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(engine))
    fetch = importlib.import_module("collector.fetch")
    run = importlib.import_module("collector.run")
    registry = importlib.import_module("collector.registry")
    fetcher = caching_fetcher_class(fetch.Fetcher, fetch.FetchError, fetch.Page)(Path(args.cache), args.offline)
    sources = registry.load_sources()
    if args.only:
        sources = [s for s in sources if any(s.slug == p or s.slug.startswith(p) for p in args.only)]
    slugs: dict[str, Any] = {}
    t0 = time.monotonic()
    for s in sources:
        t = time.monotonic()
        status, res, err, _trace = run.collect_one(s, fetcher)
        slugs[s.slug] = {
            "status": status, "error": err, "count": len(res.animals) if res else 0,
            "rows": res.rows if res else 0, "dropped": len(res.dropped) if res else 0,
            "dropped_reasons": dict(Counter(d.reason for d in res.dropped)) if res else {},
            "animals": res.animals if res else [], "seconds": round(time.monotonic() - t, 1),
        }
        print(f"{s.slug:32s} {status:9s} {slugs[s.slug]['count']:4d} {err or ''}", file=sys.stderr, flush=True)
    out = {"engine": str(engine), "cache": str(args.cache), "seconds": round(time.monotonic() - t0),
           "hits": fetcher.hits, "misses": fetcher.misses, "slugs": slugs}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(v["count"] for v in slugs.values())
    st = Counter(v["status"] for v in slugs.values())
    print(f"{len(slugs)} slug・{total} 頭・{dict(st)}・キャッシュ hit {fetcher.hits} / 取得 {fetcher.misses}・{out['seconds']} 秒")
    return 0


# --- diff --------------------------------------------------------------------------------
def _brief(a: dict[str, Any]) -> str:
    keys = ("management_no", "name", "shelter_date", "image_url", "source_url")
    return " ".join(f"{k}={a[k]}" for k in keys if a.get(k))[:200]


def diff_results(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """a・b は cmd_run の出力。slug ごとに状態・頭数・捨てた行数・増えた子・消えた子・同じ ID の項目の変化を出す。"""
    sa, sb = a.get("slugs", {}), b.get("slugs", {})
    unchanged: list[str] = []
    changed: list[dict[str, Any]] = []
    for slug in sorted(set(sa) | set(sb)):
        ra, rb = sa.get(slug) or {}, sb.get(slug) or {}
        ia = {x["id"]: x for x in ra.get("animals", [])}
        ib = {x["id"]: x for x in rb.get("animals", [])}
        fields: dict[str, list[list[Any]]] = {}
        for aid in [i for i in ia if i in ib]:
            for k in sorted((set(ia[aid]) | set(ib[aid])) - {"id"}):
                if ia[aid].get(k) != ib[aid].get(k):
                    fields.setdefault(k, []).append([aid, ia[aid].get(k), ib[aid].get(k)])
        c = {
            "slug": slug,
            "status": [ra.get("status"), rb.get("status")],
            "count": [ra.get("count", 0), rb.get("count", 0)],
            "dropped": [ra.get("dropped", 0), rb.get("dropped", 0)],
            "error": [ra.get("error"), rb.get("error")],
            "added": [i for i in ib if i not in ia],
            "removed": [i for i in ia if i not in ib],
            "added_detail": [_brief(ib[i]) for i in ib if i not in ia],
            "removed_detail": [_brief(ia[i]) for i in ia if i not in ib],
            "fields": fields,
        }
        same = (c["status"][0] == c["status"][1] and c["count"][0] == c["count"][1] and c["dropped"][0] == c["dropped"][1]
                and not c["added"] and not c["removed"] and not fields)
        (unchanged.append(slug) if same else changed.append(c))
    return {"unchanged": unchanged, "changed": changed}


def format_diff(d: dict[str, Any], limit: int = 5) -> str:
    lines = [f"変化なし {len(d['unchanged'])} slug・変化あり {len(d['changed'])} slug"]
    for c in d["changed"]:
        s0, s1 = c["status"]
        lines.append(f"== {c['slug']}: {s0} → {s1}  頭数 {c['count'][0]} → {c['count'][1]}  捨てた {c['dropped'][0]} → {c['dropped'][1]}"
                     f"  +{len(c['added'])} -{len(c['removed'])}")
        if c["error"][0] != c["error"][1]:
            lines.append(f"   error: {c['error'][0]} → {c['error'][1]}")
        for tag, items in (("+", c["added_detail"]), ("-", c["removed_detail"])):
            for x in items[:limit]:
                lines.append(f"   {tag} {x}")
            if len(items) > limit:
                lines.append(f"   {tag} … 他 {len(items) - limit}")
        for k, vs in c["fields"].items():
            lines.append(f"   ~ {k}: {len(vs)} 頭")
            for aid, v0, v1 in vs[:limit]:
                lines.append(f"       {aid}: {v0!r} → {v1!r}")
    return "\n".join(lines)


def cmd_diff(args: argparse.Namespace) -> int:
    a = json.loads(Path(args.a).read_text(encoding="utf-8"))
    b = json.loads(Path(args.b).read_text(encoding="utf-8"))
    d = diff_results(a, b)
    print(format_diff(d, limit=args.limit))
    if args.json:
        Path(args.json).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="--engine の v2 で全ページ（または --only）を読み、結果を --out に書く")
    r.add_argument("--engine", required=True, help="collector・registry・recipes を含む v2 ディレクトリ")
    r.add_argument("--cache", required=True, help="取得結果を残すディレクトリ（2 回目以降は再生する）")
    r.add_argument("--out", required=True)
    r.add_argument("--only", nargs="*", help="slug の前方一致")
    r.add_argument("--offline", action="store_true", help="キャッシュに無い URL を取りに行かない")
    r.set_defaults(func=cmd_run)
    d = sub.add_parser("diff", help="run の出力 2 つを比べる")
    d.add_argument("a")
    d.add_argument("b")
    d.add_argument("--json", help="差分を JSON でも書く")
    d.add_argument("--limit", type=int, default=5, help="slug ごとに表示する例の数")
    d.set_defaults(func=cmd_diff)
    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
