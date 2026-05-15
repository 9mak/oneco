"""BrokenSitesTracker - 連続失敗サイトの追跡と永続化

Requirement 6.4: サイトが連続 3 回エラーを返した場合、要修正リストに記録する。

ローカル YAML ファイル (`data/broken_sites.yaml` など) に状態を保持し、
1 回でも成功したらカウンタをリセットする。
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class BrokenSitesTracker:
    """サイト別の連続失敗回数を追跡する"""

    def __init__(self, state_path: Path) -> None:
        self.state_path = Path(state_path)
        self._state: dict[str, dict] = self._load()

    # ─────────────────── 公開 API ───────────────────

    def record_failure(self, site_name: str, error_message: str) -> None:
        """サイトの失敗を記録（連続失敗カウンタ +1）"""
        entry = self._state.get(site_name, {"consecutive_failures": 0})
        entry["consecutive_failures"] = int(entry.get("consecutive_failures", 0)) + 1
        entry["last_error"] = error_message
        entry["last_failed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self._state[site_name] = entry
        self._save()

    def record_success(self, site_name: str) -> None:
        """サイトの成功を記録（カウンタリセット）"""
        if site_name in self._state:
            self._state[site_name]["consecutive_failures"] = 0
            self._save()

    def consecutive_failures(self, site_name: str) -> int:
        """site_name の連続失敗回数を返す（未記録なら 0）"""
        entry = self._state.get(site_name)
        if not entry:
            return 0
        return int(entry.get("consecutive_failures", 0))

    def critical_sites(self, threshold: int = 3) -> list[str]:
        """連続失敗回数が threshold 以上のサイト一覧"""
        return [
            name
            for name, entry in self._state.items()
            if int(entry.get("consecutive_failures", 0)) >= threshold
        ]

    # ─────────────────── 内部 ───────────────────

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
                f"BrokenSitesTracker: 不正な YAML ({self.state_path}): {e}。空状態で初期化"
            )
            return {}

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            yaml.safe_dump(self._state, allow_unicode=True, sort_keys=True),
            encoding="utf-8",
        )
