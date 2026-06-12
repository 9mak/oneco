#!/usr/bin/env python3
"""sites.yaml から /transparency ページ用の自治体一覧 JSON を生成する。

入力: src/data_collector/config/sites.yaml
出力: frontend/data/transparency-sites.json

実行: python3 scripts/generate_transparency_sites.py
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITES_YAML = ROOT / "src" / "data_collector" / "config" / "sites.yaml"
OUTPUT_JSON = ROOT / "frontend" / "data" / "transparency-sites.json"


def host_of(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc or url


def main() -> None:
    with SITES_YAML.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sites = config.get("sites", [])
    by_prefecture: dict[str, list[dict[str, str]]] = {}
    seen: set[tuple[str, str, str]] = set()

    for site in sites:
        prefecture = site.get("prefecture", "不明")
        name = site.get("name", "")
        list_url = site.get("list_url", "")
        host = host_of(list_url)
        key = (prefecture, name, host)
        if key in seen:
            continue
        seen.add(key)
        by_prefecture.setdefault(prefecture, []).append(
            {"name": name, "host": host, "url": list_url}
        )

    for prefecture in by_prefecture:
        by_prefecture[prefecture].sort(key=lambda x: x["name"])

    payload = {
        "total_sources": sum(len(v) for v in by_prefecture.values()),
        "total_prefectures": len(by_prefecture),
        "total_hosts": len({s["host"] for v in by_prefecture.values() for s in v}),
        "by_prefecture": dict(sorted(by_prefecture.items())),
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Wrote {OUTPUT_JSON.relative_to(ROOT)}: "
        f"{payload['total_sources']} sources / "
        f"{payload['total_prefectures']} prefectures / "
        f"{payload['total_hosts']} hosts"
    )


if __name__ == "__main__":
    main()
