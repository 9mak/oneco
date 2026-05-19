"""指定したサイト名リストに対して adapter を実 HTML で実行して結果を集計する。

使用例:
    python3 scripts/adapter_live_test.py --names "東讃保健福祉事務所（収容動物）,北九州市（保護犬）"
    python3 scripts/adapter_live_test.py --from-json /tmp/audit_full.json --category suspicious

各サイトで:
1. SiteAdapterRegistry から adapter クラスを取得
2. site_config を sites.yaml から組み立て
3. adapter.fetch_animal_list() → adapter.extract_animal_details() を実 HTTP で実行
4. 成功 / エラー / 0 件 を判定し、サマリを表示
"""

from __future__ import annotations

import argparse
import importlib
import json
import pkgutil
import sys
from pathlib import Path
from typing import Any

# プロジェクトルートを sys.path に追加
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

# 全 adapter モジュールをインポートしてレジストリ populate
import data_collector.adapters.rule_based.sites as _sites_pkg  # noqa: E402

for _, _name, _ in pkgutil.iter_modules(_sites_pkg.__path__):
    try:
        importlib.import_module(f"data_collector.adapters.rule_based.sites.{_name}")
    except Exception:
        pass

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry  # noqa: E402
from data_collector.domain.normalizer import DataNormalizer  # noqa: E402
from data_collector.llm.config import SiteConfig  # noqa: E402


def load_sites_yaml() -> dict[str, dict[str, Any]]:
    cfg = yaml.safe_load(open(ROOT / "src/data_collector/config/sites.yaml"))
    return {s["name"]: s for s in cfg["sites"]}


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


def test_site(name: str, raw_cfg: dict[str, Any], include_js: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "list_url": raw_cfg.get("list_url")}
    adapter_cls = SiteAdapterRegistry.get(name)
    if adapter_cls is None:
        result["status"] = "no_adapter"
        return result
    result["adapter"] = adapter_cls.__name__

    try:
        site_config = build_site_config(raw_cfg)
        adapter = adapter_cls(site_config)
    except Exception as e:
        result["status"] = "init_error"
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    # Playwright が必要なサイトは include_js=False ならスキップ
    if raw_cfg.get("requires_js") and not include_js:
        result["status"] = "skipped_js"
        return result

    try:
        urls = adapter.fetch_animal_list()
    except Exception as e:
        result["status"] = "list_error"
        result["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return result

    result["list_count"] = len(urls)
    if not urls:
        result["status"] = "list_empty"
        return result

    # 最初の 1 件だけ extract & normalize
    detail_url, category = urls[0]
    try:
        raw = adapter.extract_animal_details(detail_url, category)
        an = DataNormalizer.normalize(raw)
        result["status"] = "ok"
        result["sample"] = {
            "species": an.species,
            "sex": an.sex,
            "shelter_date": str(an.shelter_date),
            "location": an.location[:30],
            "phone": an.phone,
        }
    except Exception as e:
        result["status"] = "detail_error"
        result["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", help="comma-separated site names")
    parser.add_argument("--from-json", help="audit JSON path")
    parser.add_argument("--category", default="suspicious", help="filter audit JSON by category")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--include-js", action="store_true",
                        help="requires_js: true のサイトも Playwright 経由で実行する")
    args = parser.parse_args()

    sites_map = load_sites_yaml()

    if args.names:
        target_names = [n.strip() for n in args.names.split(",") if n.strip()]
    elif args.from_json:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
        target_names = [d["name"] for d in data if d.get("category") == args.category]
    else:
        print("Specify --names or --from-json", file=sys.stderr)
        return 1

    results: list[dict[str, Any]] = []
    for i, name in enumerate(target_names, 1):
        raw = sites_map.get(name)
        if raw is None:
            results.append({"name": name, "status": "not_in_yaml"})
            print(f"  [{i}/{len(target_names)}] ⚠ not_in_yaml: {name}", file=sys.stderr)
            continue
        r = test_site(name, raw, include_js=args.include_js)
        results.append(r)
        marker = {
            "ok": "✓", "list_empty": "○", "skipped_js": "⏭",
            "list_error": "✗ list", "detail_error": "✗ detail", "init_error": "✗ init",
            "no_adapter": "✗ adapter", "not_in_yaml": "⚠ yaml",
        }.get(r["status"], "?")
        suffix = ""
        if r["status"] == "ok":
            sample = r.get("sample", {})
            suffix = f"  ({r.get('list_count')} 件, {sample.get('species')}/{sample.get('shelter_date')})"
        elif r["status"] == "list_empty":
            suffix = "  (list 0 件 = 実データなし)"
        elif "error" in r:
            suffix = f"  {r['error']}"
        print(f"  [{i}/{len(target_names)}] {marker} {name[:38]:38s} {suffix}", file=sys.stderr)

    from collections import Counter
    summary = Counter(r["status"] for r in results)
    print("\n=== summary ===", file=sys.stderr)
    for s, n in summary.most_common():
        print(f"  {s}: {n}", file=sys.stderr)

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
