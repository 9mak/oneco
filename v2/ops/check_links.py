"""公開前の機械チェック: data/latest.json の source_url（全ユニーク）と image_url（サンプル）が HTTP 200 で開くか。

  python ops/check_links.py            # source_url は全部、image_url は 80 件サンプル
  python ops/check_links.py --images 0 # 画像は見ない

自治体サーバーへの負荷を抑えるため同時 4・1 ホスト連続にしない。結果は非 200 だけ表示し、非 200 が 1 件でもあれば exit 1。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (compatible; oneco-linkcheck/1.0; +https://github.com/9mak/oneco)"


def status(url: str) -> tuple[str, int | str]:
    try:
        with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": UA}) as c:
            r = c.get(url)
            return url, r.status_code
    except Exception as e:
        return url, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "latest.json"))
    ap.add_argument("--images", type=int, default=80, help="image_url のサンプル数（0 で見ない）")
    ap.add_argument("--seed", type=int, default=20260930)
    a = ap.parse_args()
    d = json.load(open(a.data, encoding="utf-8"))
    animals = d["animals"]
    src_urls = sorted({x["source_url"] for x in animals})
    rnd = random.Random(a.seed)
    imgs = [x["image_url"] for x in animals if x.get("image_url")]
    img_sample = rnd.sample(imgs, min(a.images, len(imgs))) if a.images else []
    print(f"source_url {len(src_urls)} 件（ユニーク）、image_url {len(img_sample)} 件（{len(imgs)} 件からサンプル）")
    bad = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for url, st in ex.map(status, src_urls + img_sample):
            if st != 200:
                bad.append((url, st))
    by_source = {}
    for x in animals:
        by_source.setdefault(x["source_url"], x["source"])
    for url, st in bad:
        print(f"  {st}  {url}  ({by_source.get(url, 'image')})")
    print(f"非 200: {len(bad)} 件")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
