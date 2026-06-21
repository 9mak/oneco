"""SiteBaselineTracker - サイト別収集件数の永続ベースライン追跡とゼロ件回帰検知

snapshot (`snapshots/latest.json`) は run ごとに reset + 再構築されるため、
あるサイトが 0 件を返すとそのサイトの snapshot エントリが消え、次回 run の
「前回件数」が 0 になる。結果として「前回 ≥ 1 件 → 今回 0 件」の件数低下検知が
1 run しか効かず、2 run 目以降は永久に沈黙する（サイレント破損）。

このトラッカーは件数ベースラインを snapshot とは独立した YAML
(`data/site_baselines.yaml`) に永続化する。**0 件では last_nonzero_count を
減らさない**ため、「過去に ≥ 1 件あったサイトが今 0 件」を毎 run 検知できる。

YAML スキーマ:
    サイト名:
      last_count: 0
      last_nonzero_count: 5
      last_nonzero_at: '2026-06-18T00:00:00+09:00'
      high_water_count: 7
      consecutive_zero_runs: 2
      last_seen_at: '2026-06-19T00:00:00+09:00'

検知結果 (`ZeroCountRegression`) は `_send_run_summary_alert` 経由で運用者へ
通知される（`BrokenSitesTracker.critical_sites` / `FieldQualityTracker.detect_drifts`
と同じく既存のサマリアラート経路に合流する）。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZeroCountRegression:
    """過去 ≥ 1 件あったが今 0 件が継続しているサイトの検知結果"""

    site_name: str
    baseline_count: int  # last_nonzero_count（過去の非ゼロ件数）
    consecutive_zero_runs: int
    last_nonzero_at: str | None


class SiteBaselineTracker:
    """サイト別収集件数の永続ベースラインを保持し、ゼロ件回帰を検知する"""

    def __init__(self, state_path: Path | str) -> None:
        self.state_path = Path(state_path)
        self._state: dict[str, dict] = self._load()
        # main() のサマリ集計フェーズ（収集ループ完了後・単一スレッド）で使う
        # 想定だが、念のため read-modify-write を直列化する。
        self._lock = threading.Lock()

    # ─────────────────── 公開 API ───────────────────

    def record(self, site_name: str, count: int, now: datetime | None = None) -> None:
        """1 run のサイト件数を記録する。

        count > 0 のときのみ last_nonzero_count / high_water_count / last_nonzero_at
        を更新し、consecutive_zero_runs を 0 にリセットする。count == 0 のときは
        ベースラインを温存したまま consecutive_zero_runs を +1 する。
        """
        ts = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        count = int(count)
        with self._lock:
            entry = self._state.get(site_name, {})
            entry["last_count"] = count
            entry["last_seen_at"] = ts
            if count > 0:
                entry["last_nonzero_count"] = count
                entry["last_nonzero_at"] = ts
                entry["high_water_count"] = max(int(entry.get("high_water_count", 0)), count)
                entry["consecutive_zero_runs"] = 0
            else:
                entry["consecutive_zero_runs"] = int(entry.get("consecutive_zero_runs", 0)) + 1
            self._state[site_name] = entry
            self._save()

    def baseline(self, site_name: str) -> int:
        """過去の非ゼロ件数（last_nonzero_count、未記録なら 0）"""
        return int(self._entry(site_name).get("last_nonzero_count", 0))

    def last_count(self, site_name: str) -> int:
        return int(self._entry(site_name).get("last_count", 0))

    def high_water_count(self, site_name: str) -> int:
        return int(self._entry(site_name).get("high_water_count", 0))

    def consecutive_zero_runs(self, site_name: str) -> int:
        return int(self._entry(site_name).get("consecutive_zero_runs", 0))

    def last_nonzero_at(self, site_name: str) -> str | None:
        ts = self._entry(site_name).get("last_nonzero_at")
        return str(ts) if ts else None

    def detect_zero_count_regressions(
        self, *, threshold: int = 2, min_baseline: int = 1
    ) -> list[ZeroCountRegression]:
        """過去 ≥ min_baseline 件あったが threshold 回連続で 0 件のサイトを返す。

        Args:
            threshold: 連続 0 件回数がこの値以上で回帰として扱う。1 run だけの 0 は
                「在庫が一時的に 0」の可能性があるため、デフォルト 2 でフラップを抑える。
            min_baseline: ベースライン件数の下限。薄いサイト（baseline 1 件など）の
                誤検知を避けたい場合に引き上げる。

        一度もデータが無いサイト（baseline 0）は破損と区別できないため対象外。
        """
        out: list[ZeroCountRegression] = []
        for name, entry in self._state.items():
            baseline = int(entry.get("last_nonzero_count", 0))
            last_count = int(entry.get("last_count", 0))
            czr = int(entry.get("consecutive_zero_runs", 0))
            if baseline >= min_baseline and last_count == 0 and czr >= threshold:
                out.append(
                    ZeroCountRegression(
                        site_name=name,
                        baseline_count=baseline,
                        consecutive_zero_runs=czr,
                        last_nonzero_at=(
                            str(entry["last_nonzero_at"]) if entry.get("last_nonzero_at") else None
                        ),
                    )
                )
        return out

    # ─────────────────── 内部 ───────────────────

    def _entry(self, site_name: str) -> dict:
        return self._state.get(site_name, {})

    def _load(self) -> dict[str, dict]:
        if not self.state_path.exists():
            return {}
        try:
            data = yaml.safe_load(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {}
        except yaml.YAMLError as e:
            logger.warning(
                f"SiteBaselineTracker: 不正な YAML ({self.state_path}): {e}。空状態で初期化"
            )
            return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            yaml.safe_dump(self._state, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
