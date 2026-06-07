"""ソフトデッドライン: タイムアウト直前に adapter に早期終了を促すフラグ。

ハードタイムアウト (SiteCollectionTimeoutError) で全件破棄するよりも、
タイムアウト直前に「これまで集めた分を返してくれ」と adapter にお願いする
方が、ユーザー価値が高い。

使い方:
    deadline = SoftDeadline(seconds=300, soft_ratio=0.8)
    for url in detail_urls:
        if deadline.should_soft_stop():
            logger.warning("soft deadline reached, returning partial data")
            break
        # ... extract detail
"""

from __future__ import annotations

import time


class SoftDeadline:
    """経過時間が「ハード timeout × soft_ratio」を超えたら True を返す。

    politeness throttle と組み合わせて adapter のループ内で参照する。
    rule-based adapter のように N 件の detail を順次取得する箇所で、
    残り時間が少なくなったら detail 取得を打ち切り「これまで集まった
    分を返す」フォールバックに使う。
    """

    def __init__(self, seconds: float, soft_ratio: float = 0.8) -> None:
        if seconds <= 0:
            raise ValueError(f"seconds must be positive, got {seconds}")
        if not 0 < soft_ratio < 1:
            raise ValueError(f"soft_ratio must be in (0, 1), got {soft_ratio}")
        self._start = time.monotonic()
        self._seconds = seconds
        self._soft_ratio = soft_ratio
        self._triggered = False

    def should_soft_stop(self) -> bool:
        """soft deadline を超えたら True。一度 True を返したら以降も True。"""
        if self._triggered:
            return True
        if time.monotonic() - self._start >= self._seconds * self._soft_ratio:
            self._triggered = True
            return True
        return False

    def elapsed(self) -> float:
        """開始からの経過秒数。"""
        return time.monotonic() - self._start

    @property
    def soft_limit_seconds(self) -> float:
        """soft deadline までの秒数 (絶対時間ではなく相対)。"""
        return self._seconds * self._soft_ratio
