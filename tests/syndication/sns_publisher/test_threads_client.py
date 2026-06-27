"""Threads API client TDD (Meta Graph API ラッパー)

design.md 5.5 準拠。requests 直叩き。OAuth long-lived access token を引数で受ける。

Threads の投稿は 2 段:
  1. POST /{user_id}/threads (container 作成、media_type=TEXT/IMAGE)
  2. POST /{user_id}/threads_publish (creation_id を渡して publish)

実 API は叩かず、Session を mock する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from syndication_service.sns_publisher.threads_client import (
    ThreadsClient,
    ThreadsPostError,
    _redact_token,
)

_TEST_BASE = "https://graph.threads.net/v1.0"
_USER_ID = "1234567890"
_TOKEN = "test_access_token"


def _mock_response(json_data: dict, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status
    resp.text = str(json_data)
    if status >= 400:
        from requests.exceptions import HTTPError

        resp.raise_for_status.side_effect = HTTPError(f"{status} error")
    return resp


def _mock_session(responses: list[MagicMock]) -> MagicMock:
    """post() が responses を順番に返す mock session。

    container status の GET はデフォルトで FINISHED を返す (ポーリング即完了)。
    遷移を検証したいテストは sess.get.side_effect を上書きする。
    """
    sess = MagicMock()
    sess.post.side_effect = responses
    sess.get.return_value = _mock_response({"status": "FINISHED"})
    return sess


def _client(session: MagicMock, **kwargs) -> ThreadsClient:
    # sleep はデフォルト no-op (ポーリングテストでハングしない)。
    kwargs.setdefault("sleep", lambda _s: None)
    return ThreadsClient(
        user_id=_USER_ID,
        access_token=_TOKEN,
        session=session,
        base_url=_TEST_BASE,
        timeout=5.0,
        **kwargs,
    )


class TestSuccess:
    def test_text_only_post_returns_published_id(self):
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"id": "published_xyz"}),
            ]
        )
        client = _client(session)
        published_id = client.post("こんにちは Threads")
        assert published_id == "published_xyz"
        assert session.post.call_count == 2

    def test_create_container_called_with_correct_url_and_params(self):
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"id": "published_xyz"}),
            ]
        )
        client = _client(session)
        client.post("テスト投稿")
        first_call = session.post.call_args_list[0]
        # URL: /{user_id}/threads
        assert first_call.args[0] == f"{_TEST_BASE}/{_USER_ID}/threads"
        # params: access_token / text / media_type=TEXT
        params = first_call.kwargs.get("params") or first_call.kwargs.get("data") or {}
        assert params.get("access_token") == _TOKEN
        assert params.get("text") == "テスト投稿"
        assert params.get("media_type") == "TEXT"
        # timeout 設定が伝わる
        assert first_call.kwargs.get("timeout") == 5.0

    def test_publish_called_with_creation_id(self):
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"id": "published_xyz"}),
            ]
        )
        client = _client(session)
        client.post("hi")
        second_call = session.post.call_args_list[1]
        assert second_call.args[0] == f"{_TEST_BASE}/{_USER_ID}/threads_publish"
        params = second_call.kwargs.get("params") or second_call.kwargs.get("data") or {}
        assert params.get("creation_id") == "container_abc"
        assert params.get("access_token") == _TOKEN

    def test_image_post_includes_image_url(self):
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"id": "published_xyz"}),
            ]
        )
        client = _client(session)
        published_id = client.post("保護犬さん", image_url="https://example.jp/img/1.jpg")
        assert published_id == "published_xyz"
        first_call = session.post.call_args_list[0]
        params = first_call.kwargs.get("params") or first_call.kwargs.get("data") or {}
        assert params.get("media_type") == "IMAGE"
        assert params.get("image_url") == "https://example.jp/img/1.jpg"


class TestFailure:
    def test_container_creation_http_error_raises(self):
        session = _mock_session([_mock_response({"error": "bad"}, status=400)])
        client = _client(session)
        with pytest.raises(ThreadsPostError):
            client.post("hi")
        # publish は呼ばれない (container 段階で失敗)
        assert session.post.call_count == 1

    def test_container_missing_id_raises(self):
        session = _mock_session([_mock_response({"foo": "bar"})])
        client = _client(session)
        with pytest.raises(ThreadsPostError) as exc:
            client.post("hi")
        assert "container" in str(exc.value).lower() or "id" in str(exc.value).lower()

    def test_publish_http_error_raises(self):
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"error": "rate limit"}, status=429),
            ]
        )
        client = _client(session)
        with pytest.raises(ThreadsPostError):
            client.post("hi")

    def test_publish_missing_id_raises(self):
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"foo": "bar"}),
            ]
        )
        client = _client(session)
        with pytest.raises(ThreadsPostError):
            client.post("hi")


class TestConstructor:
    def test_missing_token_raises(self):
        with pytest.raises(ValueError):
            ThreadsClient(user_id=_USER_ID, access_token="")

    def test_missing_user_id_raises(self):
        with pytest.raises(ValueError):
            ThreadsClient(user_id="", access_token=_TOKEN)


class TestPublisherCompat:
    """publisher.publish_one が呼ぶシグネチャ post(text, candidate=...) との互換"""

    def test_post_accepts_candidate_kwarg(self):
        """publisher は threads_client.post(final_text, candidate=candidate) で呼ぶ。
        candidate kwarg は無視して構わないが、TypeError は出ないこと。"""
        session = _mock_session(
            [
                _mock_response({"id": "container_abc"}),
                _mock_response({"id": "published_xyz"}),
            ]
        )
        client = _client(session)
        published_id = client.post("hi", candidate=MagicMock())
        assert published_id == "published_xyz"


class TestRedactToken:
    """access_token がエラーメッセージ経由でログに漏れないこと (全体監査 2026-06-24)"""

    def test_redact_helper_masks_token_value(self):
        msg = "for url: https://graph.threads.net/v1.0/1/threads?access_token=SECRET123&text=hi"
        redacted = _redact_token(msg)
        assert "SECRET123" not in redacted
        assert "access_token=<redacted>" in redacted
        # token 以外のクエリは保持される (デバッグ可能性を残す)
        assert "text=hi" in redacted

    def test_redact_helper_noop_without_token(self):
        msg = "publish failed: 500 Server Error"
        assert _redact_token(msg) == msg

    def _session_raising_real_http_error(self, *, container_ok: bool) -> MagicMock:
        """requests の実挙動を再現: 4xx 時に解決済み URL (token 入り) を
        メッセージに持つ本物の HTTPError を raise_for_status() で投げさせる。

        手書き文字列ではなく requests.Response.raise_for_status() に投げさせる
        ことで「requests が URL に token を載せる」という前提自体を固定する。
        """
        sess = MagicMock()
        # container status ポーリングは FINISHED で即通過させ、publish 段に到達させる
        sess.get.return_value = _mock_response({"status": "FINISHED"})

        def _make_403_response(path: str) -> requests.Response:
            resp = requests.Response()
            resp.status_code = 403
            resp.reason = "Forbidden"
            # requests は params を URL にマージするため、解決済み URL に token が載る
            resp.url = (
                f"{_TEST_BASE}/{_USER_ID}/{path}?access_token={_TOKEN}&text=hi&media_type=TEXT"
            )
            return resp

        if container_ok:
            ok = MagicMock()
            ok.json.return_value = {"id": "container_abc"}
            ok.status_code = 200
            ok.raise_for_status.return_value = None
            sess.post.side_effect = [ok, _make_403_response("threads_publish")]
        else:
            sess.post.side_effect = [_make_403_response("threads")]
        return sess

    def test_container_http_error_does_not_leak_token(self):
        """container 作成段の HTTP エラーで token が ThreadsPostError に載らない"""
        session = self._session_raising_real_http_error(container_ok=False)
        client = _client(session)
        with pytest.raises(ThreadsPostError) as exc:
            client.post("hi")
        # 前提確認: 素の requests なら token が漏れるはずのメッセージ形
        assert "access_token=" in str(exc.value)
        # 修正後: 生の token 値は伏字化されている
        assert _TOKEN not in str(exc.value)
        assert "<redacted>" in str(exc.value)

    def test_publish_http_error_does_not_leak_token(self):
        """publish 段の HTTP エラーでも token が漏れない"""
        session = self._session_raising_real_http_error(container_ok=True)
        client = _client(session)
        with pytest.raises(ThreadsPostError) as exc:
            client.post("hi")
        assert _TOKEN not in str(exc.value)
        assert "<redacted>" in str(exc.value)


class TestContainerPolling:
    """container status ポーリング (wet 化後の間欠 400 対策・全体監査 2026-06-27)。

    Threads は container 作成後に非同期処理する。作成直後に publish すると
    status=IN_PROGRESS のまま叩いて 400 Bad Request になる間欠失敗があった。
    FINISHED を待ってから publish して安定させる。
    """

    def test_finished_immediately_publishes_without_sleep(self):
        session = _mock_session(
            [
                _mock_response({"id": "c1"}),
                _mock_response({"id": "published"}),
            ]
        )
        session.get.return_value = _mock_response({"status": "FINISHED"})
        sleep = MagicMock()
        client = _client(session, sleep=sleep)
        assert client.post("hi") == "published"
        # FINISHED 即時なので待たない
        sleep.assert_not_called()
        # create + publish の 2 回
        assert session.post.call_count == 2

    def test_in_progress_then_finished_waits_then_publishes(self):
        session = _mock_session(
            [
                _mock_response({"id": "c1"}),
                _mock_response({"id": "published"}),
            ]
        )
        session.get.side_effect = [
            _mock_response({"status": "IN_PROGRESS"}),
            _mock_response({"status": "FINISHED"}),
        ]
        sleep = MagicMock()
        client = _client(session, sleep=sleep)
        assert client.post("hi") == "published"
        assert session.get.call_count == 2
        assert sleep.call_count == 1  # IN_PROGRESS の後に 1 回待つ
        assert session.post.call_count == 2

    def test_status_check_polls_correct_container_url(self):
        session = _mock_session([_mock_response({"id": "c1"}), _mock_response({"id": "pub"})])
        session.get.return_value = _mock_response({"status": "FINISHED"})
        client = _client(session)
        client.post("hi")
        get_call = session.get.call_args
        assert get_call.args[0] == f"{_TEST_BASE}/c1"
        params = get_call.kwargs.get("params") or {}
        assert params.get("fields") == "status"
        assert params.get("access_token") == _TOKEN

    def test_error_status_raises_without_publishing(self):
        # publish が呼ばれないこと: post side_effect は container 作成の 1 件のみ
        session = _mock_session([_mock_response({"id": "c1"})])
        session.get.return_value = _mock_response({"status": "ERROR"})
        client = _client(session, sleep=MagicMock())
        with pytest.raises(ThreadsPostError) as exc:
            client.post("hi")
        assert "ERROR" in str(exc.value)
        assert session.post.call_count == 1  # publish に到達しない

    def test_expired_status_raises_without_publishing(self):
        session = _mock_session([_mock_response({"id": "c1"})])
        session.get.return_value = _mock_response({"status": "EXPIRED"})
        client = _client(session, sleep=MagicMock())
        with pytest.raises(ThreadsPostError):
            client.post("hi")
        assert session.post.call_count == 1

    def test_timeout_still_in_progress_raises_without_publishing(self):
        session = _mock_session([_mock_response({"id": "c1"})])
        session.get.return_value = _mock_response({"status": "IN_PROGRESS"})
        sleep = MagicMock()
        client = _client(session, sleep=sleep, poll_max_attempts=3)
        with pytest.raises(ThreadsPostError) as exc:
            client.post("hi")
        assert "FINISHED" in str(exc.value)
        assert session.get.call_count == 3  # 3 回試して諦める
        assert sleep.call_count == 2  # 最終試行後は待たない
        assert session.post.call_count == 1  # publish されない

    def test_status_http_error_redacts_token(self):
        session = _mock_session([_mock_response({"id": "c1"})])
        resp = requests.Response()
        resp.status_code = 403
        resp.reason = "Forbidden"
        resp.url = f"{_TEST_BASE}/c1?fields=status&access_token={_TOKEN}"
        session.get.return_value = resp
        client = _client(session, sleep=MagicMock())
        with pytest.raises(ThreadsPostError) as exc:
            client.post("hi")
        assert _TOKEN not in str(exc.value)
        assert "<redacted>" in str(exc.value)
