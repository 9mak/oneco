"""HTTP 取得。robots.txt 遵守、同一ホストへの間隔、文字コード判定、同一 URL のキャッシュ。"""

from __future__ import annotations

import logging
import random
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import UnicodeDammit

from .errors import ErrorInfo, classify_exception, host_of

log = logging.getLogger(__name__)
WAIT_FOR_MS = 20000   # render の wait_for がセレクタを待つ上限（ミリ秒）
USER_AGENT = "oneco-collector/2.0 (+https://github.com/9mak/oneco; stop/removal requests via GitHub Issues)"
_META_CHARSET = re.compile(rb"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9_\-]+)", re.I)
# --- 再試行の表（W006 T602。GET のみ）----------------------------------------
# 熊本県動物愛護センターは Keep-Alive: timeout=1 で delay（1 秒）とほぼ同じため、使い回した接続が送信の瞬間に閉じられ
# RemoteProtocolError「Server disconnected without sending a response」になる（2026-10-04・10-05 の全件収集で -2・-6 が失敗）。
# 再試行する: 下の状態コードと、接続確立前後の一過性の例外。dns・tls は直らないので再試行しない
# （回線断の日は 10/4 に 119/229 が ConnectError。DNS 不達を粘ると全体が長引くだけで、その日は latest.json を据え置く）。
# 404/410/401/403/451 などその他の 4xx は再試行しない。
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 408})
RETRY_EXCEPTIONS: tuple[type[httpx.HTTPError], ...] = (
    httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)
NO_RETRY_KINDS = frozenset({"dns", "tls"})   # ConnectError でも classify_exception がこの kind にしたものは再試行しない
MAX_ATTEMPTS = 4                # 1 URL あたりの試行回数（初回 + 再試行 3）
RETRY_BUDGET_SECONDS = 45.0     # 1 URL あたりの再試行待ちの合計の上限
RETRY_AFTER_MAX = 60.0          # Retry-After がこれを超えたら待たずに失敗（ErrorInfo.retry_after に値を残す）
BACKOFF_BASE, BACKOFF_FACTOR, BACKOFF_CAP = 2.0, 2, 20.0
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


def backoff_seconds(n: int) -> float:
    """Full Jitter（AWS Builders' Library）。n は 0 始まりの再試行番号。"""
    return random.uniform(0, min(BACKOFF_CAP, BACKOFF_BASE * BACKOFF_FACTOR**n))


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After（秒数または HTTP-date）を秒にする。読めなければ None。"""
    if not value:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


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


# --- 200 応答の検証（W006 T604）-----------------------------------------------
# 取得できたが中身が読めない（保守・CAPTCHA・空殻・別サイトへの転送）ページを 0 頭と取り違えないための判定。
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "application/pdf", "text/plain", "application/json"})
MIN_HTML_BYTES = 512
# 見出し（title・h1・h2）に出たら保守・拒否ページとみなす語。本文の任意の場所の語だけでは判定しない
# （「メンテナンス中の施設」のような通常の記述を誤検知しない）。
ERROR_PAGE_WORDS = ("メンテナンス中", "サービス停止中", "システムメンテナンス", "service unavailable", "access denied",
                    "アクセスが拒否", "captcha", "just a moment...", "ただいまアクセスが集中", "checking your browser")
# 機械が出す印は見出しに出ないので、本文先頭 2,000 文字の生 HTML で見る。
ERROR_PAGE_RAW_MARKERS = ("cf-browser-verification", "incapsula")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_HEADING = re.compile(r"<h[12][^>]*>(.*?)</h[12]>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_SECOND_LEVEL = frozenset({"co", "or", "ne", "ac", "go", "ad", "ed", "gr", "lg", "com", "net", "org", "gov", "edu"})


def _registrable(host: str) -> str:
    """登録ドメインの近似（公開サフィックス一覧は持たない）。x.lg.jp・x.co.jp は 3 ラベル、それ以外は 2 ラベル。"""
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _same_site(a: str, b: str) -> bool:
    a, b = (h.removeprefix("www.") for h in (a, b))
    return a == b or _registrable(a) == _registrable(b)


def _hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _check(page: Page, phase: str = "fetch") -> tuple[ErrorInfo, str] | None:
    """問題があれば (ErrorInfo, 理由)。無ければ None。"""
    def bad(kind: str, reason: str) -> tuple[ErrorInfo, str]:
        return ErrorInfo(kind, status=200, host=host_of(page.url), phase=phase, url=page.url), reason

    if not _same_site(_hostname(page.url), _hostname(page.final_url)):
        return bad("redirect", f"別のサイトへ転送された（{_hostname(page.final_url)}）")
    ctype = page.content_type.split(";")[0].strip().lower()
    is_pdf_url = urlsplit(page.url).path.lower().endswith(".pdf")
    rendered = "rendered" in page.content_type
    if ctype and ctype not in ALLOWED_CONTENT_TYPES and not (ctype == "application/octet-stream" and is_pdf_url):
        return bad("content", f"想定外の Content-Type（{ctype}）")
    if ctype == "application/pdf" or (ctype == "application/octet-stream" and is_pdf_url):
        if not page.content.startswith(b"%PDF-"):
            return bad("content", "PDF の中身ではない")
        return None
    if ctype in ("text/html", "application/xhtml+xml") or rendered:
        if len(page.content) < MIN_HTML_BYTES:
            return bad("content", f"本文が短すぎる（{len(page.content)} バイト）")
        text = page.html if page.html is not None else page.content.decode("utf-8", errors="replace")
        heads = [m.group(1) for m in _TITLE.finditer(text)] + [m.group(1) for m in _HEADING.finditer(text)]
        for h in heads:
            low = _TAG.sub("", h).lower()
            for w in ERROR_PAGE_WORDS:
                if w in low:
                    return bad("content", f"保守・拒否ページの印（{w}）")
        head = text[:2000].lower()
        for w in ERROR_PAGE_RAW_MARKERS:
            if w in head:
                return bad("content", f"保守・拒否ページの印（{w}）")
    return None


def validate_response(page: Page, phase: str = "fetch") -> ErrorInfo | None:
    """200 で返ってきたページが読める中身か。読めなければ ErrorInfo（kind は content か redirect）。"""
    r = _check(page, phase)
    return r[0] if r else None


def _raise_if_unreadable(page: Page, phase: str = "fetch") -> None:
    r = _check(page, phase)
    if r:
        raise FetchError(f"取得不能: {r[1]}: {page.url}", r[0])


class Fetcher:
    def __init__(self, delay: float = 1.0, timeout: httpx.Timeout | float = DEFAULT_TIMEOUT,
                 respect_robots: bool = True) -> None:
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
            raise FetchError(f"robots.txt により拒否: {url}", ErrorInfo("robots", host=host_of(url), url=url))
        r, attempt = self._get_with_retry(url)
        if r.status_code >= 400:
            raise FetchError(f"HTTP {r.status_code}: {url}",
                             ErrorInfo("http", status=r.status_code, host=host_of(url), url=url, attempt=attempt))
        ctype = r.headers.get("content-type", "")
        html = None
        if "pdf" not in ctype and not url.lower().endswith(".pdf"):
            html = decode(r.content, r.charset_encoding, encoding)
        page = Page(url, str(r.url), r.status_code, r.content, html, ctype)
        _raise_if_unreadable(page)
        self.cache[key] = page
        return page

    def _get_with_retry(self, url: str) -> tuple[httpx.Response, int]:
        """RETRY_STATUSES と RETRY_EXCEPTIONS の失敗を、上限付き指数 backoff（Full Jitter）か Retry-After で取り直す。
        試行は MAX_ATTEMPTS 回まで、待ちの合計は RETRY_BUDGET_SECONDS まで。
        返すのは (応答, 試行回数)。再試行しない 4xx・再試行を尽くした最後の応答もそのまま返す（呼び出し側が HTTP エラーにする）。"""
        waited = 0.0
        attempt = 0
        resp: httpx.Response | None = None
        failure: FetchError | None = None   # 例外で終わる場合に上げる FetchError（予算切れ・回数切れ共通）
        while True:
            attempt += 1
            self._throttle(url)
            try:
                r = resp = self.client.get(url)
                failure = None
                reason = f"HTTP {r.status_code}"
                retry_after = None
                if r.status_code not in RETRY_STATUSES:
                    return r, attempt
                retry_after = parse_retry_after(r.headers.get("retry-after"))
                if retry_after is not None and retry_after > RETRY_AFTER_MAX:
                    raise FetchError(f"HTTP {r.status_code}: {url}（Retry-After {retry_after:.0f} 秒）",
                                     ErrorInfo("http", status=r.status_code, host=host_of(url), url=url,
                                               attempt=attempt, retry_after=retry_after))
                if attempt >= MAX_ATTEMPTS:
                    return r, attempt
            except httpx.HTTPError as e:
                info = classify_exception(e, url, attempt=attempt)
                failure = FetchError(f"{type(e).__name__}: {e}", info)
                failure.__cause__ = e
                if not isinstance(e, RETRY_EXCEPTIONS) or info.kind in NO_RETRY_KINDS or attempt >= MAX_ATTEMPTS:
                    raise failure from e
                reason = info.kind
                retry_after = None
                resp = None
            wait = retry_after if retry_after is not None else backoff_seconds(attempt - 1)
            if waited + wait > RETRY_BUDGET_SECONDS:
                if resp is not None:
                    return resp, attempt
                if failure is not None:
                    raise failure
            log.info("get: %s のため %.1f 秒後に取り直す（%d/%d 回目の失敗）: %s", reason, wait, attempt, MAX_ATTEMPTS, url)
            time.sleep(wait)
            waited += wait

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
                    def _on_response(r):
                        if capture in r.url:
                            try:
                                captured.append(r.json())
                            except Exception:
                                pass

                    page.on("response", _on_response)
                page.goto(url, wait_until="networkidle", timeout=60000)
                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=WAIT_FOR_MS)
                    except Exception:
                        log.info("render: wait_for '%s' が %d ms 待っても現れない: %s", wait_for, WAIT_FOR_MS, url)
                page.wait_for_timeout(wait_ms)
                html = page.content()
                final = page.url
            finally:
                browser.close()
        res = Page(url, final, 200, html.encode("utf-8"), html, "text/html; rendered", captured)
        _raise_if_unreadable(res, "render")
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
