"""SNS 日次まとめの定型文組み立て (T151 設計 / T160)

LLM を使わない純粋関数。180 字以内を保証し、超える場合は明記する都道府県数を
3 -> 2 -> 1 の順に減らして畳む。
"""

from __future__ import annotations

from .digest import DigestStats

_TARGET_LEN = 180
_HASHTAGS = "#保護犬 #保護猫"


def _other_part(other: int) -> str:
    return f"・その他 {other}" if other >= 1 else ""


def _rest_part(prefecture_counts: list[tuple[str, int]], shown: int) -> str:
    """shown 件を明記した残りを畳む。残りが無ければ空文字。"""
    rest = prefecture_counts[shown:]
    if not rest:
        return ""
    n_pref = len(rest)
    m = sum(count for _pref, count in rest)
    return f"・他 {n_pref} 都道府県 {m} 頭"


def _breakdown_line(prefecture_counts: list[tuple[str, int]], shown: int) -> str:
    top = prefecture_counts[:shown]
    joined = "・".join(f"{pref} {count}" for pref, count in top)
    rest = _rest_part(prefecture_counts, shown)
    return f"内訳: {joined}{rest}。"


def build_digest_text(stats: DigestStats, *, site_url: str) -> str:
    """DigestStats から定型文を組み立てる。180 字以内を保証する。

    Args:
        stats: collect_daily_digest() の集計結果 (0 件なら呼び出さない)
        site_url: 末尾に貼る oneco トップページ URL

    Returns:
        str: 180 字以内の投稿文
    """
    m = stats.target_date.month
    d = stats.target_date.day
    other_part = _other_part(stats.other)
    header = (
        f"{m}/{d} に自治体サイトで新たに公開された保護動物は "
        f"{stats.total} 頭（犬 {stats.dog}・猫 {stats.cat}{other_part}）。"
    )

    # 都道府県が3つ以下 (不明含む) なら畳む必要はなく shown=len(prefecture_counts) 相当。
    # 180字を超える場合のみ明記数を 3 -> 2 -> 1 と減らす。
    for shown in (3, 2, 1):
        breakdown = _breakdown_line(stats.prefecture_counts, shown)
        text = "\n".join(
            [
                header,
                breakdown,
                "詳細と問い合わせは各自治体の公式ページへ。",
                site_url,
                _HASHTAGS,
            ]
        )
        if len(text) <= _TARGET_LEN:
            return text

    # shown=1 でも収まらない (通常想定しない極端な都道府県名長のケース)。
    # 安全側として shown=1 の結果をそのまま返す (呼び出し元の moderator 等の
    # プラットフォーム別切詰めに委ねる)。
    return text
