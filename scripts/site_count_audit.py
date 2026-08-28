"""実サイトの掲載数と oneco 公開数を adapter を経由せず突き合わせる (W001/T046)。

full_publication_audit.py は adapter の出力と API を比較するため、adapter 自体が
系統的に取り漏らすケース (熊本のページ送り・さぬきの PDF 行潰れ型) を検出できない。
このスクリプトは一覧ページを直接 fetch し、adapter とは独立なシグナルで
「実サイトに載っている数」を見積もって API 公開数と比較する。

サイトごとの独立シグナル:
    pattern_count   : sites.yaml の list_link_pattern / pdf_link_pattern を一覧ページに
                      適用した際の一意リンク数 (詳細ページ型サイトの実掲載数に相当)
    pagination      : 「次へ」rel=next 等の次ページリンクの有無 (単一ページ取得の
                      adapter が2ページ目以降を取り漏らす熊本型の穴の候補)
    zero_canary     : 「現在収容している犬はいません」等の明示的ゼロ表現
    generic signals : 同一ホスト画像数・最大テーブル行数 (single_page 型の目視補助)

比較はホスト単位で行う。同一ホストに複数サイト (山梨4面など) がある場合に
API 個体をサイトへ誤帰属させないため、ホスト内の合算で突き合わせる。

判定フラグ:
    pagination_detected : 次ページリンクがある (adapter が辿っているかは個別確認)
    undercount_suspect  : pattern 合計 > API 公開数 (掲載漏れ疑い)
    overcount_suspect   : pattern 合計 < API 公開数 (もういない子の残骸疑い)
    zero_suspect        : API 0 件なのにゼロ表現が無く掲載候補シグナルがある

undercount / overcount は当日の掲載入れ替わりを含むため、単日の結果だけで
確定させず、夜間収集後に再実行して残ったものを確定とする。

使い方:
    python3 scripts/site_count_audit.py                  # 全サイト
    python3 scripts/site_count_audit.py --sites "熊本県動物愛護センター（犬）"
    python3 scripts/site_count_audit.py --limit 20

出力 (既定 reports/):
    site_count_audit_YYYYMMDD.json / .md

通知 (T105):
    undercount_suspect / overcount_suspect / zero_suspect のいずれかが立った
    ホストがあれば DISCORD_WEBHOOK_URL (環境変数, GitHub Actions secret) 宛に
    Discord 通知する (data_collector.infrastructure.count_audit_notify)。
    pagination_detected はそれ単体では通知対象にしない (件数比較と無関係な情報フラグのため)。
    未設定なら通知は no-op でスキップされる (.github/workflows/weekly-count-audit.yml が週次実行)。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from data_collector.infrastructure.count_audit_notify import maybe_notify
from data_collector.infrastructure.notification_client import NotificationClient

ROOT = Path(__file__).resolve().parent.parent

# ゼロ表現キャナリーは zero_count_audit.py と共通 (scripts/ が sys.path に載る前提)
sys.path.insert(0, str(Path(__file__).resolve().parent))
from zero_count_audit import ZERO_REGEX  # noqa: E402

DEFAULT_API_BASE = "https://oneco-api-tvlsrcvyuq-an.a.run.app"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) oneco-count-audit/1.0"
TIMEOUT = 25

# 次ページ検出。llm/adapter.py の _find_next_page と同じ語彙に加え、
# href のクエリ/パスに 2 ページ目を示すものがあるかも見る。
NEXT_TEXTS = ["次へ", "次のページ", "次の", "Next", "next", ">>", "›", "»"]
NEXT_HREF_RE = re.compile(
    r"([?&](page|paged|p|pageno|page_no|pn)=([2-9]|[1-9]\d))|(/page/([2-9]|[1-9]\d)([/?#]|$))"
)

# 装飾・部品画像を候補から除くための名前パターン
NOISE_IMG_RE = re.compile(
    r"(icon|logo|banner|btn|button|arrow|spacer|header|footer|nav|bullet|line|"
    r"title|top|bg_|_bg|common|parts|menu|mark|qr)",
    re.IGNORECASE,
)


def load_sites_yaml() -> list[dict[str, Any]]:
    cfg = yaml.safe_load(open(ROOT / "src/data_collector/config/sites.yaml"))
    return cfg["sites"]


def get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def fetch_api_animals(api_base: str, limit: int = 100) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = get_json(f"{api_base.rstrip('/')}/animals?limit={limit}&offset={offset}")
        got = page.get("items") or []
        items.extend(got)
        if not page.get("meta", {}).get("has_next") or not got:
            break
        offset += len(got)
    return items


def host_of(url: str) -> str:
    return urlparse(url).hostname or ""


def detect_pagination(soup: BeautifulSoup, page_url: str) -> list[str]:
    """次ページリンク候補を返す (空なら未検出)。"""
    hits: list[str] = []

    def push(a: Any, why: str) -> None:
        href = a.get("href") if a else None
        if not href or href.startswith(("javascript:", "#")):
            return
        absolute = urljoin(page_url, href)
        if absolute.split("#")[0] == page_url.split("#", maxsplit=1)[0]:
            return
        entry = f"{why}: {absolute}"
        if entry not in hits:
            hits.append(entry)

    for text in NEXT_TEXTS:
        for a in soup.find_all("a", string=lambda s, t=text: bool(s) and t in s):
            push(a, f"text[{text}]")
    for attr in ["next", "pagination-next"]:
        push(soup.find("a", class_=attr), f"class[{attr}]")
        push(soup.find("a", rel=attr), f"rel[{attr}]")
    for a in soup.find_all("a", href=NEXT_HREF_RE):
        push(a, "href[page=2+]")
    return hits


def count_pattern_links(soup: BeautifulSoup, page_url: str, selector: str) -> int:
    urls: set[str] = set()
    try:
        tags = soup.select(selector)
    except Exception:
        return -1
    for a in tags:
        href = a.get("href")
        if href:
            urls.add(urljoin(page_url, href))
    return len(urls)


def generic_signals(soup: BeautifulSoup, page_url: str) -> dict[str, int]:
    page_host = host_of(page_url)
    img_count = 0
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(page_url, src)
        if host_of(absolute) != page_host:
            continue
        if NOISE_IMG_RE.search(absolute):
            continue
        img_count += 1

    max_rows = 0
    for table in soup.find_all("table"):
        rows = len(table.find_all("tr"))
        max_rows = max(max_rows, rows - 1 if rows else 0)

    text = soup.get_text()
    number_hits = len(re.findall(r"(管理|収容|個体)番号", text))
    return {"same_host_imgs": img_count, "max_table_rows": max_rows, "number_hits": number_hits}


def audit_site(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": raw["name"],
        "list_url": raw["list_url"],
        "host": host_of(raw["list_url"]),
        "category": raw.get("category"),
        "single_page": bool(raw.get("single_page")),
        "selector": raw.get("list_link_pattern") or raw.get("pdf_link_pattern"),
        "is_pdf_selector": bool(raw.get("pdf_link_pattern")),
    }
    if raw.get("requires_js"):
        out["status"] = "skipped_js"
        return out

    try:
        res = requests.get(raw["list_url"], headers={"User-Agent": UA}, timeout=TIMEOUT)
    except requests.RequestException as e:
        out["status"] = f"error:{type(e).__name__}"
        return out
    if res.status_code != 200:
        out["status"] = f"http_{res.status_code}"
        return out

    soup = BeautifulSoup(res.content, "html.parser")
    out["status"] = "ok"
    out["pagination"] = detect_pagination(soup, raw["list_url"])
    out["zero_canary"] = bool(ZERO_REGEX.search(soup.get_text()))
    out.update(generic_signals(soup, raw["list_url"]))
    if out["selector"]:
        out["pattern_count"] = count_pattern_links(soup, raw["list_url"], out["selector"])
    return out


def group_and_flag(
    site_results: list[dict[str, Any]], api_animals: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    api_by_host: dict[str, int] = {}
    for an in api_animals:
        api_by_host[host_of(an["source_url"])] = api_by_host.get(host_of(an["source_url"]), 0) + 1

    by_host: dict[str, list[dict[str, Any]]] = {}
    for r in site_results:
        by_host.setdefault(r["host"], []).append(r)

    groups: list[dict[str, Any]] = []
    for host, rows in by_host.items():
        api_count = api_by_host.get(host, 0)
        fetched = [r for r in rows if r["status"] == "ok"]
        with_pattern = [r for r in fetched if r.get("pattern_count", -1) >= 0]
        # PDF セレクタはリンク先 PDF 内の頭数を数えられないため、掲載数比較には使わない
        comparable = (
            len(with_pattern) == len(rows)
            and len(rows) > 0
            and not any(r["is_pdf_selector"] for r in rows)
        )
        pattern_total = sum(r["pattern_count"] for r in with_pattern) if with_pattern else None

        flags: list[str] = []
        if any(r.get("pagination") for r in fetched):
            flags.append("pagination_detected")
        if comparable and pattern_total is not None:
            if pattern_total > api_count:
                flags.append("undercount_suspect")
            elif pattern_total < api_count:
                flags.append("overcount_suspect")
        if api_count == 0 and fetched and not any(r.get("zero_canary") for r in fetched):
            has_signal = any(
                (r.get("pattern_count") or 0) > 0
                or r.get("number_hits", 0) >= 2
                or r.get("max_table_rows", 0) >= 2
                for r in fetched
            )
            if has_signal:
                flags.append("zero_suspect")

        groups.append(
            {
                "host": host,
                "sites": [r["name"] for r in rows],
                "api_count": api_count,
                "pattern_total": pattern_total,
                "comparable": comparable,
                "statuses": sorted({r["status"] for r in rows}),
                "flags": flags,
            }
        )
    groups.sort(key=lambda g: (not g["flags"], g["host"]))
    return groups


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    groups = result["groups"]
    flagged = [g for g in groups if g["flags"]]
    lines.append(f"# 実サイト掲載数 突き合わせ監査 (T046) {result['generated_at']}")
    lines.append("")
    lines.append(f"- API 公開中: {result['api_total']} 件")
    lines.append(f"- 対象サイト: {result['site_total']} (JS スキップ {result['js_skipped']})")
    lines.append(f"- ホストグループ: {len(groups)} / フラグあり: **{len(flagged)}**")
    lines.append("")
    lines.append("undercount / overcount は当日の掲載入れ替わりを含むため、")
    lines.append("夜間収集後の再実行で残ったものだけを確定とする。")
    lines.append("")

    lines.append("## フラグ付きホスト")
    lines.append("")
    lines.append("| ホスト | サイト | API | pattern | フラグ |")
    lines.append("| --- | --- | ---: | ---: | --- |")
    for g in flagged:
        pt = g["pattern_total"] if g["pattern_total"] is not None else "-"
        if not g["comparable"]:
            pt = f"({pt})"
        lines.append(
            f"| {g['host']} | {'<br>'.join(g['sites'])} | {g['api_count']} | {pt} "
            f"| {', '.join(g['flags'])} |"
        )
    if not flagged:
        lines.append("(なし)")
    lines.append("")

    lines.append("## ページネーション検出の内訳")
    lines.append("")
    for r in result["site_results"]:
        if r.get("pagination"):
            lines.append(f"- **{r['name']}** ({r['list_url']})")
            for hit in r["pagination"][:5]:
                lines.append(f"  - {hit}")
    lines.append("")

    lines.append("## サイト別詳細")
    lines.append("")
    lines.append("| サイト | 状態 | pattern | ゼロ表現 | 画像 | 表行 | 番号 | 次頁 |")
    lines.append("| --- | --- | ---: | :-: | ---: | ---: | ---: | :-: |")
    for r in result["site_results"]:
        lines.append(
            f"| {r['name']} | {r['status']} | {r.get('pattern_count', '-')} "
            f"| {'Y' if r.get('zero_canary') else ''} | {r.get('same_host_imgs', '-')} "
            f"| {r.get('max_table_rows', '-')} | {r.get('number_hits', '-')} "
            f"| {'Y' if r.get('pagination') else ''} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--sites", help="カンマ区切りのサイト名で絞り込み")
    parser.add_argument("--limit", type=int, help="先頭 N サイトのみ")
    parser.add_argument("--out-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    sites = load_sites_yaml()
    if args.sites:
        wanted = {s.strip() for s in args.sites.split(",")}
        sites = [s for s in sites if s["name"] in wanted]
    if args.limit:
        sites = sites[: args.limit]

    print(f"[count-audit] 対象 {len(sites)} サイト", file=sys.stderr)
    api_animals = fetch_api_animals(args.api_base)
    print(f"[count-audit] API 公開中 {len(api_animals)} 件", file=sys.stderr)

    # 同一ホストへ連続アクセスしないよう待ち時間を入れる
    site_results: list[dict[str, Any]] = []
    last_host: str | None = None
    for i, raw in enumerate(sites, 1):
        host = host_of(raw["list_url"])
        if not raw.get("requires_js") and site_results:
            time.sleep(1.5 if host == last_host else 0.5)
        r = audit_site(raw)
        last_host = host
        mark = {"ok": "✓", "skipped_js": "⏭"}.get(r["status"], "✗")
        print(
            f"  [{i}/{len(sites)}] {mark} {r['name'][:40]:40s} "
            f"pattern={r.get('pattern_count', '-')} 次頁={'Y' if r.get('pagination') else '-'} "
            f"zero={'Y' if r.get('zero_canary') else '-'}",
            file=sys.stderr,
        )
        site_results.append(r)

    groups = group_and_flag(site_results, api_animals)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "api_total": len(api_animals),
        "site_total": len(sites),
        "js_skipped": sum(1 for r in site_results if r["status"] == "skipped_js"),
        "site_results": site_results,
        "groups": groups,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    json_path = out_dir / f"site_count_audit_{stamp}.json"
    md_path = out_dir / f"site_count_audit_{stamp}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    write_markdown(result, md_path)
    print(f"[count-audit] 出力: {json_path} / {md_path}", file=sys.stderr)

    # 乖離 (undercount/overcount/zero_suspect) があれば Discord 通知 (T105)。
    # DISCORD_WEBHOOK_URL 未設定時は NotificationClient が no-op でログ警告のみ
    # (ローカル ad hoc 実行では通常未設定なので安全にスキップされる)。
    notify_config: dict[str, str] = {}
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_webhook:
        notify_config["discord_webhook_url"] = discord_webhook
    notified = maybe_notify(result, NotificationClient(notify_config))
    print(
        f"[count-audit] Discord 通知: {'送信' if notified else '乖離なし/対象外'}", file=sys.stderr
    )


if __name__ == "__main__":
    main()
