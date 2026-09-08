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


@dataclass(frozen=True)
class NeverPopulatedAlert:
    """T149: 台帳上は「提供している」フィールドなのに、直近 N 回すべて
    ほぼ100%欠損しているサイト×フィールド。ドリフト検知 (急増) では
    「最初からずっと壊れている」ケースを捉えられないため別枠で検知する。
    """

    site_name: str
    field: str
    runs_checked: int
    missing_rate: float  # 直近 run の欠損率 (通知表示用)


# T149: 直近何 run 分を「初回から欠損」判定に使うか。履歴がこれ未満の
# 場合は現時点で持っている run 全部を対象にする (初回 run から鳴らせる
# ようにするため。1 run しかなければその 1 run が 100% なら対象になる)。
NEVER_POPULATED_MIN_RUNS = 3
NEVER_POPULATED_THRESHOLD = 0.99
# 同じ (site, field) の再アラートを抑制する日数。毎 run 状態が変わらない
# 限り鳴り続けるとアラート疲れを起こすため、一定期間に1回だけ鳴らす。
NEVER_POPULATED_SUPPRESS_DAYS = 7


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

    def detect_never_populated(
        self,
        provided_fields: dict[str, dict[str, bool]] | None = None,
        min_runs: int = NEVER_POPULATED_MIN_RUNS,
        threshold: float = NEVER_POPULATED_THRESHOLD,
        suppress_days: int = NEVER_POPULATED_SUPPRESS_DAYS,
        now: datetime | None = None,
    ) -> list[NeverPopulatedAlert]:
        """T149: 台帳上「提供している」はずのフィールドが、直近 min_runs 回
        (履歴がそれ未満なら現有全 run) すべて threshold 以上欠損している
        site×field を検知する。

        `provided_fields[site_name][field] is False` の site×field は
        台帳上「元サイトが提供していない」ので対象外 (breed-null-survey /
        phone-null-survey で確認済みのケースを誤検知させないため)。
        `provided_fields` に site/field が無い場合は「提供している」扱い
        (SiteConfig.fields のデフォルトと揃える)。

        同一 (site, field) の再通知は `suppress_days` 日に1回だけに絞る
        (`last_never_alert_at` を drift yaml に記録)。抑制期間内は
        `detect_never_populated` の返り値に含めない。呼び出し側が通知を
        実際に送った後 `mark_never_populated_alerted` を呼ぶこと。
        """
        now = now or datetime.now().astimezone()
        provided_fields = provided_fields or {}
        alerts: list[NeverPopulatedAlert] = []
        for site_name, fields in self._state.items():
            site_provided = provided_fields.get(site_name, {})
            for field, field_state in fields.items():
                if site_provided.get(field, True) is False:
                    continue
                history = field_state.get("history", [])
                if not history:
                    continue
                recent = history[-min_runs:]
                if not all(float(h.get("missing_rate", 0.0)) >= threshold for h in recent):
                    continue
                last_alert_at = field_state.get("last_never_alert_at")
                if last_alert_at:
                    try:
                        last_dt = datetime.fromisoformat(last_alert_at)
                        if (now - last_dt).days < suppress_days:
                            continue
                    except ValueError:
                        pass
                alerts.append(
                    NeverPopulatedAlert(
                        site_name=site_name,
                        field=field,
                        runs_checked=len(recent),
                        missing_rate=float(recent[-1].get("missing_rate", 0.0)),
                    )
                )
        return alerts

    def mark_never_populated_alerted(
        self,
        alerts: list[NeverPopulatedAlert],
        now: datetime | None = None,
    ) -> None:
        """`detect_never_populated` が返したアラートを通知済みとして記録する。

        呼び出し側が実際に通知を送信できたときだけ呼ぶこと (送信前に呼ぶと
        送信失敗時も抑制期間に入ってしまい、直せていない状態が黙って
        7日間隠れる)。
        """
        if not alerts:
            return
        ts = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
        for a in alerts:
            field_state = self._state.get(a.site_name, {}).get(a.field)
            if field_state is not None:
                field_state["last_never_alert_at"] = ts
        self._save()

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
