"""診断結果の Discord 通知整形と reports/diagnosis/ への永続化 (T406)

`diagnosis.py` が作る `SiteDiagnosis` のリストを、
- Discord 向けコンパクトブロック (1 サイト最大 15 行、1 run 最大 5 サイト、
  残りは "+N more" にまとめる)
- reports/diagnosis/ 配下の JSON (機械可読な全件) + Markdown (人が読む全件)

の 2 経路に整形する。通知本文を絞るのは `_send_run_summary_alert` の
never_populated 通知キャップ (T149) と同じ理由: 1 run で大量に壊れると
Discord 本文が洪水化するため。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .diagnosis import SiteDiagnosis

logger = logging.getLogger(__name__)

DIAGNOSIS_REPORT_DIR = Path("reports/diagnosis")

# Discord 通知本文に含める最大サイト数 (残りは "+N more" で件数のみ)
_DISCORD_MAX_SITES = 5


def build_discord_summary(diagnoses: list[SiteDiagnosis]) -> str:
    """Discord 通知本文用のコンパクトな要約文字列を作る"""
    if not diagnoses:
        return ""
    blocks: list[str] = []
    for d in diagnoses[:_DISCORD_MAX_SITES]:
        blocks.append("\n".join(d.summary_lines()))
    text = "\n\n".join(blocks)
    remaining = len(diagnoses) - _DISCORD_MAX_SITES
    if remaining > 0:
        text += f"\n\n... (+{remaining} サイト、詳細は artifact を参照)"
    return text


def write_artifacts(
    diagnoses: list[SiteDiagnosis],
    *,
    output_dir: Path | str = DIAGNOSIS_REPORT_DIR,
    now: datetime | None = None,
) -> tuple[Path, Path] | None:
    """reports/diagnosis/ 配下に JSON + Markdown を書き出す。診断が 0 件なら何もしない。

    Returns:
        (json_path, md_path)。diagnoses が空なら None。
    """
    if not diagnoses:
        return None
    ts = (now or datetime.now(UTC).astimezone()).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"diagnosis_{ts}.json"
    md_path = out_dir / f"diagnosis_{ts}.md"

    payload = {
        "generated_at": ts,
        "site_count": len(diagnoses),
        "sites": [d.to_dict() for d in diagnoses],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 壊れサイト診断 ({ts})", "", f"対象: {len(diagnoses)} サイト", ""]
    for d in diagnoses:
        lines.extend(d.summary_lines(max_lines=1000))
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    logger.info(f"診断artifact書き出し: {json_path}, {md_path}")
    return json_path, md_path
