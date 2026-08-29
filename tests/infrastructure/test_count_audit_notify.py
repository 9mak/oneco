"""count_audit_notify のテスト (T105)

scripts/site_count_audit.py (T046) が検出する掲載数乖離を Discord へ通知する
ロジックを検証する。site_count_audit.py 自体はサイトへの実 HTTP fetch を伴う
一回性スクリプトのため単体テスト対象にせず、通知の要否判定・文面組み立てだけを
ここで固定する (secret_health.py / test_secret_health.py と同じ分離方針)。

背景: undercount_suspect / overcount_suspect / zero_suspect は当日の掲載入れ替わりを
含み得る (単日ノイズ)。pagination_detected は「次ページリンクの存在」のみを示す
情報フラグで件数比較とは無関係なため、これ単体では通知対象にしない。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from data_collector.infrastructure.count_audit_notify import evaluate, maybe_notify
from data_collector.infrastructure.notification_client import NotificationLevel


def _group(host: str, flags: list[str], sites=None, api_count=0, pattern_total=None):
    return {
        "host": host,
        "sites": sites or [host],
        "api_count": api_count,
        "pattern_total": pattern_total,
        "comparable": True,
        "statuses": ["ok"],
        "flags": flags,
    }


def _result(groups: list[dict]) -> dict:
    return {
        "generated_at": "2026-08-28T01:00:00",
        "api_total": 100,
        "site_total": 10,
        "js_skipped": 0,
        "site_results": [],
        "groups": groups,
    }


class TestEvaluate:
    def test_no_groups_no_notify(self):
        has_flags, _message, details = evaluate(_result([]))
        assert has_flags is False
        assert details == {}

    def test_no_flagged_groups_no_notify(self):
        result = _result([_group("a.example.jp", [])])
        has_flags, _message, details = evaluate(result)
        assert has_flags is False
        assert details == {}

    def test_pagination_detected_alone_does_not_notify(self):
        """pagination_detected は件数比較と無関係な情報フラグなので単体では通知しない"""
        result = _result([_group("a.example.jp", ["pagination_detected"])])
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_undercount_suspect_notifies(self):
        result = _result(
            [_group("oita.example.jp", ["undercount_suspect"], api_count=32, pattern_total=65)]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "1" in message
        assert "oita.example.jp" in details

    def test_overcount_suspect_notifies(self):
        result = _result(
            [_group("b.example.jp", ["overcount_suspect"], api_count=10, pattern_total=3)]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "b.example.jp" in details

    def test_zero_suspect_notifies(self):
        result = _result([_group("akita.example.jp", ["zero_suspect"], api_count=0)])
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "akita.example.jp" in details

    def test_pagination_plus_undercount_notifies_via_undercount(self):
        """pagination_detected が併記されていても、乖離系フラグが1つでもあれば通知対象"""
        result = _result(
            [
                _group(
                    "c.example.jp",
                    ["pagination_detected", "undercount_suspect"],
                    api_count=5,
                    pattern_total=8,
                )
            ]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "c.example.jp" in details

    def test_message_counts_only_mismatch_flagged_groups(self):
        result = _result(
            [
                _group("a.example.jp", ["pagination_detected"]),
                _group("b.example.jp", ["undercount_suspect"], api_count=1, pattern_total=2),
            ]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "1" in message
        assert "a.example.jp" not in details
        assert "b.example.jp" in details

    def test_details_include_flag_and_counts(self):
        result = _result(
            [_group("oita.example.jp", ["undercount_suspect"], api_count=32, pattern_total=65)]
        )
        _has_flags, _message, details = evaluate(result)
        detail_text = details["oita.example.jp"]
        assert "undercount_suspect" in detail_text
        assert "32" in detail_text
        assert "65" in detail_text

    def test_single_day_caveat_present_when_flagged(self):
        """当日ノイズが多いスクリプトである旨を通知本文に含め、単日結果を過信させない"""
        result = _result(
            [_group("oita.example.jp", ["undercount_suspect"], api_count=32, pattern_total=65)]
        )
        _has_flags, _message, details = evaluate(result)
        assert any("単日" in v or "確定" in v for v in details.values())

    def test_many_flagged_groups_truncated(self):
        groups = [
            _group(f"host{i}.example.jp", ["undercount_suspect"], api_count=i, pattern_total=i + 1)
            for i in range(15)
        ]
        result = _result(groups)
        _has_flags, message, details = evaluate(result)
        assert "15" in message
        # Discord 2000 文字上限を踏まえ、詳細行数に上限を設ける
        detail_host_keys = [k for k in details if k.startswith("host")]
        assert len(detail_host_keys) < 15
        assert any("他" in v for v in details.values())


class TestMaybeNotify:
    def test_notifies_when_flagged(self):
        client = MagicMock()
        result = _result(
            [_group("oita.example.jp", ["undercount_suspect"], api_count=32, pattern_total=65)]
        )
        notified = maybe_notify(result, client)
        assert notified is True
        client.send_alert.assert_called_once()
        args, _kwargs = client.send_alert.call_args
        assert args[0] == NotificationLevel.WARNING

    def test_no_notify_when_clean(self):
        client = MagicMock()
        result = _result([_group("a.example.jp", [])])
        notified = maybe_notify(result, client)
        assert notified is False
        client.send_alert.assert_not_called()

    def test_no_notify_when_only_pagination(self):
        client = MagicMock()
        result = _result([_group("a.example.jp", ["pagination_detected"])])
        notified = maybe_notify(result, client)
        assert notified is False
        client.send_alert.assert_not_called()
