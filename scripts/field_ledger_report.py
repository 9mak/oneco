#!/usr/bin/env python3
"""フィールド提供台帳 (sites.yaml `fields:`) と実測欠損率の突き合わせレポート (T148/T149)。

サイトごとに「台帳上どのフィールドを提供しているか」と「data/field_quality_drift.yaml
に記録されている直近の欠損率」を並べて表示し、次を出す:

1. 各サイト×フィールドの提供有無・直近欠損率
2. **100%欠損なのに台帳では「提供している」(=fields に false と書かれていない)**
   ペアの一覧 — これが「台帳を埋め忘れている（＝抽出漏れの可能性か、まだ
   一次ソース確認していない未提供フィールドか）」の候補。
   `field_quality_tracker.NeverPopulatedAlert` の判定条件 (直近3run 99%以上)
   とは独立に、単純に「最新1run が100%欠損」でゆるく拾う (台帳整備の
   ワークリストなので過検知気味でよい。実際にアラートを鳴らすかどうかは
   NeverPopulatedAlert 側の役目)。

使い方:
    python3 scripts/field_ledger_report.py
    python3 scripts/field_ledger_report.py --sites-yaml path/to/sites.yaml \
        --drift-yaml path/to/field_quality_drift.yaml

一次ソースを見ずに台帳へ機械的に false を書き込むツールではない。出力は
あくまで「人が確認すべき候補リスト」。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SITES_YAML = REPO_ROOT / "src" / "data_collector" / "config" / "sites.yaml"
DEFAULT_DRIFT_YAML = REPO_ROOT / "data" / "field_quality_drift.yaml"

sys.path.insert(0, str(REPO_ROOT / "src"))

from data_collector.llm.config import SiteConfigLoader  # noqa: E402


@dataclass(frozen=True)
class UndeclaredMissingPair:
    """100%欠損なのに台帳で not-provided と宣言されていない (site, field)。"""

    site_name: str
    field: str
    latest_missing_rate: float
    sample_size: int


def load_drift_state(drift_yaml_path: Path) -> dict[str, dict[str, dict]]:
    if not drift_yaml_path.exists():
        return {}
    data = yaml.safe_load(drift_yaml_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def find_undeclared_full_missing(
    provided_fields: dict[str, dict[str, bool]],
    drift_state: dict[str, dict[str, dict]],
    threshold: float = 1.0,
) -> list[UndeclaredMissingPair]:
    """直近 run が threshold 以上欠損で、台帳が false と宣言していないペアを返す。"""
    pairs: list[UndeclaredMissingPair] = []
    for site_name, fields in drift_state.items():
        site_provided = provided_fields.get(site_name, {})
        if not isinstance(fields, dict):
            continue
        for field, field_state in fields.items():
            if site_provided.get(field, True) is False:
                continue  # 台帳が既に「提供していない」と宣言済み
            history = (field_state or {}).get("history", [])
            if not history:
                continue
            latest = history[-1]
            rate = float(latest.get("missing_rate", 0.0))
            if rate >= threshold:
                pairs.append(
                    UndeclaredMissingPair(
                        site_name=site_name,
                        field=field,
                        latest_missing_rate=rate,
                        sample_size=int(latest.get("sample_size", 0)),
                    )
                )
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites-yaml", type=Path, default=DEFAULT_SITES_YAML)
    parser.add_argument("--drift-yaml", type=Path, default=DEFAULT_DRIFT_YAML)
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.0,
        help="「100%欠損」とみなす下限 (デフォルト 1.0 = 完全100%)",
    )
    args = parser.parse_args()

    config = SiteConfigLoader.load(args.sites_yaml)
    provided_fields = {s.name: s.fields for s in config.sites}
    drift_state = load_drift_state(args.drift_yaml)

    print(f"# フィールド提供台帳レポート ({args.sites_yaml})")
    print(f"# 欠損率ソース: {args.drift_yaml}")
    print()

    for site in config.sites:
        site_drift = drift_state.get(site.name)
        if not isinstance(site_drift, dict) or not site_drift:
            continue
        print(f"## {site.name}")
        for field, field_state in sorted(site_drift.items()):
            history = (field_state or {}).get("history", [])
            provided = site.fields.get(field, True)
            provided_label = "提供" if provided else "提供なし(台帳)"
            if not history:
                print(f"  - {field}: {provided_label} / 履歴なし")
                continue
            latest = history[-1]
            rate = float(latest.get("missing_rate", 0.0))
            n = int(latest.get("sample_size", 0))
            print(f"  - {field}: {provided_label} / 直近欠損率 {rate:.0%} (n={n})")
        print()

    undeclared = find_undeclared_full_missing(provided_fields, drift_state, args.threshold)
    print(
        f"# 台帳未整備の候補 (直近欠損率 >= {args.threshold:.0%} だが fields で not-provided 宣言なし)"
    )
    if not undeclared:
        print("該当なし")
    else:
        for p in sorted(undeclared, key=lambda x: (x.site_name, x.field)):
            print(
                f"  - {p.site_name} / {p.field}: {p.latest_missing_rate:.0%} 欠損 "
                f"(n={p.sample_size})"
            )
    print()
    print(f"合計 {len(undeclared)} 件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
