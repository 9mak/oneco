"""AI 修復の試行の記録（W006 T633）。不採用も含め、run ごとに data/repair_attempts/<日付>/<slug>-<run_id>.yaml へ残す。

目的は判定を変えることではなく、後から「AI は何を返し、新レシピは何を根拠に何頭取り、なぜ落ちたか」を人の直しと
突き合わせられるようにすること（0 頭の文言型を受け付ける改善 3 の可否は、この記録が無いと測れない）。
入口の HTML（または PDF のバイト列）も run ごとに <slug>-<run_id>.html に置き、同じ日の 2 回目の run で上書きしない。
data/ は git 管理外。古い日付のディレクトリは run の開始時に消す（KEEP_DAYS。ログの 30 日と同じ）。
"""

from __future__ import annotations

import logging
import shutil
from datetime import date as date_type
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("collector")
KEEP_DAYS = 30  # collect.sh のログ削除（collect-*.log・events-*.jsonl の -mtime +30）と同じ
DROPPED_HEAD = 3
_TEXT_MAX = 200


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    # 複数行（AI が返した YAML）は読める形の | ブロックで残す
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", data, style="|" if "\n" in data else None
    )


_Dumper.add_representer(str, _str)


def dropped_head(dropped: list[Any]) -> list[dict[str, str]]:
    """捨てた行の先頭 3 行（理由と本文の頭）。"""
    return [
        {"reason": d.reason, "text": " ".join(str(d.text).split())[:_TEXT_MAX]}
        for d in dropped[:DROPPED_HEAD]
    ]


def write_attempt(
    root: Path,
    date: str,
    slug: str,
    run_id: str,
    record: dict[str, Any],
    entry: bytes | None = None,
    entry_ext: str = "html",
) -> Path:
    """記録を root/<date>/<slug>-<run_id>.yaml に書く。entry があれば同名の .html（PDF なら .pdf）も。返すのは yaml のパス。"""
    d = root / date
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{slug}-{run_id}"
    if entry is not None:
        (d / f"{stem}.{entry_ext}").write_bytes(entry)
        record = {**record, "entry": {**record.get("entry", {}), "file": f"{stem}.{entry_ext}"}}
    p = d / f"{stem}.yaml"
    p.write_text(
        yaml.dump(
            record, Dumper=_Dumper, allow_unicode=True, sort_keys=False, default_flow_style=False
        ),
        encoding="utf-8",
    )
    return p


def rotate_attempts(root: Path, today: str, keep_days: int = KEEP_DAYS) -> None:
    """today から keep_days 日より前の日付ディレクトリを消す。日付名でないものは触らない。"""
    try:
        t = date_type.fromisoformat(today)
        entries = list(root.iterdir()) if root.is_dir() else []
    except (ValueError, OSError):
        return
    for p in entries:
        try:
            if not p.is_dir() or p.is_symlink():
                continue
            if (t - date_type.fromisoformat(p.name)).days > keep_days:
                shutil.rmtree(p)
        except (ValueError, OSError) as e:
            if not isinstance(e, ValueError):
                log.warning("repair_attempts の古い記録を消せない %s: %s", p, e)
