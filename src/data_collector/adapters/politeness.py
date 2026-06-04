"""クローラーの礼儀（politeness）共通定数とスロットル機構。

偽計業務妨害（刑法233条）リスクを下げるため、HTTP取得の各経路は
本モジュールの共通 User-Agent とスロットルを利用する。
"""

import time

# 全 HTTP 取得経路で共有する User-Agent。連絡先（GitHub Issues）を明記。
ONECO_USER_AGENT = (
    "oneco-collector/1.0 (+https://github.com/9mak/oneco; 停止・削除のご依頼は同 Issues へ)"
)

# request_interval 未指定の経路のフォールバック最小間隔（秒）。
DEFAULT_MIN_INTERVAL_SEC = 2.0


class RequestThrottle:
    """前回リクエストからの経過時間で sleep するシンプルなスロットル。"""

    def __init__(self) -> None:
        self._last_request_at: float | None = None

    def wait(self, min_interval_sec: float) -> None:
        """最小間隔を満たすよう必要なら sleep し最終リクエスト時刻を更新する。"""
        now = time.monotonic()
        if self._last_request_at is not None:
            remaining = min_interval_sec - (now - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()
