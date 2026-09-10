#!/usr/bin/env python3
"""GenericAdapter (T405) 用の site spec 雛形を生成する scaffold script。

一覧ページ URL を取得し、best-effort で
- list+detail 構造: detail link らしき `<a>` の候補セレクタ
- table 構造: `<thead>`/最初の `<th>` 行のヘッダ文字列
を検出して `config/site_specs/<slug>.yaml` を書き出す。

生成結果はあくまで叩き台。必ず実ページを見て `list_link_selector` /
`field_selectors` / `header_fields` を手直しすること (自動生成のまま使わない)。

Usage:
    uv run python scripts/new_site_spec.py <slug> <list_url> --name "サイト名"
    uv run python scripts/new_site_spec.py <slug> <list_url> --name "A" --name "B"
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup, Tag

_SPEC_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "data_collector" / "config" / "site_specs"
)
_USER_AGENT = "oneco-bot/1.0 (+https://github.com/9mak/oneco)"


def _guess_list_link_selector(soup: BeautifulSoup, base_url: str) -> str:
    """一覧ページ内で最も出現数の多い href パスの先頭セグメントを detail link 候補とする"""
    host = urlparse(base_url).netloc
    segment_counts: Counter[str] = Counter()
    for a in soup.find_all("a"):
        if not isinstance(a, Tag):
            continue
        href = a.get("href")
        if not href or not isinstance(href, str) or href.startswith("#"):
            continue
        path = urlparse(href).path
        if not path or path == "/":
            continue
        segments = [s for s in path.split("/") if s]
        if not segments:
            continue
        segment_counts[segments[0]] += 1

    if not segment_counts:
        return f"a[href*='{host}']"
    top_segment, _count = segment_counts.most_common(1)[0]
    return f"a[href*='/{top_segment}/']"


def _guess_table_headers(soup: BeautifulSoup) -> list[str]:
    """最初に見つかったテーブルのヘッダ行文字列を返す (見つからなければ空リスト)"""
    table = soup.find("table")
    if not isinstance(table, Tag):
        return []
    header_row = None
    thead = table.find("thead")
    if isinstance(thead, Tag):
        header_row = thead.find("tr")
    if header_row is None:
        for tr in table.find_all("tr"):
            if isinstance(tr, Tag) and tr.find("th") is not None:
                header_row = tr
                break
    if not isinstance(header_row, Tag):
        return []
    return [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]


def build_spec_dict(names: list[str], list_url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    headers = _guess_table_headers(soup)

    if headers:
        return {
            "names": names,
            "mode": "table_horizontal",
            "row_selector": "table tr",
            "skip_first_row": True,
            "header_fields": {h: "TODO_FIELD_NAME" for h in headers if h},
        }

    list_link_selector = _guess_list_link_selector(soup, list_url)
    return {
        "names": names,
        "mode": "list_detail",
        "list_link_selector": list_link_selector,
        "image_selector": "img",
        "field_selectors": {
            "species": {"label": "種類"},
            "sex": {"label": "性別"},
            "age": {"label": "年齢"},
            "color": {"label": "毛色"},
            "size": {"label": "体格"},
            "shelter_date": {"label": "収容日"},
            "location": {"label": "収容場所"},
            "phone": {"label": "連絡先"},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="spec ファイル名 (config/site_specs/<slug>.yaml)")
    parser.add_argument("list_url", help="一覧ページ URL")
    parser.add_argument(
        "--name", action="append", required=True, dest="names", help="sites.yaml の name (複数可)"
    )
    parser.add_argument(
        "--out-dir", type=Path, default=_SPEC_DIR, help="出力先ディレクトリ (テスト用)"
    )
    args = parser.parse_args()

    resp = requests.get(args.list_url, headers={"User-Agent": _USER_AGENT}, timeout=30)
    resp.raise_for_status()

    spec = build_spec_dict(args.names, args.list_url, resp.text)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.slug}.yaml"
    if out_path.exists():
        print(f"既に存在します (上書きしません): {out_path}", file=sys.stderr)
        return 1

    header = (
        f"# {args.names[0]} — scripts/new_site_spec.py で自動生成した雛形。\n"
        "# 必ず実ページを見て list_link_selector / field_selectors / header_fields を\n"
        "# 手直しすること (自動生成のまま使わない)。\n"
    )
    with out_path.open("w", encoding="utf-8") as f:
        f.write(header)
        yaml.safe_dump(spec, f, allow_unicode=True, sort_keys=False)

    print(f"生成しました: {out_path}")
    print("次の手順:")
    print("  1. 実ページを見て selector / label を確認・修正する")
    print("  2. sites.yaml に該当エントリを追加する (fields/phone/requires_js 等)")
    print("  3. tests/adapters/rule_based/sites/test_<slug>.py を書く")
    return 0


if __name__ == "__main__":
    sys.exit(main())
