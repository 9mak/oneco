"""politeness モジュール（共通UA・スロットル）のテスト。"""

from unittest.mock import patch

from data_collector.adapters.politeness import (
    DEFAULT_MIN_INTERVAL_SEC,
    ONECO_USER_AGENT,
    RequestThrottle,
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
    # monotonic を制御: 1回目=100.0, 2回目wait冒頭=100.5, 更新=101.0
    times = [100.0, 100.0, 100.5, 101.0]
    with (
        patch("data_collector.adapters.politeness.time.monotonic", side_effect=times),
        patch("data_collector.adapters.politeness.time.sleep") as mock_sleep,
    ):
        throttle.wait(2.0)  # 初回: sleepなし、_last=100.0
        throttle.wait(2.0)  # 経過0.5s → 残り1.5s sleep
    mock_sleep.assert_called_once()
    assert abs(mock_sleep.call_args[0][0] - 1.5) < 1e-9


def test_no_sleep_when_interval_already_elapsed() -> None:
    """十分な時間が経過していれば sleep しない。"""
    throttle = RequestThrottle()
    times = [100.0, 100.0, 105.0, 105.0]
    with (
        patch("data_collector.adapters.politeness.time.monotonic", side_effect=times),
        patch("data_collector.adapters.politeness.time.sleep") as mock_sleep,
    ):
        throttle.wait(2.0)
        throttle.wait(2.0)
    mock_sleep.assert_not_called()
