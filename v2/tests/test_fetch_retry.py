"""T517 ⑩ Fetcher.get の再試行（ネットワークなし。httpx.MockTransport で応答を差し替える）。

熊本県動物愛護センター（www.kumamoto-doubutuaigo.jp）は Keep-Alive: timeout=1 で、同一ホストの間隔（delay 1.0 秒）と
ほぼ同じ。前の応答から 0.99 秒前後あけて同じ接続を使い回すと、送った瞬間にサーバーが接続を閉じて
RemoteProtocolError「Server disconnected without sending a response」になる（2026-10-05 に実ページで再現）。
新しい接続で取り直せば通るので、確立済みの接続が切られた種類だけ再試行する。
ConnectError（DNS 不達・回線断）とタイムアウトは再試行しない（回線断の日に全体が長引くだけで、latest.json はどうせ据え置き）。
"""

import httpx
import pytest

from collector import fetch as fetch_mod
from collector.fetch import FetchError, Fetcher

URL = "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:2/animal_id:2"
HTML = "<html><body><ul class='list-4col'><li>猫</li></ul></body></html>"


def _fetcher(errors: list[Exception | int], retry_waits: tuple[float, ...] | None = (0, 0)) -> tuple[Fetcher, list[str]]:
    """errors を先頭から 1 回ずつ起こし（int は HTTP ステータス）、尽きたら 200 を返す Fetcher と、受けた要求の記録。"""
    calls: list[str] = []
    queue = list(errors)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if queue:
            e = queue.pop(0)
            if isinstance(e, int):
                return httpx.Response(e, request=request)
            raise e
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=UTF-8"}, request=request)

    kw = {} if retry_waits is None else {"retry_waits": retry_waits}
    f = Fetcher(delay=0, respect_robots=False, **kw)
    f.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return f, calls


def _disconnected() -> httpx.RemoteProtocolError:
    return httpx.RemoteProtocolError("Server disconnected without sending a response.")


def test_retries_server_disconnect_and_succeeds():
    f, calls = _fetcher([_disconnected()])
    page = f.get(URL)
    assert page.status == 200 and "猫" in page.html
    assert len(calls) == 2                                   # 1 回切られて、取り直しで通る


def test_retries_read_error_too():
    f, calls = _fetcher([httpx.ReadError("[Errno 54] Connection reset by peer")])
    assert f.get(URL).status == 200
    assert len(calls) == 2


def test_gives_up_after_two_retries_with_the_original_message():
    f, calls = _fetcher([_disconnected(), _disconnected(), _disconnected(), _disconnected()])
    with pytest.raises(FetchError, match="RemoteProtocolError: Server disconnected"):
        f.get(URL)
    assert len(calls) == 3                                   # 最初の 1 回 + 再試行 2 回まで


def test_connect_error_is_not_retried():
    f, calls = _fetcher([httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known")])
    with pytest.raises(FetchError, match="ConnectError"):
        f.get(URL)
    assert len(calls) == 1                                   # 回線断の日（10/4 は 119/229）に全体を長引かせない


def test_timeout_is_not_retried():
    f, calls = _fetcher([httpx.ReadTimeout("timed out")])
    with pytest.raises(FetchError, match="ReadTimeout"):
        f.get(URL)
    assert len(calls) == 1                                   # 30 秒待ちを繰り返さない


def test_http_error_status_is_not_retried():
    f, calls = _fetcher([503])
    with pytest.raises(FetchError, match="HTTP 503"):
        f.get(URL)
    assert len(calls) == 1                                   # 5xx は実績が無いので今は再試行しない


def test_default_waits_are_2_then_5_seconds(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: slept.append(s))
    f, calls = _fetcher([_disconnected(), _disconnected()], retry_waits=None)
    assert f.get(URL).status == 200
    assert len(calls) == 3
    assert slept == [2.0, 5.0]                               # delay=0 なので throttle の待ちは混ざらない


def test_retry_result_is_cached_like_a_normal_fetch():
    f, calls = _fetcher([_disconnected()])
    f.get(URL)
    f.get(URL)
    assert len(calls) == 2                                   # 2 回目の get はキャッシュから（取り直しは 1 回だけ）
