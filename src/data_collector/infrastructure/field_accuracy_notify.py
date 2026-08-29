"""致命フィールド不一致監査 (scripts/full_publication_audit.py, T045) の結果を Discord へ通知する (T101)。

scripts/full_publication_audit.py は adapter の出力と公開 API を突き合わせ、致命8フィールド
(status/phone/source_url/location/prefecture/category/species/image_urls) の値の食い違いを
検出するが、通知手段を持たず結果ファイルを見に行かないと不一致に気付けなかった。
このモジュールは同スクリプトが出力する result dict (site_results) から通知要否・文面を
組み立てる (count_audit_notify.py と同じ分離方針)。

通知対象は site_results[].mismatches (致命フィールドの値の食い違い = field_mismatch) のみ。
同じ result dict に含まれる api_only (もういない疑い) / adapter_only (掲載漏れ疑い) は
「件数」の乖離であり、scripts/site_count_audit.py (T046 → T105) が adapter を経由しない
独立シグナルで既に週次監視している対象と重複するため、ここでは通知対象にしない
(secret_health.py の「configured かつ ok=False のみ通知」と同じ絞り込み思想)。

full_publication_audit.py のモジュール docstring にある通り、field_mismatch も当日の
掲載入れ替わり (行番号仮想URL のズレ等) を含みうる。通知本文には単日結果を確定情報として
扱わず --recheck で再照合する旨の注記を必ず含める。
"""

from __future__ import annotations

from typing import Any

from .notification_client import NotificationLevel

# Discord メッセージの content 上限は 2000 文字 (NotificationClient 側で最終的に切り詰める)。
# その手前で「詳細行を並べすぎて意味のある内容が切れる」事故を防ぐため、
# 詳細行として展開するサイト数の上限をここで設ける。
_MAX_DETAIL_SITES = 10

_SINGLE_DAY_CAVEAT = (
    "致命フィールド不一致は当日の掲載入れ替わりを含む単日ノイズを含みます。"
    "この通知だけで確定とせず、python3 scripts/full_publication_audit.py --recheck "
    "<出力json> で再照合してから対応してください。"
)


def _flagged_sites(result: dict[str, Any]) -> list[dict[str, Any]]:
    site_results = result.get("site_results") or []
    return [r for r in site_results if r.get("mismatches")]


def _detail_line(site: dict[str, Any]) -> str:
    mismatches = site.get("mismatches") or []
    fields = sorted({d["field"] for m in mismatches for d in (m.get("diffs") or [])})
    return f"不一致{len(mismatches)}件 [{', '.join(fields)}]"


def evaluate(result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """full_publication_audit.py の result dict を評価し、(通知要否, メッセージ, 詳細) を返す。

    通知要否 (has_flags) は「致命フィールド不一致 (mismatches) を持つサイトが1つ以上あるか」。
    詳細 (details) は NotificationClient.send_alert にそのまま渡す key-value。
    """
    flagged = _flagged_sites(result)
    if not flagged:
        return False, "致命フィールド監査: 不一致なし", {}

    total_mismatch = sum(len(r.get("mismatches") or []) for r in flagged)
    message = (
        f"致命フィールド監査で {len(flagged)} サイト計 {total_mismatch} 件の不一致を検知 (要確認)"
    )

    details: dict[str, Any] = {}
    shown = flagged[:_MAX_DETAIL_SITES]
    for site in shown:
        details[site.get("name", "unknown")] = _detail_line(site)
    remaining = len(flagged) - len(shown)
    if remaining > 0:
        details["他"] = f"他 {remaining} サイト (詳細はレポート参照)"
    details["注意"] = _SINGLE_DAY_CAVEAT

    return True, message, details


def maybe_notify(result: dict[str, Any], notification_client: Any) -> bool:
    """不一致があれば WARNING で通知し True を返す。無ければ通知せず False。"""
    has_flags, message, details = evaluate(result)
    if not has_flags:
        return False
    notification_client.send_alert(NotificationLevel.WARNING, message, details)
    return True
