"""secret_health のテスト

外部 API トークン (Groq / Threads) の失効を定期チェックし、失効時に Discord 通知する
ロジックを検証する。実 API は叩かず httpx.Client を mock する。

背景: 2026-06-27 に Groq key が GitHub secret 側で失効していたのに約6週間気づかず、
SNS 投稿が全部 fallback テンプレ文に劣化していた（workflow は fallback で success
表示のため無音）。同じ「静かな失効」を二度と起こさないための早期検知。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from data_collector.infrastructure.notification_client import NotificationLevel
from data_collector.infrastructure.secret_health import (
    SecretCheckResult,
    check_groq,
    check_threads,
    evaluate,
    maybe_notify,
)


def _resp(status_code: int) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    return r


def _client_returning(status_code: int) -> MagicMock:
    client = MagicMock()
    client.get.return_value = _resp(status_code)
    return client


def _client_raising(exc: Exception) -> MagicMock:
    client = MagicMock()
    client.get.side_effect = exc
    return client


class TestCheckGroq:
    def test_valid_key_is_ok(self):
        result = check_groq("gsk_valid", client=_client_returning(200))
        assert result.name == "groq"
        assert result.configured is True
        assert result.ok is True
        assert result.status_code == 200

    def test_401_is_expired(self):
        result = check_groq("gsk_revoked", client=_client_returning(401))
        assert result.configured is True
        assert result.ok is False
        assert result.status_code == 401

    def test_403_is_expired(self):
        result = check_groq("gsk_revoked", client=_client_returning(403))
        assert result.ok is False

    def test_5xx_treated_as_transient_ok(self):
        """5xx は一時障害の可能性。誤通知疲労を避けるため ok 扱い (status は残す)"""
        result = check_groq("gsk_valid", client=_client_returning(503))
        assert result.ok is True
        assert result.status_code == 503

    def test_network_error_treated_as_transient_ok(self):
        result = check_groq("gsk_valid", client=_client_raising(OSError("conn reset")))
        assert result.ok is True
        assert result.status_code is None

    def test_unconfigured_key_is_skipped(self):
        """key 未設定は監視対象外 (configured=False, ok=True で通知しない)"""
        for empty in (None, "", "   "):
            result = check_groq(empty, client=_client_returning(200))
            assert result.configured is False
            assert result.ok is True

    def test_unconfigured_does_not_call_api(self):
        client = _client_returning(200)
        check_groq(None, client=client)
        client.get.assert_not_called()

    def test_authorization_header_sent(self):
        client = _client_returning(200)
        check_groq("gsk_abc", client=client)
        _, kwargs = client.get.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer gsk_abc"


class TestCheckThreads:
    def test_valid_token_is_ok(self):
        result = check_threads("EAAB_valid", client=_client_returning(200))
        assert result.name == "threads"
        assert result.configured is True
        assert result.ok is True

    def test_401_is_expired(self):
        result = check_threads("EAAB_expired", client=_client_returning(401))
        assert result.ok is False
        assert result.status_code == 401

    def test_unconfigured_token_is_skipped(self):
        result = check_threads(None, client=_client_returning(200))
        assert result.configured is False
        assert result.ok is True

    def test_token_sent_as_param_not_logged_in_url(self):
        """access_token は params で渡す (検証だけ。漏えい対策は別途)"""
        client = _client_returning(200)
        check_threads("EAAB_secret", client=client)
        _, kwargs = client.get.call_args
        assert kwargs["params"]["access_token"] == "EAAB_secret"


class TestEvaluate:
    def test_no_expired_returns_false(self):
        results = [
            SecretCheckResult("groq", configured=True, ok=True, status_code=200, detail="ok"),
            SecretCheckResult("threads", configured=True, ok=True, status_code=200, detail="ok"),
        ]
        has_expired, _message, details = evaluate(results)
        assert has_expired is False
        assert details == {}

    def test_expired_listed_in_message_and_details(self):
        results = [
            SecretCheckResult("groq", configured=True, ok=False, status_code=401, detail="401"),
            SecretCheckResult("threads", configured=True, ok=True, status_code=200, detail="ok"),
        ]
        has_expired, message, details = evaluate(results)
        assert has_expired is True
        assert "groq" in message
        assert "groq" in details
        assert "threads" not in details

    def test_unconfigured_not_treated_as_expired(self):
        results = [
            SecretCheckResult("groq", configured=False, ok=True, status_code=None, detail="skip"),
        ]
        has_expired, _, _ = evaluate(results)
        assert has_expired is False


class TestMaybeNotify:
    def test_notifies_on_expiry(self):
        client = MagicMock()
        results = [
            SecretCheckResult("groq", configured=True, ok=False, status_code=401, detail="401"),
        ]
        notified = maybe_notify(results, client)
        assert notified is True
        client.send_alert.assert_called_once()
        args, _ = client.send_alert.call_args
        assert args[0] == NotificationLevel.WARNING

    def test_no_notify_when_all_ok(self):
        client = MagicMock()
        results = [
            SecretCheckResult("groq", configured=True, ok=True, status_code=200, detail="ok"),
        ]
        notified = maybe_notify(results, client)
        assert notified is False
        client.send_alert.assert_not_called()
