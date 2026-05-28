"""FieldQualityTracker - サイト×フィールド欠損率履歴の追跡とドリフト検知

自己修復ループの「検知層」(Phase 1)。各サイトについて
location/age_months/size/sex/phone/image_urls の欠損率を毎 run 記録し、
前回比 +threshold 以上の急増 (例: 0.05 → 0.85) を adapter のラベル/
セレクタ不一致シグナルとして検出する。

YAML スキーマ (`data/field_quality_drift.yaml`):
    サイト名:
      location:
        history:
          - run_at: '2026-05-28T16:00:00+09:00'
            missing_rate: 0.05
            sample_size: 100
          - run_at: '2026-05-29T16:00:00+09:00'
            missing_rate: 0.85
            sample_size: 100
        last_alert_at: null
      age_months:
        ...

検知結果は `_send_run_summary_alert` 経由で Slack に通知され、Phase 2 で
adapter コードの自動修復ワーカーをトリガーする。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# 各 site × field の履歴を保持する最大件数。古い run は捨てる。
HISTORY_LIMIT = 10


@dataclass(frozen=True)
class FieldDrift:
    """前回比 +threshold 以上の欠損率急増を表す検知結果"""

    site_name: str
    field: str
    prev_rate: float
    curr_rate: float
    delta: float  # curr - prev (正の値のみ)


class FieldQualityTracker:
    """サイト×フィールドの欠損率履歴を保持し、急変ドリフトを検知する"""

    def __init__(self, state_path: Path) -> None:
        self.state_path = Path(state_path)
        self._state: dict[str, dict[str, dict]] = self._load()

    # ─────────────────── 公開 API ───────────────────

    def record(
        self,
        site_name: str,
        missing_rates: dict[str, float],
        sample_size: int,
        now: datetime | None = None,
    ) -> None:
        """1 run の欠損率を履歴に追加する。"""
        ts = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        site_state = self._state.setdefault(site_name, {})
        for field, rate in missing_rates.items():
            field_state = site_state.setdefault(field, {"history": [], "last_alert_at": None})
            history = field_state.setdefault("history", [])
            history.append(
                {
                    "run_at": ts,
                    "missing_rate": float(rate),
                    "sample_size": int(sample_size),
                }
            )
            # 古い履歴を切り詰め
            if len(history) > HISTORY_LIMIT:
                del history[: len(history) - HISTORY_LIMIT]
        self._save()

    def detect_drifts(self, threshold: float = 0.20) -> list[FieldDrift]:
        """前回比 +threshold 以上の欠損率急増を持つ site×field を返す。

        履歴が 1 件以下の field は判定対象外 (初回 run はドリフトなし)。
        改善 (curr < prev) はドリフトに含めない。
        """
        drifts: list[FieldDrift] = []
        for site_name, fields in self._state.items():
            for field, field_state in fields.items():
                history = field_state.get("history", [])
                if len(history) < 2:
                    continue
                prev_rate = float(history[-2].get("missing_rate", 0.0))
                curr_rate = float(history[-1].get("missing_rate", 0.0))
                delta = curr_rate - prev_rate
                if delta >= threshold:
                    drifts.append(
                        FieldDrift(
                            site_name=site_name,
                            field=field,
                            prev_rate=prev_rate,
                            curr_rate=curr_rate,
                            delta=delta,
                        )
                    )
        return drifts

    # ─────────────────── 内部 ───────────────────

    def _load(self) -> dict[str, dict[str, dict]]:
        if not self.state_path.exists():
            return {}
        try:
            data = yaml.safe_load(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            return {}
        except yaml.YAMLError as e:
            logger.warning(
                f"FieldQualityTracker: 不正な YAML ({self.state_path}): {e}。空状態で初期化"
            )
            return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            yaml.safe_dump(self._state, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
