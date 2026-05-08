#!/usr/bin/env python3
"""
sites.yaml の全 list_url に対して robots.txt 遵守チェックを実行する CLI

使い方:
    python3 scripts/monitoring/check_robots.py

終了コード:
    0: 全サイト許可、または robots.txt 不在
    1: 1件以上の disallow を検出（CI で fail させたい場合に使う）
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import yaml

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.data_collector.utils.robots_check import (  # noqa: E402
    DEFAULT_USER_AGENT,
    RobotCheckResult,
    is_allowed_by_robots,
    summarize,
)

SITES_YAML = ROOT / "src" / "data_collector" / "config" / "sites.yaml"
HTTP_TIMEOUT = 10.0


def fetch_robots(target_url: str, client: httpx.Client) -> str:
    """robots.txt を取得。404 や接続失敗は空文字を返す（permissive 扱い）"""
    from urllib.parse import urlparse

    parsed = urlparse(target_url)
    if not parsed.netloc:
        return ""
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        resp = client.get(robots_url, timeout=HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except (httpx.RequestError, httpx.HTTPStatusError):
        pass
    return ""


def load_sites() -> list[dict]:
    with open(SITES_YAML, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("sites", [])


def main() -> int:
    sites = load_sites()
    print(f"Checking {len(sites)} sites against robots.txt...\n")

    results: list[RobotCheckResult] = []
    with httpx.Client(headers={"User-Agent": DEFAULT_USER_AGENT}) as client:
        for site in sites:
            url = site.get("list_url")
            if not url:
                continue
            robots_txt = fetch_robots(url, client)
            r = is_allowed_by_robots(url, robots_txt)
            results.append(r)
            mark = "OK" if r.allowed else "BLOCKED"
            print(f"  [{mark:7}] {site.get('name', '?')} — {url}")
            if not r.allowed:
                print(f"            reason: {r.reason}")

    s = summarize(results)
    print(
        f"\n=== Summary: {s['total']} sites, "
        f"{s['allowed']} allowed, {s['disallowed']} disallowed ==="
    )
    return 1 if s["disallowed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
