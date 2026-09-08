"""致命フィールド不一致監査 (scripts/full_publication_audit.py, T045) の結果を Discord へ通知する (T101)。

scripts/full_publication_audit.py は adapter の出力と公開 API を突き合わせ、致命8フィールド
(status/phone/source_url/location/prefecture/category/species/image_urls) の値の食い違いを
検出するが、通知手段を持たず結果ファイルを見に行かないと不一致に気付けなかった。
このモジュールは同スクリプトが出力する result dict (site_results) から通知要否・文面を
組み立てる (count_audit_notify.py と同じ分離方針)。

通知対象は次の2つ。

1. site_results[].mismatches (致命フィールドの値の食い違い = field_mismatch)
2. site_results[].adapter_only (掲載漏れ疑い) のうち、count_audit_blind が立つサイトのもの

2 は当初、件数の乖離は scripts/site_count_audit.py (T046 → T105) の担当と重複するとして
通知対象外にしていた。しかし T105 の comparable 判定はホスト単位で「ホスト内の全サイトが
list_link_pattern を持ち、PDF セレクタと requires_js を1件も含まない」ことを要求するため、
213 サイト中 178 サイト (83.6%) が構造的に判定不能であることが T133 で確定した。しかも
確定済みの掲載漏れ5件のうち4件がこの盲点ホストで起きていた。重複を避ける絞り込み自体は
維持しつつ、T105 が原理的に見られない範囲だけをここが引き受ける (T140)。

api_only (もういない疑い) は引き続き通知しない。掲載漏れと違って「消し忘れ」であり、
公開品質ゲートの前提条件 (掲載漏れがないこと) には効かない。

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
    "致命フィールド不一致・掲載漏れ疑いはいずれも当日の掲載入れ替わりを含む単日ノイズを"
    "含みます。この通知だけで確定とせず、python3 scripts/full_publication_audit.py "
    "--recheck <出力json> で再照合してから対応してください。"
)


def _flagged_sites(result: dict[str, Any]) -> list[dict[str, Any]]:
    site_results = result.get("site_results") or []
    return [r for r in site_results if r.get("mismatches")]


def _blind_missing_sites(result: dict[str, Any]) -> list[dict[str, Any]]:
    """週次カウント監査 (T105) が構造的に見られないホストで掲載漏れ疑いが出たサイト。"""
    site_results = result.get("site_results") or []
    return [r for r in site_results if r.get("count_audit_blind") and r.get("adapter_only")]


def _detail_line(site: dict[str, Any]) -> str:
    mismatches = site.get("mismatches") or []
    fields = sorted({d["field"] for m in mismatches for d in (m.get("diffs") or [])})
    return f"不一致{len(mismatches)}件 [{', '.join(fields)}]"


_MAX_EXAMPLE_URLS = 3


def _missing_detail_line(site: dict[str, Any]) -> str:
    urls = site.get("adapter_only") or []
    line = f"掲載漏れ疑い{len(urls)}件 (週次カウント監査の盲点)"
    examples = urls[:_MAX_EXAMPLE_URLS]
    if examples:
        line += " 例: " + " / ".join(examples)
    return line


def evaluate(result: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """full_publication_audit.py の result dict を評価し、(通知要否, メッセージ, 詳細) を返す。

    通知要否 (has_flags) は「致命フィールド不一致 (mismatches) を持つサイト」または
    「週次カウント監査の盲点ホストで掲載漏れ疑い (adapter_only) が出たサイト」が
    1つ以上あるか。詳細 (details) は NotificationClient.send_alert にそのまま渡す key-value。
    1サイトが両方の兆候を持つ場合は詳細行をまとめて1エントリにする。
    """
    flagged = _flagged_sites(result)
    blind_missing = _blind_missing_sites(result)
    if not flagged and not blind_missing:
        return False, "致命フィールド監査: 不一致なし", {}

    parts: list[str] = []
    if flagged:
        total_mismatch = sum(len(r.get("mismatches") or []) for r in flagged)
        parts.append(f"{len(flagged)} サイト計 {total_mismatch} 件の不一致")
    if blind_missing:
        total_missing = sum(len(r.get("adapter_only") or []) for r in blind_missing)
        parts.append(f"{len(blind_missing)} サイト計 {total_missing} 件の掲載漏れ疑い")
    message = f"致命フィールド監査で {' / '.join(parts)}を検知 (要確認)"

    # サイト名で集約してから上限を適用する。カテゴリごとに独立して切ると、両者が
    # 重複しないサイト集合のとき実質上限が倍になり、Discord の 2000 文字ハード切り詰めで
    # 末尾の「注意」(単日ノイズの免責と --recheck 手順) から先に落ちる。
    lines_by_site: dict[str, list[str]] = {}
    for site in flagged:
        lines_by_site.setdefault(site.get("name", "unknown"), []).append(_detail_line(site))
    for site in blind_missing:
        lines_by_site.setdefault(site.get("name", "unknown"), []).append(_missing_detail_line(site))

    shown = list(lines_by_site.items())[:_MAX_DETAIL_SITES]
    details: dict[str, Any] = {name: " / ".join(lines) for name, lines in shown}
    remaining = len(lines_by_site) - len(shown)
    if remaining > 0:
        details["他"] = f"他 {remaining} サイト (詳細はレポート参照)"
    details["注意"] = _SINGLE_DAY_CAVEAT

    return True, message, details


def maybe_notify(result: dict[str, Any], notification_client: Any) -> bool:
    """不一致または盲点ホストの掲載漏れ疑いがあれば WARNING で通知し True を返す。"""
    has_flags, message, details = evaluate(result)
    if not has_flags:
        return False
    notification_client.send_alert(NotificationLevel.WARNING, message, details)
    return True
