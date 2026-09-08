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


def _group(host: str, flags: list[str], sites=None, api_count=0, pattern_total=None, delta=None):
    return {
        "host": host,
        "sites": sites or [host],
        "api_count": api_count,
        "pattern_total": pattern_total,
        "delta": delta,
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
        # T141: comparable ホストが約200に増える見込みを踏まえ上限を15へ広げたため、
        # 上限を超えるには15より多い件数が要る
        groups = [
            _group(f"host{i}.example.jp", ["undercount_suspect"], api_count=i, pattern_total=i + 1)
            for i in range(20)
        ]
        result = _result(groups)
        _has_flags, message, details = evaluate(result)
        assert "20" in message
        # Discord 2000 文字上限を踏まえ、詳細行数に上限を設ける
        detail_host_keys = [k for k in details if k.startswith("host")]
        assert len(detail_host_keys) <= 15
        assert any("他" in v for v in details.values())


class TestMagnitudeThreshold:
    """T141: comparable ホスト急増によるノイズ抑制のための |delta| 閾値 (max(2, 20%))"""

    def test_delta_below_threshold_is_silenced(self):
        # api=100, delta=1 は max(2, 20)=20 未満なので静音化
        result = _result(
            [
                _group(
                    "a.example.jp",
                    ["undercount_suspect"],
                    api_count=100,
                    pattern_total=101,
                    delta=1,
                )
            ]
        )
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_delta_at_absolute_floor_notifies(self):
        # api=5, 20%=1 なので下限の2が閾値になり、delta=2 でちょうど通知
        result = _result(
            [_group("b.example.jp", ["undercount_suspect"], api_count=5, pattern_total=7, delta=2)]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "b.example.jp" in details

    def test_delta_just_below_absolute_floor_is_silenced(self):
        result = _result(
            [_group("c.example.jp", ["undercount_suspect"], api_count=5, pattern_total=6, delta=1)]
        )
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_delta_meets_ratio_threshold_notifies(self):
        # api=100, 20%=20 が閾値。delta=25 は超える
        result = _result(
            [
                _group(
                    "d.example.jp",
                    ["overcount_suspect"],
                    api_count=100,
                    pattern_total=75,
                    delta=-25,
                )
            ]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "d.example.jp" in details

    def test_total_outage_on_small_host_bypasses_threshold(self):
        """reviewer F-01: api_count=1 → pattern_total=0 (全滅) は delta=-1 が
        max(2, round(1*0.2))=2 未満でも必ず通知する"""
        result = _result(
            [
                _group(
                    "g.example.jp",
                    ["overcount_suspect"],
                    api_count=1,
                    pattern_total=0,
                    delta=-1,
                )
            ]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "g.example.jp" in details

    def test_total_outage_on_larger_host_bypasses_threshold(self):
        """api_count=10 → pattern_total=0 (全滅) は delta=-10 が閾値2以上でも
        従来通り通知される (回帰確認)"""
        result = _result(
            [
                _group(
                    "h.example.jp",
                    ["overcount_suspect"],
                    api_count=10,
                    pattern_total=0,
                    delta=-10,
                )
            ]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "h.example.jp" in details

    def test_reverse_total_outage_api_zero_bypasses_threshold(self):
        """api_count=0 なのに実サイトには掲載がある (公開側が全滅) も必ず通知する"""
        result = _result(
            [
                _group(
                    "i.example.jp",
                    ["undercount_suspect"],
                    api_count=0,
                    pattern_total=3,
                    delta=3,
                )
            ]
        )
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "i.example.jp" in details

    def test_zero_suspect_ignores_magnitude_threshold(self):
        """zero_suspect は件数差でなく質的判定なので閾値の対象外 (delta=None でも通知)"""
        result = _result([_group("e.example.jp", ["zero_suspect"], api_count=0, delta=None)])
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert "e.example.jp" in details

    def test_missing_delta_does_not_silence_legacy_groups(self):
        """delta キーの無い旧形式 group (T141以前) は静音化せず従来通り通知する"""
        result = _result(
            [_group("f.example.jp", ["undercount_suspect"], api_count=32, pattern_total=65)]
        )
        has_flags, _message, _details = evaluate(result)
        assert has_flags is True

    def test_details_sorted_by_absolute_delta_descending(self):
        result = _result(
            [
                _group(
                    "small.example.jp",
                    ["undercount_suspect"],
                    api_count=10,
                    pattern_total=13,
                    delta=3,
                ),
                _group(
                    "large.example.jp",
                    ["undercount_suspect"],
                    api_count=10,
                    pattern_total=30,
                    delta=20,
                ),
            ]
        )
        _has_flags, _message, details = evaluate(result)
        keys = [k for k in details if k.endswith(".example.jp")]
        assert keys == ["large.example.jp", "small.example.jp"]


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
