"""image_url_audit_notify のテスト (T102)

scripts/image_url_audit.py が検出する「画像URLが元ページに実在するか」の
乖離を Discord へ通知するロジックを検証する。scripts/image_url_audit.py
自体はサイトへの実 HTTP fetch を伴う一回性スクリプトのため単体テスト対象にせず、
通知の要否判定・文面組み立てだけをここで固定する
(count_audit_notify.py / test_count_audit_notify.py と同じ分離方針)。

通知対象は「image_not_found_on_page」(元ページに画像が実在しない = T020型の
別個体写真混入・掲載変更の疑い) と「image_broken_link」(画像 URL 自体が
確定的に 4xx を返すリンク切れ) の2種類のみ。ページ取得エラー・画像取得の
一時障害 (timeout/5xx) は誤通知疲労を避けるため通知対象に含めない
(secret_health.py / uptime-check.yml と同じ思想)。
"""

from __future__ import annotations

from data_collector.infrastructure.image_url_audit_notify import evaluate, maybe_notify
from data_collector.infrastructure.notification_client import NotificationLevel


def _animal_result(source_url: str, flags: list[str], image_urls=None, **extra):
    return {
        "id": extra.pop("id", 1),
        "source_url": source_url,
        "image_urls": image_urls or ["https://example.jp/a.jpg"],
        "flags": flags,
        **extra,
    }


def _result(animal_results: list[dict]) -> dict:
    return {
        "generated_at": "2026-08-29T12:00:00",
        "shard": 0,
        "rotation_days": 7,
        "shard_total": len(animal_results),
        "animal_results": animal_results,
    }


class TestEvaluate:
    def test_no_animals_no_notify(self):
        has_flags, _message, details = evaluate(_result([]))
        assert has_flags is False
        assert details == {}

    def test_no_flagged_animals_no_notify(self):
        result = _result([_animal_result("https://a.example.jp/x", [])])
        has_flags, _message, details = evaluate(result)
        assert has_flags is False
        assert details == {}

    def test_page_fetch_error_alone_does_not_notify(self):
        """ページ取得エラーは一時障害の可能性があるため単体では通知しない"""
        result = _result([_animal_result("https://a.example.jp/x", ["page_fetch_error"])])
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_image_fetch_error_alone_does_not_notify(self):
        """画像取得の一時障害 (timeout/5xx) は単体では通知しない"""
        result = _result([_animal_result("https://a.example.jp/x", ["image_fetch_error"])])
        has_flags, _message, _details = evaluate(result)
        assert has_flags is False

    def test_image_not_found_on_page_notifies(self):
        result = _result(
            [
                _animal_result(
                    "https://kumamoto.example.jp/animals/2078",
                    ["image_not_found_on_page"],
                    id=2078,
                )
            ]
        )
        has_flags, message, details = evaluate(result)
        assert has_flags is True
        assert "1" in message
        assert any("2078" in k or "2078" in v for k, v in details.items())

    def test_image_broken_link_notifies(self):
        result = _result([_animal_result("https://b.example.jp/y", ["image_broken_link"], id=42)])
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert any("42" in k or "42" in v for k, v in details.items())

    def test_detail_cap_limits_shown_entries_with_remainder_note(self):
        animals = [
            _animal_result(f"https://c.example.jp/{i}", ["image_not_found_on_page"], id=i)
            for i in range(15)
        ]
        result = _result(animals)
        has_flags, _message, details = evaluate(result)
        assert has_flags is True
        assert len(details) <= 12  # 上限 + 「他」注記 + 「注意」
        assert any("他" in k for k in details)

    def test_message_mentions_count_and_flag_kinds(self):
        result = _result(
            [
                _animal_result("https://d.example.jp/1", ["image_not_found_on_page"], id=1),
                _animal_result("https://d.example.jp/2", ["image_broken_link"], id=2),
            ]
        )
        _has_flags, message, _details = evaluate(result)
        assert "2" in message


class TestMaybeNotify:
    def test_notifies_when_flagged(self):
        class _FakeClient:
            def __init__(self):
                self.calls = []

            def send_alert(self, level, message, details):
                self.calls.append((level, message, details))

        client = _FakeClient()
        result = _result(
            [_animal_result("https://e.example.jp/1", ["image_not_found_on_page"], id=1)]
        )
        notified = maybe_notify(result, client)
        assert notified is True
        assert len(client.calls) == 1
        assert client.calls[0][0] == NotificationLevel.WARNING

    def test_does_not_notify_when_clean(self):
        class _FakeClient:
            def __init__(self):
                self.calls = []

            def send_alert(self, level, message, details):
                self.calls.append((level, message, details))

        client = _FakeClient()
        result = _result([_animal_result("https://e.example.jp/1", [])])
        notified = maybe_notify(result, client)
        assert notified is False
        assert client.calls == []
