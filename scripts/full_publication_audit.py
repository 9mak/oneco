"""公開中の全動物を実サイトと機械照合する全数監査 (W001/T045・T046)。

50件サンプリング (publication_audit.py) を全数へ拡張したもの。sites.yaml の全サイトに
対して adapter を実 HTTP で実行し、normalize まで通した結果を公開 API の全件と
source_url で突き合わせる。判定対象は致命 8 フィールド:

    status / phone / source_url / location / prefecture / category / species / image_urls

比較の3方向:
    field_mismatch : source_url が一致した個体で、致命フィールドの値が食い違う
    api_only       : API にいるが実サイトから取れない (もういない子の疑い)
    adapter_only   : 実サイトにいるが API にいない (掲載漏れの疑い)

api_only / adapter_only は「本日の掲載入れ替わり」でも発生するため、直後の夜間収集の
翌朝に --recheck で再照合して残ったものだけを確定とする。

requires_js のサイトは adapter が実行できないため監査対象外 (T009 の Playwright 監査で
別途扱う)。それらのサイトに属する API 個体は api_only とせず js_unaudited に分類する。

使い方:
    python3 scripts/full_publication_audit.py                     # 全サイト実行
    python3 scripts/full_publication_audit.py --sites "山梨県（探している犬）"
    python3 scripts/full_publication_audit.py --recheck reports/full_audit_YYYYMMDD.json

出力 (既定 reports/):
    full_audit_YYYYMMDD.json   全比較結果 (機械可読・再照合の入力)
    full_audit_YYYYMMDD.md     サイト別サマリと不一致の一覧 (人が読む)
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
import time
import traceback
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

import data_collector.adapters.rule_based.sites as _sites_pkg  # noqa: E402

for _, _name, _ in pkgutil.iter_modules(_sites_pkg.__path__):
    try:
        importlib.import_module(f"data_collector.adapters.rule_based.sites.{_name}")
    except Exception:
        pass

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry  # noqa: E402
from data_collector.llm.config import SiteConfig  # noqa: E402

DEFAULT_API_BASE = "https://oneco-api-tvlsrcvyuq-an.a.run.app"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) oneco-full-audit/1.0"

# 致命 8 フィールドのうち source_url は突き合わせキーそのもののため、
# 値比較の対象は残り 7 フィールド。
COMPARE_FIELDS = [
    "status",
    "phone",
    "location",
    "prefecture",
    "category",
    "species",
    "image_urls",
]


def load_sites_yaml() -> list[dict[str, Any]]:
    cfg = yaml.safe_load(open(ROOT / "src/data_collector/config/sites.yaml"))
    return cfg["sites"]


def build_site_config(raw: dict[str, Any]) -> SiteConfig:
    return SiteConfig(
        name=raw["name"],
        prefecture=raw.get("prefecture", ""),
        prefecture_code=raw.get("prefecture_code", "00"),
        list_url=raw["list_url"],
        category=raw.get("category", "adoption"),
        requires_js=raw.get("requires_js", False),
        single_page=raw.get("single_page", False),
        list_link_pattern=raw.get("list_link_pattern"),
        pdf_link_pattern=raw.get("pdf_link_pattern"),
        pdf_multi_animal=raw.get("pdf_multi_animal", False),
        timeout_sec=raw.get("timeout_sec"),
        fallback_to_llm=raw.get("fallback_to_llm", False),
    )


def get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def fetch_api_animals(api_base: str, limit: int = 100) -> list[dict[str, Any]]:
    """公開 API から全件をページングして取得する。"""
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


def normalize_value(field: str, value: Any) -> Any:
    """比較前の正規化。表記ゆれで誤検出しないための最小限に留める。"""
    if field == "image_urls":
        return sorted(str(u) for u in (value or []))
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def collect_site(raw_cfg: dict[str, Any]) -> dict[str, Any]:
    """1サイトの adapter を実 HTTP で実行し normalize 済み個体を返す。"""
    name = raw_cfg["name"]
    out: dict[str, Any] = {"name": name, "list_url": raw_cfg["list_url"], "animals": []}
    started = time.monotonic()

    adapter_cls = SiteAdapterRegistry.get(name)
    if adapter_cls is None:
        out["status"] = "no_adapter"
        return out
    if raw_cfg.get("requires_js"):
        out["status"] = "skipped_js"
        return out

    try:
        adapter = adapter_cls(build_site_config(raw_cfg))
        urls = adapter.fetch_animal_list()
    except Exception as e:
        out["status"] = "list_error"
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return out

    if not urls:
        out["status"] = "list_empty"
        out["elapsed_sec"] = round(time.monotonic() - started, 1)
        return out

    detail_errors: list[dict[str, str]] = []
    for detail_url, category in urls:
        try:
            raw = adapter.extract_animal_details(detail_url, category)
            # 本番の保存経路 (collector_service.py) と同じく adapter.normalize を
            # 通す。DataNormalizer を直接呼ぶと高知県等のサイト固有オーバーライド
            # (location フォールバック・テンプレート画像除外) がバイパスされ、
            # 監査側の偽陽性になる (review-20260814 F-01)
            an = adapter.normalize(raw)
            out["animals"].append(
                {
                    "source_url": str(an.source_url),
                    "status": str(an.status.value) if an.status else None,
                    "phone": an.phone,
                    "location": an.location,
                    # normalize は source_url から都道府県を推定し、取れないサイトは
                    # pipeline 側で site_config.prefecture にフォールバックする
                    # (commit e3d7166)。比較器も同じフォールバックを適用する。
                    "prefecture": an.prefecture or raw_cfg.get("prefecture") or None,
                    "category": an.category,
                    "species": an.species,
                    "image_urls": [str(u) for u in an.image_urls],
                }
            )
        except Exception as e:
            detail_errors.append(
                {"url": str(detail_url), "error": f"{type(e).__name__}: {str(e)[:200]}"}
            )

    out["status"] = "ok" if not detail_errors else "partial"
    out["detail_errors"] = detail_errors
    out["elapsed_sec"] = round(time.monotonic() - started, 1)
    return out


def diff_animal(adapter_animal: dict[str, Any], api_animal: dict[str, Any]) -> list[dict[str, Any]]:
    """致命フィールドの食い違いを返す。空リストなら一致。"""
    diffs: list[dict[str, Any]] = []
    for field in COMPARE_FIELDS:
        a = normalize_value(field, adapter_animal.get(field))
        b = normalize_value(field, api_animal.get(field))
        if field == "status" and a is None:
            # adapter 段は status を持たず、DB 投入時に既定 'sheltered' が付く
            # (database/models.py の default)。None vs 'sheltered' は設計どおり。
            a = "sheltered"
        if a != b:
            diffs.append({"field": field, "site": a, "api": b})
    return diffs


def attribute_host(url: str) -> str:
    return urlparse(url).hostname or ""


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    sites = load_sites_yaml()
    if args.sites:
        wanted = {s.strip() for s in args.sites.split(",")}
        sites = [s for s in sites if s["name"] in wanted]

    print(f"[audit] 対象 {len(sites)} サイト / API: {args.api_base}", file=sys.stderr)
    api_animals = fetch_api_animals(args.api_base)
    print(f"[audit] API 公開中 {len(api_animals)} 件", file=sys.stderr)

    api_by_url = {a["source_url"]: a for a in api_animals}
    js_hosts = {attribute_host(s["list_url"]) for s in load_sites_yaml() if s.get("requires_js")}

    site_results: list[dict[str, Any]] = []
    matched_urls: set[str] = set()
    for i, raw_cfg in enumerate(sites, 1):
        r = collect_site(raw_cfg)
        r["mismatches"] = []
        r["adapter_only"] = []
        for an in r.get("animals", []):
            api_an = api_by_url.get(an["source_url"])
            if api_an is None:
                r["adapter_only"].append(an["source_url"])
                continue
            matched_urls.add(an["source_url"])
            diffs = diff_animal(an, api_an)
            if diffs:
                r["mismatches"].append({"source_url": an["source_url"], "diffs": diffs})
        n_animals = len(r.get("animals", []))
        marker = {"ok": "✓", "partial": "△", "list_empty": "○", "skipped_js": "⏭"}.get(
            r["status"], "✗"
        )
        print(
            f"  [{i}/{len(sites)}] {marker} {r['name'][:40]:40s} "
            f"{n_animals:3d}件 不一致{len(r['mismatches']):3d} "
            f"漏れ疑い{len(r['adapter_only']):3d} {r.get('error', '')}",
            file=sys.stderr,
        )
        site_results.append(r)
        # 実行が途中で殺されても再開・分析できるよう、20サイトごとに途中結果を残す
        if i % 20 == 0 and args.partial_path:
            Path(args.partial_path).write_text(
                json.dumps({"site_results": site_results}, ensure_ascii=False),
                encoding="utf-8",
            )

    # API にいるが今回どのサイトからも取れなかった個体
    api_only: list[dict[str, Any]] = []
    js_unaudited: list[str] = []
    audited_all = args.sites is None  # サイト絞り込み時は api_only 判定をしない
    if audited_all:
        for url, an in api_by_url.items():
            if url in matched_urls:
                continue
            if attribute_host(url) in js_hosts:
                js_unaudited.append(url)
            else:
                api_only.append(
                    {"source_url": url, "id": an.get("id"), "species": an.get("species")}
                )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "api_total": len(api_animals),
        "site_results": site_results,
        "api_only": api_only,
        "js_unaudited": js_unaudited,
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    sr = result["site_results"]
    total_mismatch = sum(len(r["mismatches"]) for r in sr)
    total_adapter_only = sum(len(r["adapter_only"]) for r in sr)
    total_animals = sum(len(r.get("animals", [])) for r in sr)
    by_status: dict[str, int] = {}
    for r in sr:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1

    lines.append(f"# 全数監査結果 {result['generated_at']}")
    lines.append("")
    lines.append(f"- API 公開中: {result['api_total']} 件")
    lines.append(f"- adapter 取得: {total_animals} 件 ({len(sr)} サイト)")
    lines.append(f"- サイト状態: {json.dumps(by_status, ensure_ascii=False)}")
    lines.append(f"- 致命フィールド不一致: **{total_mismatch} 件**")
    lines.append(f"- 掲載漏れ疑い (adapter_only): **{total_adapter_only} 件**")
    lines.append(f"- もういない疑い (api_only): **{len(result['api_only'])} 件**")
    lines.append(f"- JS サイトのため未監査: {len(result['js_unaudited'])} 件")
    lines.append("")
    lines.append("api_only / adapter_only は当日の掲載入れ替わりを含むため、")
    lines.append("夜間収集後の再照合 (--recheck) で残ったものだけを確定とする。")
    lines.append("")

    lines.append("## 致命フィールド不一致")
    lines.append("")
    for r in sr:
        for m in r["mismatches"]:
            lines.append(f"### {r['name']}")
            lines.append(f"- {m['source_url']}")
            for d in m["diffs"]:
                lines.append(f"  - `{d['field']}`: サイト `{d['site']}` / API `{d['api']}`")
    if total_mismatch == 0:
        lines.append("(なし)")
    lines.append("")

    lines.append("## サイト別サマリ")
    lines.append("")
    lines.append("| サイト | 状態 | 取得 | 不一致 | 漏れ疑い | 所要秒 |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    for r in sorted(sr, key=lambda x: (-len(x["mismatches"]), -len(x["adapter_only"]))):
        lines.append(
            f"| {r['name']} | {r['status']} | {len(r.get('animals', []))} "
            f"| {len(r['mismatches'])} | {len(r['adapter_only'])} "
            f"| {r.get('elapsed_sec', '')} |"
        )
    lines.append("")

    if result["api_only"]:
        lines.append("## もういない疑い (api_only)")
        lines.append("")
        for a in result["api_only"]:
            lines.append(f"- id={a['id']} {a['species']} {a['source_url']}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def run_recheck(args: argparse.Namespace) -> int:
    """前回結果の api_only / adapter_only を最新 API と再照合し、残存だけを出す。"""
    prev = json.loads(Path(args.recheck).read_text(encoding="utf-8"))
    api_animals = fetch_api_animals(args.api_base)
    api_urls = {a["source_url"] for a in api_animals}

    remaining_api_only = [a for a in prev["api_only"] if a["source_url"] in api_urls]
    resolved_adapter_only: dict[str, list[str]] = {}
    remaining_adapter_only: dict[str, list[str]] = {}
    for r in prev["site_results"]:
        res = [u for u in r["adapter_only"] if u in api_urls]
        rem = [u for u in r["adapter_only"] if u not in api_urls]
        if res:
            resolved_adapter_only[r["name"]] = res
        if rem:
            remaining_adapter_only[r["name"]] = rem

    print(f"api_only 残存: {len(remaining_api_only)} / {len(prev['api_only'])}")
    for a in remaining_api_only:
        print(f"  - id={a['id']} {a['source_url']}")
    print(f"adapter_only 解消サイト: {len(resolved_adapter_only)}")
    print(f"adapter_only 残存サイト: {len(remaining_adapter_only)}")
    for name, urls in remaining_adapter_only.items():
        print(f"  - {name}: {len(urls)} 件")
        for u in urls[:5]:
            print(f"      {u}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--sites", help="comma-separated site names (デバッグ用)")
    parser.add_argument("--out-dir", default=str(ROOT / "reports"))
    parser.add_argument("--recheck", help="前回の full_audit JSON を最新 API と再照合する")
    parser.add_argument("--partial-path", dest="partial_path", help="途中結果の逐次書き出し先")
    args = parser.parse_args()

    if args.recheck:
        return run_recheck(args)

    try:
        result = run_audit(args)
    except Exception:
        traceback.print_exc()
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    json_path = out_dir / f"full_audit_{stamp}.json"
    md_path = out_dir / f"full_audit_{stamp}.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_markdown(result, md_path)
    print(f"\n[audit] 出力: {json_path}\n[audit] 出力: {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
