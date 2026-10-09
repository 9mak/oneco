"""収集の状態を日をまたいで持つ（W006 T607）。state/sources.json（git 管理外）。

slug ごと: last_ok / last_ok_count / consecutive_failures（日数）/ first_failed / last_status /
           last_error_kind / last_host / last_date / prev_status
ホストごと: breaker[host] = {opened: 日付, failures: 件数}（T603）
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any

from .registry import ROOT

log = logging.getLogger("collector")
JST = timezone(timedelta(hours=9))
STATE_DIR = ROOT / "state"
FAILING = ("failed", "ambiguous_empty")   # 「読めていない」状態
GOOD = ("ok", "empty")


class AlreadyRunningError(RuntimeError):
    """別の収集が動いている（T609）。"""


def _empty() -> dict[str, Any]:
    return {"sources": {}, "breaker": {}}


def load_state(state_dir: Path = STATE_DIR) -> dict[str, Any]:
    p = state_dir / "sources.json"
    if not p.exists():
        return _empty()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("sources", {}), dict):
            raise ValueError("形が違う")
    except (OSError, ValueError) as e:
        log.warning("state/sources.json が壊れているので空から始める: %s", e)
        return _empty()
    data.setdefault("sources", {})
    if not isinstance(data.get("breaker"), dict):
        data["breaker"] = {}
    return data


def save_state(state: dict[str, Any], state_dir: Path = STATE_DIR) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    p = state_dir / "sources.json"
    tmp = state_dir / f".sources.json.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


class RunLock:
    """run() 全体を囲む排他。fcntl.flock を非ブロッキングで取る（プロセスが死ねば OS が解放する）。"""

    def __init__(self, state_dir: Path = STATE_DIR) -> None:
        self.path = state_dir / "collect.lock"
        self._fd: int | None = None

    def __enter__(self) -> RunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            raise AlreadyRunningError("他の収集が動いている") from e
        self._fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


def update_sources(state: dict[str, Any], report: list[dict[str, Any]], date: str) -> None:
    """今日の report を slug ごとの状態に反映する。同じ日に 2 回走っても consecutive_failures を二重に数えない。"""
    sources = state.setdefault("sources", {})
    for r in report:
        status = r["status"]
        if status not in FAILING and status not in GOOD:
            continue   # link_only / disabled は触らない
        st = sources.setdefault(r["slug"], {})
        if st.get("last_date") != date:
            st["prev_status"] = st.get("last_status")
            prev_n = st.get("consecutive_failures", 0)
        else:   # 同じ日の再実行: 今日分を引いてから数え直す
            prev_n = max(st.get("consecutive_failures", 0) - 1, 0) if st.get("last_status") in FAILING else 0
        if status in GOOD:
            st.update(last_ok=date, last_ok_count=r.get("count", 0), consecutive_failures=0, first_failed=None,
                      last_error_kind=None)
        else:
            info = r.get("error_info") or {}
            st["consecutive_failures"] = prev_n + 1
            st["first_failed"] = st.get("first_failed") or date
            st["last_error_kind"] = info.get("kind")
            st["last_host"] = info.get("host")
        st["last_status"] = status
        st["last_date"] = date
