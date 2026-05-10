#!/usr/bin/env python3
"""
sites.yaml のサイトのうち、詳細リンクの抽出ヒントが何も無いサイト
（= Data Collector が LLM で extract_detail_links を呼ぶサイト）を一覧表示する。

LLM 呼び出しを減らすには、これらのサイトに `list_link_pattern` を
人手で設定するのが効果的。

使い方:
    python3 scripts/maintenance/list_sites_without_link_pattern.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.data_collector.llm.config import SiteConfig, SiteConfigLoader  # noqa: E402

SITES_YAML = ROOT / "src" / "data_collector" / "config" / "sites.yaml"


def needs_link_pattern(site: SiteConfig) -> bool:
    """このサイトが LLM で extract_detail_links を呼ぶか判定する。

    以下のいずれかが true なら LLM 抽出は不要:
    - list_link_pattern が設定済み（CSS セレクタで詳細URL取得）
    - pdf_link_pattern が設定済み（PDF からの抽出）
    - single_page=True（list_url 自体が動物情報、詳細ページなし）
    """
    if site.list_link_pattern:
        return False
    if site.pdf_link_pattern:
        return False
    if site.single_page:
        return False
    return True


def main() -> int:
    config = SiteConfigLoader.load(SITES_YAML)
    missing = [s for s in config.sites if needs_link_pattern(s)]

    print(f"Total sites: {len(config.sites)}")
    print(f"Sites without link pattern (LLM-only): {len(missing)}")
    print(f"Coverage: {len(config.sites) - len(missing)} / {len(config.sites)} sites covered")
    print()
    print("=== LLM extract_detail_links を呼ぶサイト ===")

    for site in missing:
        prefix = "[JS]" if site.requires_js else "    "
        print(f"  {prefix} {site.name}")
        print(f"         {site.list_url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
