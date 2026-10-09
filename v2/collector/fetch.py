"""HTTP 取得。robots.txt 遵守、同一ホストへの間隔、文字コード判定、同一 URL のキャッシュ。"""

from __future__ import annotations

import logging

import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import UnicodeDammit

from .errors import ErrorInfo, classify_exception, host_of

log = logging.getLogger(__name__)
WAIT_FOR_MS = 20000   # render の wait_for がセレクタを待つ上限（ミリ秒）
USER_AGENT = "oneco-collector/2.0 (+https://github.com/9mak/oneco; stop/removal requests via GitHub Issues)"
_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9_\-]+)", re.I)
# get で取り直す一過性の失敗 = 確立済みの接続をサーバーが閉じた／切った種類だけ。
# 熊本県動物愛護センターは Keep-Alive: timeout=1 で delay（1 秒）とほぼ同じため、使い回した接続が送信の瞬間に閉じられ
# RemoteProtocolError「Server disconnected without sending a response」になる（2026-10-04・10-05 の全件収集で -2・-6 が失敗）。
# ConnectError（DNS 不達・回線断）とタイムアウトは取り直さない: 回線断の日（10/4 は 119/229 が ConnectError）に
# 1 ページ 7 秒ずつ全体が長引くだけで、その日は latest.json を据え置くため得るものが無い。5xx は実績が無いので入れない。
RETRY_ERRORS: tuple[type[httpx.HTTPError], ...] = (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)
RETRY_WAITS: tuple[float, ...] = (2.0, 5.0)   # 再試行前の待ち（秒）。要素数 = 再試行の回数


class FetchError(Exception):
    """取得の失敗。info（ErrorInfo）に kind / status / host / phase を持つ。文字列は表示用。"""

    def __init__(self, message: str, info: ErrorInfo | None = None) -> None:
        super().__init__(message)
        self.info = info or ErrorInfo("other")


_GONE = re.compile(r"HTTP (404|410): ")


def page_gone(e: FetchError) -> bool:
    """ページが無い（HTTP 404・410）ことによる失敗か。サーバーエラー・接続失敗・robots 拒否は False。"""
    info = getattr(e, "info", None)
    if info is not None and info.kind == "http":
        return info.status in (404, 410)
    return bool(_GONE.match(str(e)))


@dataclass
class Page:
    url: str          # 要求した URL
    final_url: str    # リダイレクト後
    status: int
    content: bytes
    html: str | None  # テキストとして解釈できたもの（PDF 等は None）
    content_type: str
    captured: list[Any] = field(default_factory=list)   # render(capture=…) で捕まえた JSON 応答


def decode(content: bytes, header_charset: str | None, forced: str | None = None) -> str:
    if forced:
        return content.decode(forced, errors="replace")
    m = _META_CHARSET.search(content[:4096])
    for enc in (m.group(1).decode() if m else None, header_charset):
        if not enc:
            continue
        try:
            return content.decode(enc.lower().replace("shift-jis", "shift_jis").replace("x-sjis", "shift_jis"))
        except (LookupError, UnicodeDecodeError):
            continue
    return UnicodeDammit(content).unicode_markup or content.decode("utf-8", errors="replace")


class Fetcher:
    def __init__(self, delay: float = 1.0, timeout: float = 30.0, respect_robots: bool = True,
                 retry_waits: tuple[float, ...] = RETRY_WAITS) -> None:
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
        self.delay = delay
        self.respect_robots = respect_robots
        self.retry_waits = retry_waits
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.cache: dict[str, Page] = {}

    # --- politeness -------------------------------------------------------
    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        wait = self._last.get(host, 0) + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(base + "/robots.txt")
                if r.status_code >= 400:
                    self._robots[base] = None
                else:
                    rp.parse(r.text.splitlines())
                    self._robots[base] = rp
            except httpx.HTTPError:
                self._robots[base] = None
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(USER_AGENT, url)

    # --- fetch ------------------------------------------------------------
    def get(self, url: str, encoding: str | None = None) -> Page:
        key = (url, encoding)
        if key in self.cache:
            return self.cache[key]
        if not self._allowed(url):
            raise FetchError(f"robots.txt により拒否: {url}", ErrorInfo("robots", host=host_of(url), url=url))
        r = self._get_with_retry(url)
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code}: {url}",
                             ErrorInfo("http", status=r.status_code, host=host_of(url), url=url))
        ctype = r.headers.get("content-type", "")
        html = None
        if "pdf" not in ctype and not url.lower().endswith(".pdf"):
            html = decode(r.content, r.charset_encoding, encoding)
        page = Page(url, str(r.url), r.status_code, r.content, html, ctype)
        self.cache[key] = page
        return page

    def _get_with_retry(self, url: str) -> httpx.Response:
        """RETRY_ERRORS の失敗だけ、retry_waits の秒数を待って取り直す（取り直しは httpx が新しい接続で行う）。"""
        waits = list(self.retry_waits)
        attempt = 1
        while True:
            self._throttle(url)
            try:
                return self.client.get(url)
            except RETRY_ERRORS as e:
                if not waits:
                    raise FetchError(f"{type(e).__name__}: {e}", classify_exception(e, url, attempt=attempt)) from e
                log.info("get: %s のため %.0f 秒後に取り直す: %s", type(e).__name__, waits[0], url)
                time.sleep(waits.pop(0))
                attempt += 1
            except httpx.HTTPError as e:
                raise FetchError(f"{type(e).__name__}: {e}", classify_exception(e, url, attempt=attempt)) from e

    def render(self, url: str, wait_ms: int = 3000, capture: str | None = None, wait_for: str | None = None) -> Page:
        """JavaScript 描画が必要なページを Playwright で取る。

        capture に URL の一部（例 "elasticsearch/search"）を渡すと、描画中にその URL へ返ってきた
        JSON 応答を Page.captured に集める（Bubble 製 SPA のように一覧が API 応答にしか無いサイト用）。
        wait_for にセレクタを渡すと、networkidle の後にその要素が現れるまで（最長 WAIT_FOR_MS）待ってから HTML を取る。
        一覧を jQuery が後から組み立てるサイト（高松市）で、networkidle 直後は見出し行だけ、という取りこぼしを防ぐ。
        現れなければ待ち切って、その時点の HTML で続ける（0 頭の日は empty_text が拾う）。
        """
        key = (url, "render", capture, wait_for)
        if key in self.cache:
            return self.cache[key]
        if not self._allowed(url):
            raise FetchError(f"robots.txt により拒否: {url}", ErrorInfo("robots", host=host_of(url), url=url, phase="render"))
        from playwright.sync_api import sync_playwright

        self._throttle(url)
        captured: list[Any] = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                if capture:
                    def _on_response(r):  # noqa: ANN001
                        if capture in r.url:
                            try:
                                captured.append(r.json())
                            except Exception:  # noqa: BLE001 — JSON でない応答は無視
                                pass

                    page.on("response", _on_response)
                page.goto(url, wait_until="networkidle", timeout=60000)
                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=WAIT_FOR_MS)
                    except Exception:  # noqa: BLE001 — PlaywrightTimeoutError。現れない日はそのまま続ける
                        log.info("render: wait_for '%s' が %d ms 待っても現れない: %s", wait_for, WAIT_FOR_MS, url)
                page.wait_for_timeout(wait_ms)
                html = page.content()
                final = page.url
            finally:
                browser.close()
        res = Page(url, final, 200, html.encode("utf-8"), html, "text/html; rendered", captured)
        self.cache[key] = res
        return res


class FakeFetcher(Fetcher):
    """テスト用。URL → HTML/bytes の辞書だけを返す。captures は URL → render 中に捕まえたことにする JSON の列。"""

    def __init__(self, pages: dict[str, str | bytes], redirects: dict[str, str] | None = None,
                 captures: dict[str, list[Any]] | None = None, status: dict[str, int] | None = None) -> None:
        super().__init__(delay=0, respect_robots=False)
        self.pages = pages
        self.redirects = redirects or {}
        self.captures = captures or {}
        self.status = status or {}      # URL → HTTP ステータス（400 以上なら本物の Fetcher と同じ「HTTP 404: URL」で失敗する）
        self.render_calls: list[tuple[str, str | None]] = []

    def get(self, url: str, encoding: str | None = None) -> Page:
        if self.status.get(url, 200) >= 400:
            raise FetchError(f"HTTP {self.status[url]}: {url}", ErrorInfo("http", status=self.status[url], host=host_of(url), url=url))
        if url not in self.pages:
            raise FetchError(f"FakeFetcher に無い URL: {url}", ErrorInfo("connect", host=host_of(url), url=url))
        body = self.pages[url]
        final = self.redirects.get(url, url)
        if isinstance(body, bytes):
            is_pdf = body[:5] == b"%PDF-"
            return Page(url, final, 200, body, None if is_pdf else decode(body, None, encoding), "application/pdf" if is_pdf else "text/html")
        return Page(url, final, 200, body.encode("utf-8"), body, "text/html")

    def render(self, url: str, wait_ms: int = 0, capture: str | None = None, wait_for: str | None = None) -> Page:
        self.render_calls.append((url, capture) if wait_for is None else (url, capture, wait_for))
        page = self.get(url)
        page.captured = list(self.captures.get(url, [])) if capture else []
        return page
