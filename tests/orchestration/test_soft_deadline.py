"""SoftDeadline のユニットテスト。

ハードタイムアウトの前に adapter に「もう止まれ」と伝えるための
協調キャンセル機構なので、時刻ベース判定の正確性をピン留めする。
"""

from __future__ import annotations

import time

import pytest

from data_collector.orchestration.soft_deadline import SoftDeadline


def test_initial_state_does_not_trigger() -> None:
    """生成直後は経過 0 なので発火しない。"""
    deadline = SoftDeadline(seconds=10, soft_ratio=0.8)
    assert deadline.should_soft_stop() is False


def test_triggers_after_soft_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """soft_ratio × seconds を超えた時点で発火する。"""
    fake_time = [100.0]
    monkeypatch.setattr(
        "data_collector.orchestration.soft_deadline.time.monotonic",
        lambda: fake_time[0],
    )
    deadline = SoftDeadline(seconds=10, soft_ratio=0.8)
    # 7.9s 経過: まだ発火しない (8.0s が境界)
    fake_time[0] = 107.9
    assert deadline.should_soft_stop() is False
    # 8.0s 経過: 発火
    fake_time[0] = 108.0
    assert deadline.should_soft_stop() is True


def test_once_triggered_stays_triggered(monkeypatch: pytest.MonkeyPatch) -> None:
    """一度 True を返したら時刻を巻き戻しても True (latched)。"""
    fake_time = [100.0]
    monkeypatch.setattr(
        "data_collector.orchestration.soft_deadline.time.monotonic",
        lambda: fake_time[0],
    )
    deadline = SoftDeadline(seconds=10, soft_ratio=0.5)
    fake_time[0] = 106.0
    assert deadline.should_soft_stop() is True
    # 時刻を巻き戻し
    fake_time[0] = 100.0
    assert deadline.should_soft_stop() is True


def test_invalid_seconds_raises() -> None:
    with pytest.raises(ValueError):
        SoftDeadline(seconds=0)
    with pytest.raises(ValueError):
        SoftDeadline(seconds=-1)


def test_invalid_soft_ratio_raises() -> None:
    with pytest.raises(ValueError):
        SoftDeadline(seconds=10, soft_ratio=0)
    with pytest.raises(ValueError):
        SoftDeadline(seconds=10, soft_ratio=1.0)


def test_soft_limit_seconds_property() -> None:
    deadline = SoftDeadline(seconds=300, soft_ratio=0.8)
    assert deadline.soft_limit_seconds == pytest.approx(240.0)


def test_elapsed_increases(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_time = [50.0]
    monkeypatch.setattr(
        "data_collector.orchestration.soft_deadline.time.monotonic",
        lambda: fake_time[0],
    )
    deadline = SoftDeadline(seconds=10)
    assert deadline.elapsed() == 0
    fake_time[0] = 55.5
    assert deadline.elapsed() == pytest.approx(5.5)


def test_real_clock_smoke() -> None:
    """単発の実時刻 smoke (CI 等で fake clock 周りの bug を検知)。"""
    deadline = SoftDeadline(seconds=0.5, soft_ratio=0.5)
    # 0.0s: まだ
    assert deadline.should_soft_stop() is False
    time.sleep(0.3)
    # 0.3s > 0.25s: 発火
    assert deadline.should_soft_stop() is True
