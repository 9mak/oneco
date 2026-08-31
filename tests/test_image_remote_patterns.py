"""frontend/next.config.ts の remotePatterns と sites.yaml の整合性確認テスト

frontend 側で画像最適化 (`/_next/image`) を機能させるには、sites.yaml の各サイト
ホストが next.config.ts の `remotePatterns` に一致する必要がある。列挙漏れは
ビルド時には検出されず、本番で「特定自治体の動物画像だけ表示されない」という
silent failure として現れるため、ingestion 側のテストで列挙漏れを検出する。

ワイルドカード方針 (**.jp / **.okinawa) は維持しつつ、それ以外の TLD
(.com / 特殊 TLD) のホストが全て個別列挙されていることを担保する。

検知ロジック本体は scripts/sync_remote_patterns.py に一本化されている
(T104: `--fix` で不足ホストを自動追記できる同期スクリプト)。このテストは
その関数を import して使うことでロジックの二重管理を避ける
(scripts/site_count_audit.py が scripts/zero_count_audit.py を import するのと
同じ sys.path 追加パターンに倣う)。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITES_YAML = REPO_ROOT / "src" / "data_collector" / "config" / "sites.yaml"
NEXT_CONFIG = REPO_ROOT / "frontend" / "next.config.ts"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from sync_remote_patterns import (  # noqa: E402
    build_report,
    load_next_config_hostnames,
    load_sites_hosts,
)


def test_all_sites_yaml_hosts_are_covered_by_next_config():
    """sites.yaml の全 hostname が next.config.ts の remotePatterns に一致する

    一致経路:
      - **.jp / **.okinawa ワイルドカード
      - .com 等の個別 hostname 列挙

    列挙漏れがあると本番で `/_next/image?url=https://that-host/...` が
    400 を返し、その自治体の動物カードの画像だけ全て表示されない silent
    failure が発生する。
    """
    assert load_sites_hosts(SITES_YAML), "sites.yaml から hostname が抽出できなかった"
    assert load_next_config_hostnames(NEXT_CONFIG), (
        "next.config.ts から hostname が抽出できなかった"
    )

    report = build_report(SITES_YAML, NEXT_CONFIG)
    assert not report.missing_hosts, (
        "next.config.ts の remotePatterns に列挙されていないホストがあります "
        "(本番で画像最適化が失敗): " + ", ".join(report.missing_hosts) + "\n"
        "`python3 scripts/sync_remote_patterns.py --fix` で自動追記できます。"
    )


def test_non_wildcard_hostnames_are_actually_used_by_sites():
    """next.config.ts の個別 hostname が実際に sites.yaml で使用されている

    yaml に存在しない host を例外列挙しても本番では絶対に使われないため
    dead code。列挙のメンテナンス時の取りこぼし防止として警告する。
    """
    report = build_report(SITES_YAML, NEXT_CONFIG)
    assert not report.dead_hostnames, (
        "next.config.ts に列挙されているが sites.yaml に存在しない hostname "
        "(dead exception entry): " + ", ".join(report.dead_hostnames)
    )
