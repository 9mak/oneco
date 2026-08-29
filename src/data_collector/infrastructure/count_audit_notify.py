"""実サイト掲載数監査 (scripts/site_count_audit.py, T046) の結果を Discord へ通知する (T105)。

scripts/site_count_audit.py は adapter を経由せず実サイトと oneco 公開数を突き合わせる
週次バッチだが、通知手段を持たず結果ファイルを見に行かないと乖離に気付けなかった。
このモジュールは同スクリプトが出力する result dict (groups) から通知要否・文面を組み立てる。

通知対象は group["flags"] のうち以下の「件数比較」フラグのみ (secret_health.py の
「configured かつ ok=False のみ通知」と同じ絞り込み思想):

- undercount_suspect: 実サイト側の pattern 件数が API 公開数を上回る (掲載漏れ疑い)
- overcount_suspect : API 公開数が実サイト側 pattern 件数を上回る (残骸疑い)
- zero_suspect       : API 0 件なのにゼロ表現が無く掲載候補シグナルがある

pagination_detected は「次ページリンクの存在」を示すだけの情報フラグで、件数比較とは
独立に付与される (adapter が正しく辿っている場合でも立つ)。これ単体では乖離の証拠にならず
通知すると誤通知疲労を招くため対象外とする。

site_count_audit.py のモジュール docstring にある通り、undercount / overcount は
当日の掲載入れ替わりを含むノイズが多い。通知本文には単日結果を確定情報として
扱わない注記を必ず含める。
"""

from __future__ import annotations

from typing import Any

from .notification_client import NotificationLevel

# 件数比較として意味のあるフラグのみを通知対象にする (pagination_detected は対象外)
_COUNT_MISMATCH_FLAGS = frozenset({"undercount_suspect", "overcount_suspect", "zero_suspect"})

# Discord メッセージの content 上限は 2000 文字 (NotificationClient 側で最終的に切り詰める)。
# その手前で「詳細行を並べすぎて意味のある内容が切れる」事故を防ぐため、
# 詳細行として展開するホスト数の上限をここで設ける。
_MAX_DETAIL_GROUPS = 10

_SINGLE_DAY_CAVEAT = (
    "undercount/overcount は当日の掲載入れ替わりを含む単日ノイズを含みます。"
    "この通知だけで確定とせず、再実行しても残るか確認してください。"
)


def _flagged_groups(result: dict[str, Any]) -> list[dict[str, Any]]:
    groups = result.get("groups") or []
    return [g for g in groups if _COUNT_MISMATCH_FLAGS.intersection(g.get("flags") or [])]


def _detail_line(group: dict[str, Any]) -> str:
    mismatch_flags = sorted(_COUNT_MISMATCH_FLAGS.intersection(group.get("flags") or []))
    sites = "/".join(group.get("sites") or [group.get("host", "?")])
    api_count = group.get("api_count")
    pattern_total = group.get("pattern_total")
    return f"{sites} api={api_count} pattern={pattern_total} [{', '.join(mismatch_flags)}]"


def evaluate(result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """site_count_audit.py の result dict を評価し、(通知要否, メッセージ, 詳細) を返す。

    通知要否 (has_flags) は「件数比較フラグが1つ以上立ったホストがあるか」。
    詳細 (details) は NotificationClient.send_alert にそのまま渡す key-value。
    """
    flagged = _flagged_groups(result)
    if not flagged:
        return False, "掲載数監査: 乖離なし", {}

    message = f"掲載数監査で {len(flagged)} ホストに乖離疑いを検知 (要確認)"

    details: dict[str, Any] = {}
    shown = flagged[:_MAX_DETAIL_GROUPS]
    for group in shown:
        details[group.get("host", "unknown")] = _detail_line(group)
    remaining = len(flagged) - len(shown)
    if remaining > 0:
        details["他"] = f"他 {remaining} 件 (詳細はレポート参照)"
    details["注意"] = _SINGLE_DAY_CAVEAT

    return True, message, details


def maybe_notify(result: dict[str, Any], notification_client: Any) -> bool:
    """乖離があれば WARNING で通知し True を返す。無ければ通知せず False。"""
    has_flags, message, details = evaluate(result)
    if not has_flags:
        return False
    notification_client.send_alert(NotificationLevel.WARNING, message, details)
    return True
