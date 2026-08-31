"""scripts/sync_remote_patterns.py の単体テスト (T104)。

sites.yaml / next.config.ts の実ファイルではなく tmp_path 上の合成フィクスチャで
検出・自動追記ロジックそのものを検証する。実ファイルとの整合性は
tests/test_image_remote_patterns.py が別途担保する。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from sync_remote_patterns import (  # noqa: E402
    MAX_REMOTE_PATTERNS,
    RemotePatternsSyncError,
    apply_fix,
    build_report,
    load_next_config_hostnames,
    load_sites_hosts,
    main,
    matches_wildcard,
)

# 実ファイルを模した最小フィクスチャ。remotePatterns の構造 (4スペース閉じ括弧)
# は next.config.ts と揃える (_insert_hostnames の挿入位置検出がこれに依存する)。
# `{}` が多用の TS 構文と衝突するため str.format は使わず前後を単純結合する。
_NEXT_CONFIG_HEADER = """import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    loader: 'custom',
    remotePatterns: [
      { protocol: 'https', hostname: '**.jp' },
      { protocol: 'https', hostname: '**.okinawa' },
"""
_NEXT_CONFIG_FOOTER = """    ],
  },
};

export default nextConfig;
"""


def _write_next_config(path: Path, extra_hostnames: list[str]) -> None:
    extra = "".join(f"      {{ protocol: 'https', hostname: '{h}' }},\n" for h in extra_hostnames)
    path.write_text(_NEXT_CONFIG_HEADER + extra + _NEXT_CONFIG_FOOTER, encoding="utf-8")


def _write_sites_yaml(path: Path, urls: list[str]) -> None:
    lines = ["sites:"]
    for i, url in enumerate(urls):
        lines.append(f'  - name: "テストサイト{i}"')
        lines.append(f'    list_url: "{url}"')
        lines.append('    category: "lost"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_matches_wildcard_covers_suffix_and_exact():
    wildcards = ["**.jp", "**.okinawa", "example-shelter.com"]
    assert matches_wildcard("city.example.jp", wildcards)
    assert matches_wildcard("example.jp", wildcards)
    assert matches_wildcard("example-shelter.com", wildcards)
    assert not matches_wildcard("example-shelter.net", wildcards)
    assert not matches_wildcard("notjp.example.com", wildcards)


def test_build_report_detects_missing_host(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(
        sites_yaml,
        [
            "https://city.example.jp/list",  # **.jp でカバー済み
            "https://shinki-mishuuroku.example-shelter.com/list",  # 未列挙
        ],
    )
    _write_next_config(next_config, extra_hostnames=[])

    report = build_report(sites_yaml, next_config)

    assert report.missing_hosts == ["shinki-mishuuroku.example-shelter.com"]
    assert not report.in_sync


def test_build_report_detects_dead_hostname(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://city.example.jp/list"])
    _write_next_config(next_config, extra_hostnames=["unused-shelter.com"])

    report = build_report(sites_yaml, next_config)

    assert report.in_sync  # 不足ホストはない
    assert report.dead_hostnames == ["unused-shelter.com"]


def test_build_report_in_sync_when_all_covered(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(
        sites_yaml,
        ["https://city.example.jp/list", "https://shelter.example-shelter.com/list"],
    )
    _write_next_config(next_config, extra_hostnames=["shelter.example-shelter.com"])

    report = build_report(sites_yaml, next_config)

    assert report.in_sync
    assert report.dead_hostnames == []


def test_apply_fix_inserts_missing_host_and_resolves(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(
        sites_yaml,
        [
            "https://city.example.jp/list",
            "https://shinki-mishuuroku.example-shelter.com/list",
        ],
    )
    _write_next_config(next_config, extra_hostnames=["existing-shelter.com"])

    before_report = build_report(sites_yaml, next_config)
    assert before_report.missing_hosts == ["shinki-mishuuroku.example-shelter.com"]

    apply_fix(before_report.missing_hosts, next_config)

    content = next_config.read_text(encoding="utf-8")
    assert "hostname: 'shinki-mishuuroku.example-shelter.com'" in content
    # 既存のエントリ (コメントや他ホスト) を壊していないこと
    assert "hostname: 'existing-shelter.com'" in content
    assert content.count("hostname:") == 4  # **.jp / **.okinawa / 既存1 / 新規1

    after_report = build_report(sites_yaml, next_config)
    assert after_report.in_sync


def test_apply_fix_noop_when_no_missing_hosts(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://city.example.jp/list"])
    _write_next_config(next_config, extra_hostnames=[])
    original = next_config.read_text(encoding="utf-8")

    apply_fix([], next_config)

    assert next_config.read_text(encoding="utf-8") == original


def test_apply_fix_raises_when_remote_patterns_block_missing(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://shinki.example-shelter.com/list"])
    next_config.write_text("export default {};\n", encoding="utf-8")

    with pytest.raises(RemotePatternsSyncError, match="remotePatterns"):
        apply_fix(["shinki.example-shelter.com"], next_config)


def test_apply_fix_raises_when_exceeding_max_patterns(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    # 既存で上限ちょうどのホスト数を作り、1件追加で超過させる。
    existing = [
        f"existing-{i}.com" for i in range(MAX_REMOTE_PATTERNS - 2)
    ]  # + **.jp/**.okinawa で上限ちょうど
    _write_sites_yaml(sites_yaml, [f"https://existing-{i}.com/list" for i in range(len(existing))])
    _write_next_config(next_config, extra_hostnames=existing)
    original = next_config.read_text(encoding="utf-8")

    with pytest.raises(RemotePatternsSyncError, match="上限"):
        apply_fix(["one-more.com"], next_config)

    # 書き込みが行われていないこと
    assert next_config.read_text(encoding="utf-8") == original


def test_main_check_only_returns_1_when_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://shinki.example-shelter.com/list"])
    _write_next_config(next_config, extra_hostnames=[])

    exit_code = main(["--sites-yaml", str(sites_yaml), "--next-config", str(next_config)])

    assert exit_code == 1
    assert "shinki.example-shelter.com" in capsys.readouterr().err


def test_main_returns_0_when_in_sync(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://city.example.jp/list"])
    _write_next_config(next_config, extra_hostnames=[])

    exit_code = main(["--sites-yaml", str(sites_yaml), "--next-config", str(next_config)])

    assert exit_code == 0


def test_main_fix_applies_and_returns_0(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://shinki.example-shelter.com/list"])
    _write_next_config(next_config, extra_hostnames=[])

    exit_code = main(["--fix", "--sites-yaml", str(sites_yaml), "--next-config", str(next_config)])

    assert exit_code == 0
    assert "hostname: 'shinki.example-shelter.com'" in next_config.read_text(encoding="utf-8")


def test_load_sites_hosts_and_load_next_config_hostnames_smoke(tmp_path: Path):
    sites_yaml = tmp_path / "sites.yaml"
    next_config = tmp_path / "next.config.ts"
    _write_sites_yaml(sites_yaml, ["https://a.example.jp/list", "https://b.example.jp/list"])
    _write_next_config(next_config, extra_hostnames=["c.example.com"])

    assert load_sites_hosts(sites_yaml) == {"a.example.jp", "b.example.jp"}
    assert "c.example.com" in load_next_config_hostnames(next_config)
