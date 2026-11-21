"""W006 T656 付随・項目 4・5: fetch.py の render() の HTTP エラーと、get()・post() の PDF 判定（2026-11-20）。

項目 4: render() は 404・410 だけを取得失敗にし、403・429・5xx は status 200 の成功として返していた
  （本文が保守ページの語を含まなければ、そのまま「読めない」ではなく parser 失敗に分類され、ホスト遮断・AI 修復の判定にも乗らない）。
項目 5: get()・post() は Content-Type に小文字の "pdf" がなく、URL が ".pdf" で終わらなければ HTML として decode する。
  大文字の Content-Type（Application/PDF）やクエリ付きの URL（dog.pdf?v=2）の PDF が、html に文字化けの文字列が入った
  Page になり、Executor は html が None のときだけ PDF とみなすので、PDF が HTML 文書として読まれていた。
"""

import httpx
import pytest
from collector import fetch as fetch_mod
from collector.fetch import Fetcher, FetchError
from test_repair_gate_t635 import _fake_playwright

PDF = b"%PDF-1.4\n" + b"\x80\x81\xfe\xff binary " * 80


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda s: None)


def _fetcher(ctype: str | None, body: bytes = PDF) -> Fetcher:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": ctype} if ctype is not None else {}
        return httpx.Response(200, content=body, headers=headers, request=request)

    f = Fetcher(delay=0, respect_robots=False)
    f.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return f


# --- 項目 4: render() の HTTP エラー --------------------------------------------------
@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503])
def test_render_http_errors_are_fetch_failures(monkeypatch, status):
    browser = _fake_playwright(monkeypatch, status)
    with pytest.raises(FetchError) as ei:
        Fetcher(delay=0, respect_robots=False).render("https://a.jp/x")
    info = ei.value.info
    assert (info.kind, info.status, info.phase, info.url) == ("http", status, "render", "https://a.jp/x")
    assert f"HTTP {status}: https://a.jp/x" in str(ei.value)
    assert browser.closed is True


@pytest.mark.parametrize("status", [200, 204, 301, 304, None])
def test_render_non_error_statuses_still_work(monkeypatch, status):
    _fake_playwright(monkeypatch, status)
    assert "本文です" in Fetcher(delay=0, respect_robots=False).render("https://a.jp/x").html


def test_render_5xx_trips_the_host_breaker_like_get():
    """render の 5xx は get と同じ error_info（kind=http・status>=500）になるので、ホスト遮断の数え対象（run._is_trip_failure）に乗る。"""
    from collector.errors import ErrorInfo
    from collector.run import _is_trip_failure

    assert _is_trip_failure(ErrorInfo("http", status=503, phase="render").to_dict())


# --- 項目 5: PDF の判定 ---------------------------------------------------------------
@pytest.mark.parametrize("ctype,url", [
    ("Application/PDF", "https://a.jp/list"),
    ("APPLICATION/PDF; charset=binary", "https://a.jp/list"),
    ("application/pdf", "https://a.jp/list"),
    ("application/octet-stream", "https://a.jp/dog.pdf?v=2"),
    ("application/octet-stream", "https://a.jp/dog.PDF?v=2&x=1#top"),
    ("application/pdf", "https://a.jp/dog.pdf?v=2"),
    ("application/octet-stream", "https://a.jp/dog.pdf"),
])
def test_get_treats_pdf_as_pdf(ctype, url):
    page = _fetcher(ctype).get(url)
    assert page.html is None and page.content == PDF


@pytest.mark.parametrize("ctype", ["Application/PDF", "application/pdf", "APPLICATION/PDF"])
def test_post_treats_pdf_as_pdf(ctype):
    page = _fetcher(ctype).post("https://a.jp/search", {"q": "1"})
    assert page.html is None and page.content == PDF


def test_get_html_is_still_decoded_and_a_pdf_word_in_the_query_is_not_a_pdf():
    html = "<html><head><title>一覧</title></head><body>" + "<p>犬 pdf</p>" * 100 + "</body></html>"
    page = _fetcher("text/html; charset=UTF-8", html.encode()).get("https://a.jp/list?type=pdf&from=a.pdf.html")
    assert page.html is not None and "犬" in page.html
