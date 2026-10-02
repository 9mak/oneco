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

log = logging.getLogger(__name__)
WAIT_FOR_MS = 20000   # render の wait_for がセレクタを待つ上限（ミリ秒）
USER_AGENT = "oneco-collector/2.0 (+https://github.com/9mak/oneco; stop/removal requests via GitHub Issues)"
_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9_\-]+)", re.I)


class FetchError(Exception):
    pass


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
    def __init__(self, delay: float = 1.0, timeout: float = 30.0, respect_robots: bool = True) -> None:
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
        self.delay = delay
        self.respect_robots = respect_robots
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
            raise FetchError(f"robots.txt により拒否: {url}")
        self._throttle(url)
        try:
            r = self.client.get(url)
        except httpx.HTTPError as e:
            raise FetchError(f"{type(e).__name__}: {e}") from e
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code}: {url}")
        ctype = r.headers.get("content-type", "")
        html = None
        if "pdf" not in ctype and not url.lower().endswith(".pdf"):
            html = decode(r.content, r.charset_encoding, encoding)
        page = Page(url, str(r.url), r.status_code, r.content, html, ctype)
        self.cache[key] = page
        return page

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
            raise FetchError(f"robots.txt により拒否: {url}")
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
                 captures: dict[str, list[Any]] | None = None) -> None:
        super().__init__(delay=0, respect_robots=False)
        self.pages = pages
        self.redirects = redirects or {}
        self.captures = captures or {}
        self.render_calls: list[tuple[str, str | None]] = []

    def get(self, url: str, encoding: str | None = None) -> Page:
        if url not in self.pages:
            raise FetchError(f"FakeFetcher に無い URL: {url}")
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
