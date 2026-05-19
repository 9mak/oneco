"""0 件抽出サイトの自動振り分けスクリプト

最新 workflow で「rule-based 収集完了: 0件」だったサイトを HTTP fetch し、
HTML 中のキャナリー (ゼロ表現 / 動物コンテンツ候補) で 3 分類する:

  - true_zero   : 「該当なし」「現在いません」等の明示的ゼロ表現あり (正常)
  - suspicious  : ゼロ表現なし、かつ動物コンテンツ候補多数 (adapter 不具合疑い)
  - maybe_zero  : ゼロ表現も無く、コンテンツ候補も少ない (要手動確認)
  - unreachable : 404 / timeout / ネットワークエラー
  - skipped_js  : requires_js: true のサイト (Playwright 未対応 — 別途調査)

使い方:
    python3 scripts/zero_count_audit.py            # /tmp/zero_sites.json を読む
    python3 scripts/zero_count_audit.py --input X  # 任意のサイトリスト JSON
    python3 scripts/zero_count_audit.py --limit 20 # 先頭 N 件だけ走らせる

出力:
    reports/zero_audit_YYYYMMDD.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) oneco-zero-audit/1.0"
TIMEOUT = 20

ZERO_PATTERNS = [
    r"現在[^。]{0,20}(収容|登録|保護)[^。]{0,20}(無|なし|いません|ありません|0\s*[頭匹件])",
    r"該当[^。]{0,15}(無|なし|ありません|データはありません)",
    r"(犬|猫|動物|該当する|お知らせするもの)[^。]{0,15}(はいません|はありません|ございません)",
    r"(保護|収容|譲渡|登録)[^。]{0,20}(犬|猫|動物)?[^。]{0,10}(0\s*[頭匹件]|無し|なし)",
    r"現在[^。]{0,15}(掲載|公開)[^。]{0,15}(無|なし|ありません)",
    r"情報は[^。]{0,10}ありません",
    r"見つかりませんでした",
]
ZERO_REGEX = re.compile("|".join(ZERO_PATTERNS))

# 動物コンテンツ候補シグナル
ANIMAL_IMG_ALT = re.compile(r"(犬|猫|オス|メス|♂|♀|保護犬|保護猫|収容|譲渡|迷子)")
# detail-page を表す部分文字列 (list / search / static は除外)
DETAIL_LINK = re.compile(
    r"(detail|/animal/|/animals/|/inu/|/neko/|/dog/|/cat/|/stray/|/hogo/|"
    r"/jyoto/|/jouto/|/info\d|infoid=)",
    re.I,
)
# サイト共通要素 (ナビ・ヘッダ・フッタ・サイドバー) を除去するための selector 群
NOISE_SELECTORS = [
    "header", "footer", "nav", "aside", "script", "style", "noscript",
    "[role=navigation]", "[role=banner]", "[role=contentinfo]",
    ".header", ".footer", ".nav", ".menu", ".sidebar", ".breadcrumb",
    ".gnav", ".global-nav", ".side-menu", ".pankuzu",
    "#header", "#footer", "#nav", "#sidebar", "#menu", "#breadcrumb",
]
# 「該当なし」を含むテーブル行はカウントから除外
EMPTY_ROW_HINT = re.compile(r"(該当.{0,10}(なし|ありません)|現在.{0,10}(いません|ありません)|お知らせ)")

Category = Literal["true_zero", "suspicious", "maybe_zero", "unreachable", "skipped_js"]


@dataclass
class AuditResult:
    name: str
    list_url: str
    prefecture: str | None
    category: Category
    http_status: int | None = None
    reason: str = ""
    signals: dict[str, int] = field(default_factory=dict)


def fetch(url: str, retries: int = 2) -> tuple[int | None, str]:
    """HTML を取得して (status, body) を返す。失敗時は (None, error_message)。
    タイムアウト/接続エラーは指数バックオフで retry。"""
    import time
    last_err = ""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url, timeout=TIMEOUT, headers={"User-Agent": UA}, allow_redirects=True
            )
            return resp.status_code, resp.text
        except requests.RequestException as e:
            last_err = str(e)
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    return None, last_err


def analyze(html: str, list_url: str) -> tuple[bool, dict[str, int]]:
    """HTML を解析し (zero_phrase_found, signals) を返す

    ノイズ除去:
      - ヘッダ/フッタ/ナビ/サイドバー要素を destruct してから測る
      - detail_link は list_url と同一ドメインかつ list_url のパスを共有するもののみ
      - table 行は「該当なし」表現を含む行を除外
    """
    soup = BeautifulSoup(html, "html.parser")
    # ゼロ表現は全テキストから検出（フッタの注意書き等にあっても拾う）
    full_text = soup.get_text(" ", strip=True)
    zero_found = bool(ZERO_REGEX.search(full_text))

    # ノイズ要素を除去
    for sel in NOISE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()

    list_parsed = urlparse(list_url)
    list_host = list_parsed.netloc
    list_path_prefix = list_parsed.path.rsplit("/", 1)[0] or "/"

    imgs = soup.select("img")
    animal_imgs = [
        i for i in imgs if ANIMAL_IMG_ALT.search(i.get("alt", "") or i.get("title", ""))
    ]

    detail_links = []
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not DETAIL_LINK.search(href):
            continue
        # list_url と同一ドメイン or 相対 URL のみカウント
        absolute = urljoin(list_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc and parsed.netloc != list_host:
            continue
        # list_url のパス階層を共有しないリンクは別セクション扱いで除外
        if parsed.path and not parsed.path.startswith(list_path_prefix):
            continue
        detail_links.append(a)

    # 該当なし行を除外
    table_rows = [
        tr for tr in soup.select("table tr") if not EMPTY_ROW_HINT.search(tr.get_text())
    ]
    pdf_links = soup.select('a[href$=".pdf"]')

    return zero_found, {
        "imgs": len(imgs),
        "animal_alt_imgs": len(animal_imgs),
        "detail_links": len(detail_links),
        "table_rows": len(table_rows),
        "pdf_links": len(pdf_links),
        "text_len": len(full_text),
    }


def classify(zero_found: bool, signals: dict[str, int]) -> tuple[Category, str]:
    # 動物 alt の img はゼロ表現があっても優先（「現在いません」と書いてあるが動物画像が
    # 並んでいる = ページの一部分にだけゼロ表現がある場合）
    if signals["animal_alt_imgs"] >= 3:
        return "suspicious", f"動物 alt の img が {signals['animal_alt_imgs']} 件ある"

    if zero_found:
        return "true_zero", "明示的ゼロ表現あり"

    # ノイズ除去後の detail link / table 行 / PDF が多ければ疑わしい
    if signals["detail_links"] >= 5:
        return "suspicious", f"detail 系リンクが {signals['detail_links']} 件ある"
    if signals["table_rows"] >= 8:
        return "suspicious", f"非空 table 行が {signals['table_rows']} 行ある"
    if signals["pdf_links"] >= 2:
        return "suspicious", f"PDF リンクが {signals['pdf_links']} 件ある"

    return "maybe_zero", "ゼロ表現もコンテンツ候補も少ない"


def audit_one(site: dict) -> AuditResult:
    name = site["name"]
    url = site["list_url"]
    pref = site.get("prefecture")

    if site.get("requires_js"):
        return AuditResult(
            name=name, list_url=url, prefecture=pref,
            category="skipped_js", reason="requires_js: true (Playwright 必要)",
        )

    status, body = fetch(url)
    if status is None:
        return AuditResult(
            name=name, list_url=url, prefecture=pref,
            category="unreachable", reason=f"fetch error: {body[:80]}",
        )
    if status >= 400:
        return AuditResult(
            name=name, list_url=url, prefecture=pref,
            category="unreachable", http_status=status, reason=f"HTTP {status}",
        )

    zero_found, signals = analyze(body, url)
    cat, reason = classify(zero_found, signals)
    return AuditResult(
        name=name, list_url=url, prefecture=pref,
        category=cat, http_status=status, reason=reason, signals=signals,
    )


def render_report(results: list[AuditResult], output_path: Path) -> None:
    buckets: dict[Category, list[AuditResult]] = {
        "suspicious": [], "maybe_zero": [], "true_zero": [],
        "unreachable": [], "skipped_js": [],
    }
    for r in results:
        buckets[r.category].append(r)

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 0 件抽出サイト キャナリー監査レポート ({today})",
        "",
        f"対象サイト数: **{len(results)}**",
        "",
        "| カテゴリ | 件数 | 説明 |",
        "|---|---:|---|",
        f"| 🔴 suspicious | {len(buckets['suspicious'])} | adapter 不具合疑い・要修正調査 |",
        f"| 🟡 maybe_zero | {len(buckets['maybe_zero'])} | コンテンツ候補が少なく現状ゼロが有力だが要再確認 |",
        f"| 🟢 true_zero | {len(buckets['true_zero'])} | 明示的「ゼロ」表現あり、現状正常 |",
        f"| ⚪ unreachable | {len(buckets['unreachable'])} | 404 / timeout / 接続エラー |",
        f"| ⏭️ skipped_js | {len(buckets['skipped_js'])} | requires_js: true (Playwright 監査 TODO) |",
        "",
    ]

    section_titles = {
        "suspicious": "🔴 suspicious — adapter 修正候補（優先度高）",
        "unreachable": "⚪ unreachable — URL 失効・要対応",
        "maybe_zero": "🟡 maybe_zero — 現状ゼロが有力だが手動確認推奨",
        "true_zero": "🟢 true_zero — 現状ゼロが正常（対応不要）",
        "skipped_js": "⏭️ skipped_js — Playwright 監査が別途必要",
    }

    for cat in ("suspicious", "unreachable", "maybe_zero", "true_zero", "skipped_js"):
        rows = buckets[cat]
        if not rows:
            continue
        lines.append(f"## {section_titles[cat]} ({len(rows)} 件)")
        lines.append("")
        lines.append("| サイト | 都道府県 | 理由 | シグナル | URL |")
        lines.append("|---|---|---|---|---|")
        for r in rows:
            signals_str = ", ".join(f"{k}={v}" for k, v in r.signals.items()) if r.signals else "-"
            lines.append(
                f"| {r.name} | {r.prefecture or '-'} | {r.reason} | {signals_str} | "
                f"[link]({r.list_url}) |"
            )
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="/tmp/zero_sites.json")
    parser.add_argument("--limit", type=int, default=0, help="先頭 N 件のみ (0=全件)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--output", default=f"reports/zero_audit_{datetime.now().strftime('%Y%m%d')}.md"
    )
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    sites = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if args.limit > 0:
        sites = sites[: args.limit]

    print(f"Auditing {len(sites)} sites with {args.workers} workers...", file=sys.stderr)
    results: list[AuditResult] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit_one, s): s for s in sites}
        done = 0
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            done += 1
            marker = {
                "suspicious": "🔴", "maybe_zero": "🟡", "true_zero": "🟢",
                "unreachable": "⚪", "skipped_js": "⏭️",
            }[r.category]
            print(f"  [{done}/{len(sites)}] {marker} {r.name[:40]:40s} {r.reason}", file=sys.stderr)

    render_report(results, Path(args.output))
    print(f"\nReport saved: {args.output}", file=sys.stderr)

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON saved: {args.json_out}", file=sys.stderr)

    # 集計サマリを stdout に
    from collections import Counter
    c = Counter(r.category for r in results)
    print("\n=== summary ===", file=sys.stderr)
    for k, v in c.most_common():
        print(f"  {k}: {v}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
