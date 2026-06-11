"""frontend/next.config.ts の remotePatterns と sites.yaml の整合性確認テスト

frontend 側で画像最適化 (`/_next/image`) を機能させるには、sites.yaml の各サイト
ホストが next.config.ts の `remotePatterns` に一致する必要がある。列挙漏れは
ビルド時には検出されず、本番で「特定自治体の動物画像だけ表示されない」という
silent failure として現れるため、ingestion 側のテストで列挙漏れを検出する。

ワイルドカード方針 (**.jp / **.okinawa) は維持しつつ、それ以外の TLD
(.com / 特殊 TLD) のホストが全て個別列挙されていることを担保する。
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SITES_YAML = REPO_ROOT / "src" / "data_collector" / "config" / "sites.yaml"
NEXT_CONFIG = REPO_ROOT / "frontend" / "next.config.ts"


def _load_sites_hosts() -> set[str]:
    """sites.yaml から全サイトの hostname を抽出する"""
    with SITES_YAML.open() as f:
        cfg = yaml.safe_load(f)
    hosts: set[str] = set()
    for site in cfg.get("sites", []):
        url = site.get("list_url") or site.get("url")
        if not url:
            continue
        host = urlparse(url).hostname
        if host:
            hosts.add(host)
    return hosts


def _load_next_config_hostnames() -> list[str]:
    """next.config.ts から hostname フィールドを抽出する

    `{ protocol: 'https', hostname: 'xxx' }` の hostname 部分を全て拾う。
    """
    content = NEXT_CONFIG.read_text(encoding="utf-8")
    # `hostname: '...'` または `hostname: "..."` を抽出
    pattern = re.compile(r"hostname:\s*['\"]([^'\"]+)['\"]")
    return pattern.findall(content)


def _matches_wildcard(host: str, wildcards: list[str]) -> bool:
    """**.jp 形式のワイルドカードと host を比較する

    Next.js の `hostname` ワイルドカード仕様:
    - `**.jp` は任意のサブドメイン + .jp に一致 (`a.b.jp`, `c.jp` 等)
    """
    for wc in wildcards:
        if wc.startswith("**."):
            suffix = wc[2:]  # ".jp" 等
            if host == suffix.lstrip(".") or host.endswith(suffix):
                return True
        elif wc == host:
            return True
    return False


def test_all_sites_yaml_hosts_are_covered_by_next_config():
    """sites.yaml の全 hostname が next.config.ts の remotePatterns に一致する

    一致経路:
      - **.jp / **.okinawa ワイルドカード
      - .com 等の個別 hostname 列挙

    列挙漏れがあると本番で `/_next/image?url=https://that-host/...` が
    400 を返し、その自治体の動物カードの画像だけ全て表示されない silent
    failure が発生する。
    """
    yaml_hosts = _load_sites_hosts()
    next_hostnames = _load_next_config_hostnames()
    assert yaml_hosts, "sites.yaml から hostname が抽出できなかった"
    assert next_hostnames, "next.config.ts から hostname が抽出できなかった"

    missing = [h for h in sorted(yaml_hosts) if not _matches_wildcard(h, next_hostnames)]
    assert not missing, (
        "next.config.ts の remotePatterns に列挙されていないホストがあります "
        "(本番で画像最適化が失敗): " + ", ".join(missing)
    )


def test_non_wildcard_hostnames_are_actually_used_by_sites():
    """next.config.ts の個別 hostname が実際に sites.yaml で使用されている

    yaml に存在しない host を例外列挙しても本番では絶対に使われないため
    dead code。列挙のメンテナンス時の取りこぼし防止として警告する。
    """
    yaml_hosts = _load_sites_hosts()
    next_hostnames = _load_next_config_hostnames()
    # ワイルドカードを除いた個別 hostname のみ検査
    individuals = [h for h in next_hostnames if not h.startswith("**.")]
    unused = [h for h in individuals if h not in yaml_hosts]
    assert not unused, (
        "next.config.ts に列挙されているが sites.yaml に存在しない hostname "
        "(dead exception entry): " + ", ".join(unused)
    )
