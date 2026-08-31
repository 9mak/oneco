#!/usr/bin/env python3
"""sites.yaml の画像ホストと frontend/next.config.ts の remotePatterns を同期する (T104)。

これまで `tests/test_image_remote_patterns.py` は不一致を「検知するだけ」で、
新規サイト追加のたびに `next.config.ts` への追記は手作業だった (漏れると
本番で該当自治体の画像だけ表示されない silent failure になる、PR #179)。

このスクリプトは検知ロジックを一本化した上で、`--fix` で不足ホストを
`next.config.ts` の remotePatterns 個別列挙セクションへ自動追記できるようにする。
`tests/test_image_remote_patterns.py` はこのモジュールの検知関数を import して
使う (ロジックの二重管理を避ける)。

使い方:
    # 不足ホストの検知のみ (CI/pre-commit相当。不一致があれば exit 1)
    python3 scripts/sync_remote_patterns.py

    # 不足ホストを next.config.ts に自動追記する
    python3 scripts/sync_remote_patterns.py --fix

LLM は使わない。sites.yaml と next.config.ts の純粋な文字列/構造比較のみ。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITES_YAML = REPO_ROOT / "src" / "data_collector" / "config" / "sites.yaml"
DEFAULT_NEXT_CONFIG = REPO_ROOT / "frontend" / "next.config.ts"

# Next.js 16 の remotePatterns 上限 (next.config.ts のコメントに明記)。
# 超過するとビルドエラーになるため --fix はここで安全側に倒して止まる。
MAX_REMOTE_PATTERNS = 50

_HOSTNAME_RE = re.compile(r"hostname:\s*['\"]([^'\"]+)['\"]")
_REMOTE_PATTERNS_BLOCK_RE = re.compile(
    r"(?P<open>remotePatterns:\s*\[\n)(?P<body>.*?)(?P<close>\n( {4})\],)",
    re.DOTALL,
)


class RemotePatternsSyncError(RuntimeError):
    """next.config.ts の構造が想定と異なり自動追記できない場合に送出する。"""


@dataclass(frozen=True)
class SyncReport:
    """sites.yaml と next.config.ts の突き合わせ結果。"""

    missing_hosts: list[str] = field(default_factory=list)
    """sites.yaml にあるが next.config.ts の remotePatterns でカバーされていないホスト"""

    dead_hostnames: list[str] = field(default_factory=list)
    """next.config.ts に個別列挙されているが sites.yaml で使われていないホスト (dead entry)"""

    @property
    def in_sync(self) -> bool:
        return not self.missing_hosts


def load_sites_hosts(sites_yaml: Path = DEFAULT_SITES_YAML) -> set[str]:
    """sites.yaml から全サイトの hostname を抽出する。"""
    with sites_yaml.open(encoding="utf-8") as f:
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


def load_next_config_hostnames(next_config: Path = DEFAULT_NEXT_CONFIG) -> list[str]:
    """next.config.ts の remotePatterns から hostname フィールドを全て抽出する。"""
    content = next_config.read_text(encoding="utf-8")
    return _HOSTNAME_RE.findall(content)


def matches_wildcard(host: str, wildcards: list[str]) -> bool:
    """`**.jp` 形式のワイルドカードと個別列挙の両方に対して host の一致を判定する。

    Next.js の `hostname` ワイルドカード仕様:
        `**.jp` は任意のサブドメイン + `.jp` に一致する (`a.b.jp`, `c.jp` 等)。
    """
    for wc in wildcards:
        if wc.startswith("**."):
            suffix = wc[2:]  # ".jp" 等
            if host == suffix.lstrip(".") or host.endswith(suffix):
                return True
        elif wc == host:
            return True
    return False


def build_report(
    sites_yaml: Path = DEFAULT_SITES_YAML,
    next_config: Path = DEFAULT_NEXT_CONFIG,
) -> SyncReport:
    """sites.yaml と next.config.ts を突き合わせて不足/dead ホストを算出する。"""
    yaml_hosts = load_sites_hosts(sites_yaml)
    next_hostnames = load_next_config_hostnames(next_config)

    missing = sorted(h for h in yaml_hosts if not matches_wildcard(h, next_hostnames))

    individuals = [h for h in next_hostnames if not h.startswith("**.")]
    dead = sorted({h for h in individuals if h not in yaml_hosts})

    return SyncReport(missing_hosts=missing, dead_hostnames=dead)


def _insert_hostnames(content: str, hosts: list[str]) -> str:
    """remotePatterns 配列の末尾 (個別列挙セクション) に新規 hostname エントリを追記する。"""
    match = _REMOTE_PATTERNS_BLOCK_RE.search(content)
    if not match:
        raise RemotePatternsSyncError(
            "next.config.ts から remotePatterns 配列が見つかりませんでした "
            "(構造が変わった可能性があるので手動で確認してください)"
        )

    new_lines = "\n".join(
        f"      {{ protocol: 'https', hostname: '{host}' }}," for host in sorted(hosts)
    )
    new_body = match.group("body").rstrip("\n") + "\n" + new_lines
    new_block = match.group("open") + new_body + match.group("close")
    return content[: match.start()] + new_block + content[match.end() :]


def apply_fix(
    missing_hosts: list[str],
    next_config: Path = DEFAULT_NEXT_CONFIG,
) -> None:
    """不足ホストを next.config.ts に追記して書き戻す。

    Next.js の remotePatterns 上限 (50件) を超える場合は書き込まずに例外を送出する
    (機械的な追記だけでは解決できない設計判断が必要なため)。
    """
    if not missing_hosts:
        return

    current_hostnames = load_next_config_hostnames(next_config)
    total_after = len(current_hostnames) + len(missing_hosts)
    if total_after > MAX_REMOTE_PATTERNS:
        raise RemotePatternsSyncError(
            f"remotePatterns が Next.js の上限 {MAX_REMOTE_PATTERNS} 件を超えます "
            f"(現在 {len(current_hostnames)} 件 + 追加 {len(missing_hosts)} 件 = {total_after} 件)。"
            "個別列挙ではなくワイルドカード方針の見直しが必要なため自動追記を中止しました。"
        )

    content = next_config.read_text(encoding="utf-8")
    new_content = _insert_hostnames(content, missing_hosts)
    next_config.write_text(new_content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="不足ホストを next.config.ts に自動追記する (デフォルトは検知のみ)",
    )
    parser.add_argument(
        "--sites-yaml",
        type=Path,
        default=DEFAULT_SITES_YAML,
        help="sites.yaml のパス (既定: %(default)s)",
    )
    parser.add_argument(
        "--next-config",
        type=Path,
        default=DEFAULT_NEXT_CONFIG,
        help="next.config.ts のパス (既定: %(default)s)",
    )
    args = parser.parse_args(argv)

    report = build_report(args.sites_yaml, args.next_config)

    if report.dead_hostnames:
        print(
            "[警告] next.config.ts に列挙されているが sites.yaml で未使用のホスト "
            f"(dead entry): {', '.join(report.dead_hostnames)}",
            file=sys.stderr,
        )

    if report.in_sync:
        print("OK: sites.yaml の全ホストが next.config.ts の remotePatterns でカバーされています")
        return 0

    if not args.fix:
        print(
            "[NG] next.config.ts の remotePatterns に列挙されていないホストがあります:",
            file=sys.stderr,
        )
        for host in report.missing_hosts:
            print(f"  - {host}", file=sys.stderr)
        print(
            "\n`python3 scripts/sync_remote_patterns.py --fix` で自動追記できます。",
            file=sys.stderr,
        )
        return 1

    try:
        apply_fix(report.missing_hosts, args.next_config)
    except RemotePatternsSyncError as e:
        print(f"[エラー] 自動追記できませんでした: {e}", file=sys.stderr)
        return 2

    print(f"追記しました ({len(report.missing_hosts)} 件): {', '.join(report.missing_hosts)}")
    print(f"更新先: {args.next_config}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
