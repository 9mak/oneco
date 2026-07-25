"""0件検知の軽量再検証 (LLM 不使用)

SiteBaselineTracker.detect_zero_count_regressions() は「過去≥1件のサイトが
threshold 回連続0件」を検知するが、baseline 1〜2件の薄いサイトは在庫の
自然な増減で 2 回連続 0 件になりやすく、誤検知が多い(2026-07-24 実データ:
検知15件中14件が baseline 1〜2件)。

一方で threshold を単純に引き上げる(様子見期間を延ばす)と、逆に「本サイト
には掲載されているのに oneco 側の収集が壊れて 0 件になっている」見逃しを
長引かせてしまう。

そこで threshold を弄る代わりに、baseline の大小に関係なく検知の都度、
LLM を使わない軽量な再確認を挟む:
1. adapter でもう一度 fetch_animal_list() する (一時的なネットワーク/在庫の
   揺らぎを除外)
2. それでも 0 件なら、list ページの実 HTML にサイト側の明示的な「該当なし」
   メッセージがあるか確認する (あれば「本サイト側も0件」で正常と確定)

どちらにも当てはまらなければ壊れている疑いが濃厚と判断し、修理候補として
残す (should_flag=True)。判定に必要な情報が取れない(例外)場合は安全側に
倒して True にする。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

_ZERO_MESSAGE_PATTERNS = [
    # 「現在/只今/ただいま + (説明) + ありません/いません」
    # (2026-07-25 実サイト調査: 「対象となる犬はいません」等「いません」型が
    # 「ありません」型と同程度に多く、旧パターンは「ありません」のみだった)
    re.compile(r"(現在|只今|ただいま)[、,]?.{0,25}(ありません|いません)"),
    re.compile(r"該当する.{0,15}(情報|動物)?.{0,3}ありません"),
    re.compile(r"対象.{0,10}(動物|犬|猫).{0,5}いません"),
    re.compile(r"収容.{0,15}(動物|情報|犬|猫)?.{0,5}(ありません|いません)"),
]


class _ListFetchableAdapter(Protocol):
    def fetch_animal_list(self) -> list[tuple[str, str]]: ...

    def _http_get(self, url: str) -> str: ...


@dataclass
class ZeroCountVerification:
    """0件再検証の結果。

    should_flag=True: 壊れている疑いが濃厚。修理候補として残すべき。
    should_flag=False: 正常(在庫の一時的な揺らぎ、またはサイト側の明示的な0件)。
    """

    should_flag: bool
    reason: str


def _has_explicit_zero_message(html: str) -> bool:
    return any(pattern.search(html) for pattern in _ZERO_MESSAGE_PATTERNS)


def verify_zero_count(adapter: _ListFetchableAdapter, list_url: str) -> ZeroCountVerification:
    """0件検知後に呼ぶ軽量再検証。LLM は使わない。"""
    try:
        urls = adapter.fetch_animal_list()
    except Exception as e:
        return ZeroCountVerification(
            should_flag=True, reason=f"再取得で例外が発生 ({type(e).__name__}: {e})"
        )
    if urls:
        return ZeroCountVerification(
            should_flag=False, reason=f"再取得したら{len(urls)}件あった(一時的な揺らぎ)"
        )

    try:
        html = adapter._http_get(list_url)
    except Exception as e:
        return ZeroCountVerification(
            should_flag=True,
            reason=f"0件確定後のHTML再取得で例外が発生 ({type(e).__name__}: {e})",
        )

    if _has_explicit_zero_message(html):
        return ZeroCountVerification(
            should_flag=False, reason="サイト側に明示的な0件メッセージあり"
        )

    return ZeroCountVerification(
        should_flag=True, reason="再取得も0件で、0件メッセージも見当たらない"
    )
