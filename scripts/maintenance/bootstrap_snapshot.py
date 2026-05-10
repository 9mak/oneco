#!/usr/bin/env python3
"""
Bootstrap snapshot from production DB.

Phase A の SnapshotStore は「2 日目以降の LLM 抽出をスキップ」する仕組みだが、
初回フル抽出が Groq 100K tokens/day で完走しないため snapshot が育たない。
本スクリプトは production DB に既に保存されている動物データを REST API
経由で取得し、`snapshots/latest.json` に書き込んで bootstrap する。

実行後、`git add snapshots/latest.json && git commit && git push` すれば
次回の data-collector workflow で **既知 URL の LLM 抽出がスキップされる** ため、
新規動物の抽出だけに Groq の token 予算を使えるようになる。

使い方:
    python3 scripts/maintenance/bootstrap_snapshot.py
    python3 scripts/maintenance/bootstrap_snapshot.py --api-base https://...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.data_collector.domain.models import AnimalData  # noqa: E402

DEFAULT_API_BASE = "https://oneco-api-tvlsrcvyuq-an.a.run.app"
SNAPSHOT_PATH = ROOT / "snapshots" / "latest.json"
PAGE_SIZE = 1000  # API max


def fetch_all_animals(api_base: str) -> list[dict]:
    """全件を pagination で取得する"""
    items: list[dict] = []
    offset = 0
    with httpx.Client(timeout=30.0) as client:
        while True:
            url = f"{api_base}/animals?limit={PAGE_SIZE}&offset={offset}"
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            page = payload.get("items", [])
            items.extend(page)
            print(f"  fetched offset={offset}, count={len(page)}, total={len(items)}")
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
    return items


def to_animal_data(item: dict) -> AnimalData | None:
    """API レスポンスの 1 動物を AnimalData にバリデート。失敗したら None。"""
    # id, status_changed_at 等の不要フィールドを落とす（AnimalData は受け付けるが
    # 余計なものは保存しない方針）
    fields = {
        k: v
        for k, v in item.items()
        if k
        in {
            "species",
            "shelter_date",
            "location",
            "prefecture",
            "source_url",
            "category",
            "sex",
            "age_months",
            "color",
            "size",
            "phone",
            "image_urls",
            "status",
            "status_changed_at",
            "outcome_date",
            "local_image_paths",
        }
    }
    try:
        return AnimalData.model_validate(fields)
    except Exception as e:
        print(f"  WARN: skip animal {item.get('source_url')!r}: {e}", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default=DEFAULT_API_BASE)
    ap.add_argument(
        "--out",
        default=str(SNAPSHOT_PATH),
        help=f"出力先（デフォルト: {SNAPSHOT_PATH.relative_to(ROOT)}）",
    )
    args = ap.parse_args()

    print(f"Fetching animals from {args.api_base}/animals ...")
    raw_items = fetch_all_animals(args.api_base)
    print(f"Total fetched: {len(raw_items)}")

    print("Validating against AnimalData schema ...")
    animals: list[AnimalData] = []
    for item in raw_items:
        a = to_animal_data(item)
        if a is not None:
            animals.append(a)
    print(f"Valid animals: {len(animals)} / {len(raw_items)}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [a.model_dump(mode="json") for a in animals]
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote snapshot: {out_path}")
    print(f"  unique source_urls: {len({a.source_url for a in animals})}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
