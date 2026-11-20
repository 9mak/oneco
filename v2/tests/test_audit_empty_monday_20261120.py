"""W006 T656 付随・項目 7: 0 頭の根拠の監査（ops/audit_empty.py）は、同じ顔ぶれが続く間も月曜だけもう一度送る（2026-11-20）。

当たる slug の集合が前回と変わった日にしか送らないので、直さないまま放置されやすかった（11/20 も 3 件当たっているが「前回と同じ。送らない」）。
月曜（JST）は、集合が同じでも 1 件以上当たっていれば送る。同じ日に何度走らせても 1 通。0 件の月曜は送らない。
"""

from __future__ import annotations

import json
from datetime import date

import pytest
from test_audit_empty_t631 import _finds, _mod

MON, TUE, SUN = date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 22)
NEXT_MON = date(2026, 11, 23)


def _send(m, findings, state, sent, today):
    return m.notify_if_changed(findings, state, sent.append, today=today)


def test_same_set_is_silent_on_other_days_but_sent_on_monday(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "s.json"
    assert _send(m, _finds(m, "a-1", "b-1"), state, sent, TUE) is True          # 初回（火）: 前回なし → 送る
    assert _send(m, _finds(m, "a-1", "b-1"), state, sent, date(2026, 11, 18)) is False   # 同じ集合の水曜 → 送らない
    assert _send(m, _finds(m, "a-1", "b-1"), state, sent, SUN) is False         # 日曜も送らない
    assert len(sent) == 1
    assert _send(m, _finds(m, "a-1", "b-1"), state, sent, NEXT_MON) is True     # 月曜 → 同じ顔ぶれでも送る
    assert len(sent) == 2
    assert "月曜の再通知" in sent[1] and "前回と同じ" in sent[1] and "a-1" in sent[1] and "b-1" in sent[1]
    assert "増えた" not in sent[1] and "解消" not in sent[1]


def test_monday_sends_once_even_if_run_twice(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "s.json"
    _send(m, _finds(m, "a-1"), state, sent, TUE)
    assert _send(m, _finds(m, "a-1"), state, sent, MON) is True
    assert _send(m, _finds(m, "a-1"), state, sent, MON) is False     # 同じ月曜の 2 回目
    assert len(sent) == 2


def test_changed_set_on_monday_is_one_message_and_counts_as_the_mondays(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "s.json"
    _send(m, _finds(m, "a-1"), state, sent, TUE)
    assert _send(m, _finds(m, "a-1", "b-1"), state, sent, MON) is True
    assert "増えた: b-1" in sent[-1] and "月曜の再通知" not in sent[-1]    # 変わった日は従来の文面
    assert _send(m, _finds(m, "a-1", "b-1"), state, sent, MON) is False  # その月曜はもう送った
    assert len(sent) == 2


def test_monday_with_nothing_found_is_silent(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "s.json"
    _send(m, _finds(m, "a-1"), state, sent, TUE)
    assert _send(m, [], state, sent, MON) is True      # 解消（集合が変わった）は従来どおり 1 通
    assert _send(m, [], state, sent, NEXT_MON) is False  # 0 件のまま続く月曜は送らない
    assert len(sent) == 2


def test_monday_send_failure_does_not_record_and_retries_next_run(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "s.json"
    _send(m, _finds(m, "a-1"), state, sent, TUE)

    def boom(_msg: str) -> None:
        raise OSError("down")

    with pytest.raises(OSError):
        m.notify_if_changed(_finds(m, "a-1"), state, boom, today=MON)
    assert _send(m, _finds(m, "a-1"), state, sent, MON) is True   # 失敗した月曜は記録されていないので、次の実行でまた送る
    assert len(sent) == 2


def test_state_without_notified_key_still_works_and_keeps_slugs(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "s.json"
    state.write_text(json.dumps({"date": "2026-11-20", "slugs": ["a-1"]}), encoding="utf-8")   # 旧い形式（notified なし）
    assert _send(m, _finds(m, "a-1"), state, sent, TUE) is False
    assert _send(m, _finds(m, "a-1"), state, sent, MON) is True
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["slugs"] == ["a-1"] and saved["notified"] == "2026-11-16"
