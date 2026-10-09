"""W006 T602（再試行の表・Retry-After・backoff・予算）と T604（200 応答の検証）。ネットワークなし。"""

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from collector import fetch as fetch_mod
from collector.errors import ErrorInfo
from collector.fetch import Fetcher, FetchError, Page, validate_response

URL = "https://www.city.example.lg.jp/animals/list.html"
BODY = "<html><head><title>収容動物一覧</title></head><body><h1>収容動物</h1>" + "<p>犬猫の情報</p>" * 60 + "</body></html>"


def _fetcher(script: list, headers_for_ok: dict | None = None) -> tuple[Fetcher, list[str]]:
    """script を先頭から 1 回ずつ消費（Exception は raise、int は status、httpx.Response はそのまま）。尽きたら 200。"""
    calls: list[str] = []
    queue = list(script)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if queue:
            e = queue.pop(0)
            if isinstance(e, Exception):
                raise e
            if isinstance(e, httpx.Response):
                e.request = request
                return e
            return httpx.Response(e, request=request)
        return httpx.Response(200, content=BODY.encode(), request=request,
                              headers=headers_for_ok or {"content-type": "text/html; charset=UTF-8"})

    f = Fetcher(delay=0, respect_robots=False)
    f.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return f, calls


@pytest.fixture
def sleeps(monkeypatch):
    s: list[float] = []
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda x: s.append(x))
    monkeypatch.setattr(fetch_mod.random, "uniform", lambda a, b: b)   # ジッタは上限値に固定
    return s


# --- T602 -----------------------------------------------------------------
def test_default_timeout_is_split():
    t = Fetcher(delay=0, respect_robots=False).client.timeout
    assert (t.connect, t.read, t.write, t.pool) == (10.0, 30.0, 10.0, 10.0)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 408])
def test_retryable_statuses_are_retried(status, sleeps):
    f, calls = _fetcher([status])
    assert f.get(URL).status == 200
    assert len(calls) == 2


@pytest.mark.parametrize("status", [404, 410, 401, 403, 451, 400])
def test_other_4xx_not_retried(status, sleeps):
    f, calls = _fetcher([status])
    with pytest.raises(FetchError) as ei:
        f.get(URL)
    assert len(calls) == 1 and ei.value.info.status == status and sleeps == []


@pytest.mark.parametrize("exc", [
    httpx.ConnectError("[Errno 61] Connection refused"), httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"),
    httpx.WriteTimeout("t"), httpx.PoolTimeout("t"), httpx.RemoteProtocolError("x"), httpx.ReadError("x"),
    httpx.WriteError("x")])
def test_retryable_exceptions(exc, sleeps):
    f, calls = _fetcher([exc])
    assert f.get(URL).status == 200
    assert len(calls) == 2


@pytest.mark.parametrize("msg", ["[Errno 8] nodename nor servname provided, or not known",
                                 "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"])
def test_dns_and_tls_not_retried(msg, sleeps):
    f, calls = _fetcher([httpx.ConnectError(msg)])
    with pytest.raises(FetchError):
        f.get(URL)
    assert len(calls) == 1


def test_timeout_is_retried_now(sleeps):
    """方針変更: 以前は timeout を再試行しなかったが、connect/read の分離と回数・待ち時間の上限（4 回・45 秒）を入れたので再試行する。"""
    f, calls = _fetcher([httpx.ReadTimeout("t"), httpx.ReadTimeout("t")])
    assert f.get(URL).status == 200
    assert len(calls) == 3


def test_max_attempts_is_4_and_attempt_recorded(sleeps):
    f, calls = _fetcher([503] * 10)
    with pytest.raises(FetchError) as ei:
        f.get(URL)
    assert len(calls) == 4
    assert ei.value.info.attempt == 4 and ei.value.info.kind == "http" and ei.value.info.status == 503
    assert len(sleeps) == 3


def test_exception_exhaustion_records_attempt(sleeps):
    f, calls = _fetcher([httpx.ReadTimeout("t")] * 10)
    with pytest.raises(FetchError) as ei:
        f.get(URL)
    assert len(calls) == 4 and ei.value.info.kind == "timeout" and ei.value.info.attempt == 4


def test_full_jitter_backoff_bounds(sleeps, monkeypatch):
    seen: list[tuple[float, float]] = []

    def uni(a, b):
        seen.append((a, b))
        return b

    monkeypatch.setattr(fetch_mod.random, "uniform", uni)
    f, _ = _fetcher([503, 503, 503])
    f.get(URL)
    assert seen == [(0, 2.0), (0, 4.0), (0, 8.0)]
    assert sleeps == [2.0, 4.0, 8.0]


def test_backoff_cap():
    assert fetch_mod.backoff_seconds(0) <= 2.0
    assert fetch_mod.backoff_seconds(10) <= 20.0


def test_retry_after_seconds_preferred(sleeps):
    f, calls = _fetcher([httpx.Response(429, headers={"Retry-After": "7"})])
    f.get(URL)
    assert sleeps == [7.0] and len(calls) == 2


def test_retry_after_http_date(sleeps):
    when = datetime.now(UTC) + timedelta(seconds=30)
    f, _ = _fetcher([httpx.Response(503, headers={"Retry-After": format_datetime(when, usegmt=True)})])
    f.get(URL)
    assert 25 <= sleeps[0] <= 31


def test_retry_after_over_max_fails_without_retry(sleeps):
    f, calls = _fetcher([httpx.Response(503, headers={"Retry-After": "120"})])
    with pytest.raises(FetchError) as ei:
        f.get(URL)
    assert len(calls) == 1 and sleeps == [] and ei.value.info.retry_after == 120.0 and ei.value.info.status == 503


def test_retry_budget_cuts_off(sleeps):
    f, calls = _fetcher([httpx.Response(429, headers={"Retry-After": "40"}), httpx.Response(429, headers={"Retry-After": "40"})])
    with pytest.raises(FetchError):
        f.get(URL)
    assert len(calls) == 2 and sleeps == [40.0]        # 2 回目の 40 秒は合計 45 秒を超えるので待たない


def test_retry_status_table():
    assert fetch_mod.RETRY_STATUSES == frozenset({429, 500, 502, 503, 504, 408})


# --- T604 -----------------------------------------------------------------
def _page(body: str | bytes = BODY, ctype="text/html; charset=UTF-8", url=URL, final=None) -> Page:
    raw = body.encode() if isinstance(body, str) else body
    is_pdf = raw[:5] == b"%PDF-"
    return Page(url, final or url, 200, raw, None if is_pdf else raw.decode("utf-8", "replace"), ctype)


def test_valid_page_passes():
    assert validate_response(_page()) is None


@pytest.mark.parametrize("final", [
    "https://city.example.lg.jp/animals/list.html",         # www. の有無
    "https://www2.city.example.lg.jp/animals/",             # 同一登録ドメイン配下
])
def test_redirect_allowed(final):
    assert validate_response(_page(url="https://www.city.example.lg.jp/a", final=final)) is None


def test_redirect_to_other_host():
    info = validate_response(_page(final="https://other.example.com/"))
    assert info is not None and info.kind == "redirect" and info.status == 200 and info.host == "www.city.example.lg.jp"
    assert info.url == URL and info.phase == "fetch"


def test_redirect_to_other_registrable_under_lg_jp():
    info = validate_response(_page(url="https://www.city.a.lg.jp/", final="https://www.city.b.lg.jp/"))
    assert info is not None and info.kind == "redirect"


@pytest.mark.parametrize("ctype", ["text/html", "application/xhtml+xml", "text/plain", "application/json"])
def test_allowed_content_types(ctype):
    assert validate_response(_page(ctype=ctype)) is None


def test_bad_content_type():
    info = validate_response(_page(ctype="image/png"))
    assert info is not None and info.kind == "content"


def test_octet_stream_ok_for_pdf_url_only():
    pdf = b"%PDF-1.4 " + b"x" * 100
    assert validate_response(_page(pdf, ctype="application/octet-stream", url="https://a.example.jp/x.pdf")) is None
    info = validate_response(_page(BODY, ctype="application/octet-stream"))
    assert info is not None and info.kind == "content"


def test_pdf_must_start_with_magic():
    assert validate_response(_page(b"%PDF-1.7 abc", ctype="application/pdf")) is None
    info = validate_response(_page(b"<html>not pdf</html>", ctype="application/pdf"))
    assert info is not None and info.kind == "content"


def test_empty_shell_html():
    info = validate_response(_page("<html><body></body></html>"))
    assert info is not None and info.kind == "content"


@pytest.mark.parametrize("marker", ["メンテナンス中", "サービス停止中", "システムメンテナンス", "Service Unavailable",
                                    "Access Denied", "アクセスが拒否", "CAPTCHA", "Just a moment...",
                                    "ただいまアクセスが集中", "Checking your browser"])
def test_maintenance_in_title(marker):
    body = f"<html><head><title>{marker}</title></head><body>" + "<p>x</p>" * 100 + "</body></html>"
    info = validate_response(_page(body))
    assert info is not None and info.kind == "content"


def test_maintenance_in_h1():
    body = "<html><head><title>市</title></head><body><h1>ただいまメンテナンス中です</h1>" + "<p>x</p>" * 100 + "</body></html>"
    assert validate_response(_page(body)) is not None


@pytest.mark.parametrize("marker", ["cf-browser-verification", "Incapsula"])
def test_machine_markers_in_head_of_body(marker):
    body = f"<html><head><title>市</title></head><body><div id='{marker}'></div>" + "<p>x</p>" * 100 + "</body></html>"
    assert validate_response(_page(body)) is not None


def test_word_only_in_body_text_is_not_flagged():
    body = BODY.replace("犬猫の情報", "メンテナンス中の施設の案内", 1)
    assert validate_response(_page(body)) is None


def test_get_raises_fetcherror_with_info(sleeps):
    f, calls = _fetcher([], headers_for_ok={"content-type": "image/png"})
    with pytest.raises(FetchError, match="取得不能: .*: " + URL) as ei:
        f.get(URL)
    i: ErrorInfo = ei.value.info
    assert (i.kind, i.status, i.host, i.url, i.phase) == ("content", 200, "www.city.example.lg.jp", URL, "fetch")
    assert not f.cache and len(calls) == 1


def test_get_redirect_to_other_host_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.city.example.lg.jp":
            return httpx.Response(302, headers={"location": "https://evil.example.com/x"}, request=request)
        return httpx.Response(200, content=BODY.encode(), headers={"content-type": "text/html"}, request=request)

    f = Fetcher(delay=0, respect_robots=False)
    f.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(FetchError) as ei:
        f.get(URL)
    assert ei.value.info.kind == "redirect"


def test_render_result_is_validated_too():
    shell = "<html><title>Just a moment...</title></html>" + " " * 600
    info = validate_response(Page(URL, URL, 200, shell.encode(), shell, "text/html; rendered"), phase="render")
    assert info is not None and info.kind == "content" and info.phase == "render"
    assert validate_response(Page(URL, URL, 200, BODY.encode(), BODY, "text/html; rendered"), phase="render") is None
    bad = validate_response(Page(URL, "https://x.example.com/", 200, BODY.encode(), BODY, "text/html; rendered"), phase="render")
    assert bad is not None and bad.kind == "redirect"
