"""politeness モジュール（共通UA・スロットル）のテスト。"""

import threading
import time
from unittest.mock import patch

from data_collector.adapters.politeness import (
    DEFAULT_MIN_INTERVAL_SEC,
    ONECO_USER_AGENT,
    RequestThrottle,
    get_throttle_for_url,
)


def test_user_agent_contains_contact() -> None:
    """User-Agent に連絡先（リポジトリURL）が含まれる。"""
    assert "github.com/9mak/oneco" in ONECO_USER_AGENT


def test_user_agent_is_ascii_only() -> None:
    """User-Agent は ASCII のみ。

    HTTP/1.1 ヘッダーは Latin-1 互換でなければならず、Python の
    http.client.putheader は厳格に latin-1 エンコードする。日本語等を
    含めると本番 HTTP 取得が UnicodeEncodeError で全件失敗するため、
    ASCII 限定を契約として固定する。
    """
    ONECO_USER_AGENT.encode("ascii")  # raises UnicodeEncodeError if non-ASCII


def test_default_min_interval_is_at_least_one_second() -> None:
    """フォールバック間隔は1秒以上（負荷配慮の下限）。"""
    assert DEFAULT_MIN_INTERVAL_SEC >= 1.0


def test_first_request_does_not_sleep() -> None:
    """初回リクエストは待機しない。"""
    throttle = RequestThrottle()
    with patch("data_collector.adapters.politeness.time.sleep") as mock_sleep:
        throttle.wait(2.0)
    mock_sleep.assert_not_called()


def test_second_request_sleeps_remaining_interval() -> None:
    """間隔未満の連続リクエストは残り時間だけ sleep する。"""
    throttle = RequestThrottle()
    # 並列対応 wait は monotonic を 1 回/呼び出ししか使わない。
    # 1回目=100.0, 2回目=100.5 → 2回目の sleep は (100.0+2.0)-100.5=1.5s
    times = [100.0, 100.5]
    with (
        patch("data_collector.adapters.politeness.time.monotonic", side_effect=times),
        patch("data_collector.adapters.politeness.time.sleep") as mock_sleep,
    ):
        throttle.wait(2.0)  # 初回: sleepなし、_last=100.0
        throttle.wait(2.0)  # 経過0.5s → 残り1.5s sleep、_last=102.0
    mock_sleep.assert_called_once()
    assert abs(mock_sleep.call_args[0][0] - 1.5) < 1e-9


def test_no_sleep_when_interval_already_elapsed() -> None:
    """十分な時間が経過していれば sleep しない。"""
    throttle = RequestThrottle()
    times = [100.0, 105.0]
    with (
        patch("data_collector.adapters.politeness.time.monotonic", side_effect=times),
        patch("data_collector.adapters.politeness.time.sleep") as mock_sleep,
    ):
        throttle.wait(2.0)
        throttle.wait(2.0)
    mock_sleep.assert_not_called()


def test_get_throttle_for_url_shares_per_domain() -> None:
    """同じドメインの URL は同じ throttle インスタンスを共有する。"""
    a = get_throttle_for_url("https://www.city.nagoya.jp/foo")
    b = get_throttle_for_url("https://www.city.nagoya.jp/bar")
    assert a is b
    # 異なるドメインは別 throttle
    c = get_throttle_for_url("https://www.city.osaka.lg.jp/foo")
    assert a is not c


def test_get_throttle_for_url_is_thread_safe() -> None:
    """多数 thread から同時呼び出ししても、同じドメインなら同じインスタンスを返す。"""
    results: list = []
    barrier = threading.Barrier(20)

    def worker() -> None:
        barrier.wait()
        results.append(get_throttle_for_url("https://race.example.jp/x"))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(r) for r in results}) == 1


def test_request_throttle_serializes_concurrent_waits() -> None:
    """複数 thread が同一 throttle.wait を呼んでもバーストは起きない。

    politeness の核要件: スレッドが同時に wait しても 2 回目以降の "requested"
    時刻は min_interval_sec ずつずれる。これが無いと並列 worker が同一ドメインに
    バーストして WAF に block される (名古屋市 403 ケース)。
    """
    throttle = RequestThrottle()
    request_times: list = []
    lock = threading.Lock()
    barrier = threading.Barrier(5)

    def worker() -> None:
        barrier.wait()
        throttle.wait(0.05)
        with lock:
            request_times.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(5)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 5 回の wait で 5 \* 0.05 = 0.25s 以上の合計時間がかかる
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15, f"throttle did not serialize: elapsed={elapsed}"
    # 連続するリクエストは少なくとも 0.03s 以上離れている (lock 開放後の余白も含む)
    sorted_times = sorted(request_times)
    intervals = [sorted_times[i + 1] - sorted_times[i] for i in range(len(sorted_times) - 1)]
    assert all(iv >= 0.03 for iv in intervals), f"intervals too short: {intervals}"
