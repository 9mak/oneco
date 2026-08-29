"""画像URL実在監査 (scripts/image_url_audit.py, T102) の結果を Discord へ通知する。

W002 Acceptance「画像URLが元ページに実在するかを自動照合する」に対応する。
熊本の別個体写真混入事故 (T020, PR #263) のように、元サイトと違う子の写真が
公開される致命リスクを、目視でなく機械的に検知する。scripts/image_url_audit.py は
実 HTTP fetch を伴う一回性バッチだが通知手段を持たないため、このモジュールが
同スクリプトの result dict (animal_results) から通知要否・文面を組み立てる。

通知対象は animal_results[].flags のうち以下の2種類のみ
(secret_health.py / count_audit_notify.py と同じ「確定的な異常だけを通知する」思想):

- image_not_found_on_page: 元ページ (source_url) を実際に fetch し、そのページの
  <img>/画像リンクの中に登録済み image_url が1件も見つからない。T020 型の
  「別個体の写真が公開されている」「掲載自体が既に変わっている」の一次シグナル。
- image_broken_link: image_url 自体に直接アクセスし、確定的な 4xx が返る
  (リンク切れ)。

以下は通知対象に含めない (誤通知疲労を避けるため):

- page_fetch_error: source_url 自体の取得に失敗 (timeout/5xx/接続エラー)。
  一時障害の可能性があり、ページが存在しないと確定できない。
- image_fetch_error: image_url 取得の一時障害 (timeout/5xx/接続エラー)。
  4xx ほど確定的でない。

なお image_not_found_on_page は「その日 (収集後) にサイト側で掲載内容が
入れ替わった」だけでも起こりうる (site_count_audit.py の undercount/overcount と
同種の単日ノイズ)。通知本文には単日結果を確定情報として扱わない注記を含める。
"""

from __future__ import annotations

from typing import Any

from .notification_client import NotificationLevel

# 通知対象とする確定的な異常フラグのみ (page_fetch_error / image_fetch_error は対象外)
_NOTIFY_FLAGS = frozenset({"image_not_found_on_page", "image_broken_link"})

# Discord メッセージの content 上限は 2000 文字 (NotificationClient 側で最終的に切り詰める)。
# その手前で「詳細行を並べすぎて意味のある内容が切れる」事故を防ぐため、
# 詳細行として展開する個体数の上限をここで設ける。
_MAX_DETAIL_ANIMALS = 10

_SINGLE_DAY_CAVEAT = (
    "image_not_found_on_page はサイト側の掲載入れ替わり (収集後の更新) でも起こりえます。"
    "この通知だけで別個体混入と確定させず、元ページ・元画像を目視で確認してください。"
)


def _flagged_animals(result: dict[str, Any]) -> list[dict[str, Any]]:
    animals = result.get("animal_results") or []
    return [a for a in animals if _NOTIFY_FLAGS.intersection(a.get("flags") or [])]


def _detail_line(animal: dict[str, Any]) -> str:
    flags = sorted(_NOTIFY_FLAGS.intersection(animal.get("flags") or []))
    return f"{animal.get('source_url', '?')} [{', '.join(flags)}]"


def evaluate(result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """image_url_audit.py の result dict を評価し、(通知要否, メッセージ, 詳細) を返す。

    通知要否 (has_flags) は「通知対象フラグが1つ以上立った個体があるか」。
    詳細 (details) は NotificationClient.send_alert にそのまま渡す key-value。
    """
    flagged = _flagged_animals(result)
    if not flagged:
        return False, "画像URL監査: 乖離なし", {}

    message = f"画像URL監査で {len(flagged)} 件の個体に乖離疑いを検知 (要確認)"

    details: dict[str, Any] = {}
    shown = flagged[:_MAX_DETAIL_ANIMALS]
    for animal in shown:
        key = f"id={animal.get('id', '?')}"
        details[key] = _detail_line(animal)
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
