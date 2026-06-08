"""クローラーの礼儀（politeness）共通定数とスロットル機構。

偽計業務妨害（刑法233条）リスクを下げるため、HTTP取得の各経路は
本モジュールの共通 User-Agent とスロットルを利用する。
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

# 全 HTTP 取得経路で共有する User-Agent。連絡先（GitHub Issues）を明記。
# HTTP/1.1 ヘッダーは Latin-1 互換でなければならない (http.client.putheader が
# 厳格に latin-1 エンコードする)。日本語を含めると本番収集が UnicodeEncodeError で
# 全サイト失敗するため、内容は ASCII のみで構成する。
ONECO_USER_AGENT = (
    "oneco-collector/1.0 (+https://github.com/9mak/oneco; stop/removal requests via GitHub Issues)"
)

# request_interval 未指定の経路のフォールバック最小間隔（秒）。
DEFAULT_MIN_INTERVAL_SEC = 2.0


class RequestThrottle:
    """前回リクエストからの経過時間で sleep するシンプルなスロットル。

    並列収集で同一インスタンスが複数 thread から共有される場合があるため
    `_lock` で last_request_at の更新を排他する (= バーストを許さない)。
    """

    def __init__(self) -> None:
        self._last_request_at: float | None = None
        self._lock = threading.Lock()

    def wait(self, min_interval_sec: float) -> None:
        """最小間隔を満たすよう必要なら sleep し最終リクエスト時刻を更新する。"""
        # sleep 中に次の thread を入れたくないので「予定 sleep 完了時刻」を
        # ロック内で確定して last_request_at を即時更新する。
        with self._lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                target = self._last_request_at + min_interval_sec
            else:
                target = now
            self._last_request_at = max(target, now)
        # 実 sleep は lock 外。他 thread は target を見て更にずらすので
        # politeness 順序は維持される。
        remaining = target - now
        if remaining > 0:
            time.sleep(remaining)


# ─────────────────── ドメイン共有 throttle ───────────────────
# 並列収集で同一ドメインに対する複数 site の adapter が個別の
# RequestThrottle を持つと「サイト切り替えで throttle がリセット」され、
# サーバ側 WAF が短時間バーストとして検知して 403 を返すケースがある
# (実例: 名古屋市 3 サイトが連続 403 で失敗、2026-06-08)。
# モジュールスコープで domain → RequestThrottle を共有することで、サイトを
# またいで同じ domain への送信間隔を保証する。
_DOMAIN_THROTTLES: dict[str, RequestThrottle] = {}
_DOMAIN_THROTTLES_LOCK = threading.Lock()


def get_throttle_for_url(url: str) -> RequestThrottle:
    """url のホストに対応する RequestThrottle を返す (プロセス共有・スレッド安全)。

    netloc が取れない URL や空文字には専用の throttle を割り当てる (= 並列
    バケットが 1 つ増えるだけで動作には影響しない)。
    """
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        host = ""
    key = host or "__empty__"
    with _DOMAIN_THROTTLES_LOCK:
        throttle = _DOMAIN_THROTTLES.get(key)
        if throttle is None:
            throttle = RequestThrottle()
            _DOMAIN_THROTTLES[key] = throttle
        return throttle
