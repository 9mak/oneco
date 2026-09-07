"""field_accuracy_notify のテスト (T101)

scripts/full_publication_audit.py (T045) が検出する致命8フィールドの不一致を
Discord へ通知するロジックを検証する。full_publication_audit.py 自体は全サイトへの
実 HTTP fetch を伴う一回性スクリプトのため単体テスト対象にせず、通知の要否判定・
文面組み立てだけをここで固定する (count_audit_notify.py / test_count_audit_notify.py
と同じ分離方針)。

背景: field_mismatch は当日の掲載入れ替わり (行番号仮想URL のズレ等) を含み得る
(単日ノイズ)。api_only / adapter_only (件数の乖離) は原則 site_count_audit.py (T105) の
担当なのでここでは通知しない。ただし T105 の comparable 判定はホスト単位で全サイトが
list_link_pattern を持つことを要求するため、213 サイト中 178 サイトが構造的に判定不能
だと T133 で確定した。その盲点に属するサイトの adapter_only (掲載漏れ疑い) だけは
どの経路にも乗らないので、count_audit_blind が立つサイトに限りここで通知する (T140)。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from data_collector.infrastructure.field_accuracy_notify import evaluate, maybe_notify
from data_collector.infrastructure.notification_client import NotificationLevel


def _mismatch(source_url: str, diffs: list[dict]) -> dict:
    return {"source_url": source_url, "diffs": diffs}


def _site(
    name: str,
    mismatches: list[dict] | None = None,
    adapter_only=None,
    count_audit_blind: bool = False,
) -> dict:
    return {
        "name": name,
        "list_url": f"https://{name}.example.jp/list",
        "status": "ok",
        "mismatches": mismatches or [],
        "adapter_only": adapter_only or [],
        "count_audit_blind": count_audit_blind,
    }


def _result(site_results: list[dict], api_only=None) -> dict:
    return {
        "generated_at": "2026-08-29T03:00:00",
        "api_base": "https://oneco-api.example",
        "api_total": 100,
        "site_results": site_results,
        "api_only": api_only or [],
        "js_unaudited": [],
    }


class TestEvaluate:
    def test_no_sites_no_notify(self):
        has_flags, _message, details = evaluate(_result([]))
        assert has_flags is False
        assert details == {}

    def test_no_mismatches_no_notify(self):
        result = _result([_site("a-pref")])
        has_flags, _message, details = evaluate(result)
        assert has_flags is False
        assert details == {}

    def test_adapter_only_in_comparable_host_does_not_notify(self):
        """T105 が判定できるホスト (count_audit_blind=False) の adapter_only は
        週次カウント監査の担当と重複するため、ここでは通知しない"""
        result = _result([_site("a-pref", adapter_only=["https://a-pref.example.jp/1"])])
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_adapter_only_in_blind_host_notifies(self):
        """T105 が構造的に判定できないホストの adapter_only はどの経路にも乗らないので通知する"""
        result = _result(
            [
                _site(
                    "tokushima",
                    adapter_only=["https://tokushima.example.jp/1"],
                    count_audit_blind=True,
                )
            ]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "掲載漏れ" in message
        assert "tokushima" in details

    def test_blind_host_without_adapter_only_does_not_notify(self):
        """盲点ホストでも掲載漏れ疑いが無ければ通知しない (誤通知疲労を避ける)"""
        result = _result([_site("tokushima", count_audit_blind=True)])
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_blind_missing_detail_includes_count(self):
        result = _result(
            [
                _site(
                    "okinawa",
                    adapter_only=[
                        "https://okinawa.example.jp/1",
                        "https://okinawa.example.jp/2",
                    ],
                    count_audit_blind=True,
                )
            ]
        )
        _has_flags, _message, details = evaluate(result)
        assert "2件" in details["okinawa"]

    def test_mismatch_and_blind_missing_both_reported(self):
        """両方あるときは1通にまとめ、どちらの件数も落とさない"""
        result = _result(
            [
                _site(
                    "kumamoto",
                    mismatches=[
                        _mismatch(
                            "https://kumamoto.example.jp/1",
                            [{"field": "phone", "site": "096-000-0000", "api": None}],
                        )
                    ],
                ),
                _site(
                    "tokushima",
                    adapter_only=["https://tokushima.example.jp/1"],
                    count_audit_blind=True,
                ),
            ]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "不一致" in message
        assert "掲載漏れ" in message
        assert "kumamoto" in details
        assert "tokushima" in details

    def test_same_site_with_both_signals_is_not_double_counted(self):
        """1サイトが両方の兆候を持っても詳細キーは衝突させず、両方の情報を残す"""
        result = _result(
            [
                _site(
                    "oita",
                    mismatches=[
                        _mismatch(
                            "https://oita.example.jp/1",
                            [{"field": "location", "site": "大分市", "api": "別府市"}],
                        )
                    ],
                    adapter_only=["https://oita.example.jp/2"],
                    count_audit_blind=True,
                )
            ]
        )
        _has_flags, _message, details = evaluate(result)
        detail_text = " ".join(str(v) for v in details.values())
        assert "location" in detail_text
        assert "掲載漏れ" in detail_text

    def test_combined_detail_cap_is_not_doubled(self):
        """詳細行の上限は2カテゴリ合算で効かせる (reviewer F-01)

        flagged と blind_missing に独立に上限をかけると、両者が重複しないサイト集合の
        とき実質上限が倍になる。details は Discord 側で 2000 文字にハード切り詰めされ、
        そのとき末尾に置いた「注意」(単日ノイズの免責と --recheck 手順) から先に消える。
        """
        site_results = [
            _site(
                f"mismatch{i}",
                mismatches=[
                    _mismatch(
                        f"https://mismatch{i}.example.jp/1",
                        [{"field": "phone", "site": "000", "api": None}],
                    )
                ],
            )
            for i in range(10)
        ] + [
            _site(
                f"blind{i}",
                adapter_only=[f"https://blind{i}.example.jp/1"],
                count_audit_blind=True,
            )
            for i in range(10)
        ]
        _has_flags, _message, details = evaluate(_result(site_results))
        site_keys = [k for k in details if k not in ("他", "注意")]
        assert len(site_keys) <= 10
        assert "注意" in details
        assert details["他"] == "他 10 サイト (詳細はレポート参照)"

    def test_many_blind_missing_sites_truncated(self):
        site_results = [
            _site(
                f"blind{i}",
                adapter_only=[f"https://blind{i}.example.jp/1"],
                count_audit_blind=True,
            )
            for i in range(15)
        ]
        result = _result(site_results)
        _has_flags, message, details = evaluate(result)
        assert "15" in message
        detail_site_keys = [k for k in details if k.startswith("blind")]
        assert len(detail_site_keys) < 15

    def test_api_only_alone_does_not_notify(self):
        result = _result(
            [_site("a-pref")],
            api_only=[{"source_url": "https://a-pref.example.jp/2", "id": 1, "species": "dog"}],
        )
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_field_mismatch_notifies(self):
        result = _result(
            [
                _site(
                    "yamanashi",
                    mismatches=[
                        _mismatch(
                            "https://yamanashi.example.jp/1",
                            [{"field": "phone", "site": "055-000-0000", "api": None}],
                        )
                    ],
                )
            ]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "1" in message
        assert "yamanashi" in details

    def test_message_counts_only_flagged_sites(self):
        result = _result(
            [
                _site("clean-pref"),
                _site(
                    "kumamoto",
                    mismatches=[
                        _mismatch(
                            "https://kumamoto.example.jp/1",
                            [{"field": "status", "site": "adoption", "api": "protection"}],
                        )
                    ],
                ),
            ]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "1" in message
        assert "clean-pref" not in details
        assert "kumamoto" in details

    def test_details_include_mismatch_count_and_fields(self):
        result = _result(
            [
                _site(
                    "ehime",
                    mismatches=[
                        _mismatch(
                            "https://ehime.example.jp/1",
                            [
                                {"field": "location", "site": "松山市", "api": "今治市"},
                                {"field": "image_urls", "site": [], "api": ["a.jpg"]},
                            ],
                        ),
                        _mismatch(
                            "https://ehime.example.jp/2",
                            [{"field": "phone", "site": "089-000-0000", "api": None}],
                        ),
                    ],
                )
            ]
        )
        _has_flags, _message, details = evaluate(result)
        detail_text = details["ehime"]
        assert "2件" in detail_text
        assert "location" in detail_text
        assert "phone" in detail_text

    def test_single_day_caveat_present_when_flagged(self):
        """当日の掲載入れ替わりを含みうる旨を通知本文に含め、単日結果を過信させない"""
        result = _result(
            [
                _site(
                    "chiba",
                    mismatches=[
                        _mismatch(
                            "https://chiba.example.jp/1",
                            [{"field": "species", "site": "犬", "api": "猫"}],
                        )
                    ],
                )
            ]
        )
        _has_flags, _message, details = evaluate(result)
        assert any("単日" in v or "recheck" in v for v in details.values())

    def test_many_flagged_sites_truncated(self):
        site_results = [
            _site(
                f"pref{i}",
                mismatches=[
                    _mismatch(
                        f"https://pref{i}.example.jp/1",
                        [{"field": "phone", "site": "000", "api": None}],
                    )
                ],
            )
            for i in range(15)
        ]
        result = _result(site_results)
        _has_flags, message, details = evaluate(result)
        assert "15" in message
        # Discord 2000 文字上限を踏まえ、詳細行数に上限を設ける
        detail_site_keys = [k for k in details if k.startswith("pref")]
        assert len(detail_site_keys) < 15
        assert any("他" in v for v in details.values())


class TestMaybeNotify:
    def test_notifies_when_flagged(self):
        client = MagicMock()
        result = _result(
            [
                _site(
                    "yamanashi",
                    mismatches=[
                        _mismatch(
                            "https://yamanashi.example.jp/1",
                            [{"field": "phone", "site": "055-000-0000", "api": None}],
                        )
                    ],
                )
            ]
        )
        notified = maybe_notify(result, client)
        assert notified is True
        client.send_alert.assert_called_once()
        args, _kwargs = client.send_alert.call_args
        assert args[0] == NotificationLevel.WARNING

    def test_no_notify_when_clean(self):
        client = MagicMock()
        result = _result([_site("a-pref")])
        notified = maybe_notify(result, client)
        assert notified is False
        client.send_alert.assert_not_called()

    def test_no_notify_when_only_adapter_only_in_comparable_host(self):
        client = MagicMock()
        result = _result([_site("a-pref", adapter_only=["https://a-pref.example.jp/1"])])
        notified = maybe_notify(result, client)
        assert notified is False
        client.send_alert.assert_not_called()

    def test_notifies_when_blind_host_has_adapter_only(self):
        client = MagicMock()
        result = _result(
            [
                _site(
                    "tokushima",
                    adapter_only=["https://tokushima.example.jp/1"],
                    count_audit_blind=True,
                )
            ]
        )
        notified = maybe_notify(result, client)
        assert notified is True
        client.send_alert.assert_called_once()
        args, _kwargs = client.send_alert.call_args
        assert args[0] == NotificationLevel.WARNING
