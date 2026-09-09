"""ドキュメント記載のサイト数/requires_js件数が sites.yaml の実測値と一致するかを検査する (T142)

211サイト/requires_js 27件のような値をドキュメントに固定値でハードコードすると、
sites.yaml が更新されるたびに無言で乖離していく (2026-09-09 時点の監査で
.kiro/steering/structure.md の "211サイト" 記載が実際は213件へ乖離していたのを発見)。
CI で機械的に検出できるよう、ここで一致を強制する。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SITES_YAML = REPO_ROOT / "src" / "data_collector" / "config" / "sites.yaml"


def _load_site_counts() -> tuple[int, int]:
    """(総サイト数, requires_js: true のサイト数) を返す"""
    with open(SITES_YAML, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    sites = data["sites"]
    total = len(sites)
    requires_js = sum(1 for s in sites if s.get("requires_js"))
    return total, requires_js


def test_architecture_md_site_count_matches_sites_yaml() -> None:
    """ARCHITECTURE.md に書かれたサイト数が sites.yaml の実件数と一致するか"""
    total, _ = _load_site_counts()
    text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert f"{total} サイト" in text or f"{total}サイト" in text, (
        f"ARCHITECTURE.md のサイト数表記が sites.yaml の実件数 ({total}) と一致しません。"
        "sites.yaml を更新したら ARCHITECTURE.md の該当箇所も更新してください。"
    )


def test_adapters_wiki_site_and_js_counts_match_sites_yaml() -> None:
    """docs/wiki/03-adapters.md のサイト数 / requires_js 件数が sites.yaml と一致するか"""
    total, requires_js = _load_site_counts()
    text = (REPO_ROOT / "docs" / "wiki" / "03-adapters.md").read_text(encoding="utf-8")

    assert f"エントリ数({total})" in text or f"{total} エントリ" in text, (
        f"docs/wiki/03-adapters.md のサイト数表記が sites.yaml の実件数 ({total}) と"
        "一致しません。sites.yaml を更新したら本ファイルの該当箇所も更新してください。"
    )

    js_match = re.search(r"requires_js: true`、(\d+)サイト", text)
    assert js_match is not None, (
        "docs/wiki/03-adapters.md に requires_js 件数の記載パターンが見つかりません "
        "(想定書式: 「requires_js: true`、N サイト」)。書式を変更した場合は本テストの "
        "正規表現も更新してください。"
    )
    assert int(js_match.group(1)) == requires_js, (
        f"docs/wiki/03-adapters.md の requires_js 件数 ({js_match.group(1)}) が "
        f"sites.yaml の実件数 ({requires_js}) と一致しません。"
    )
