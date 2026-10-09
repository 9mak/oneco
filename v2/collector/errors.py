"""収集の失敗を構造化して持つ（W006 T601）。

文字列（"HTTP 503: url"）は表示用。判定（再試行・遮断・回線断・通知の dedup）は ErrorInfo の
kind / status / host / phase で行う。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

# kind の一覧（判定で使う固定語）
#   dns        名前解決に失敗
#   connect    TCP 接続に失敗（拒否・到達不能）
#   tls        TLS ハンドシェイク・証明書の失敗
#   timeout    connect / read / write / pool のタイムアウト
#   protocol   確立済み接続をサーバーが閉じた等（RemoteProtocolError / ReadError / WriteError）
#   http       4xx / 5xx（status に入れる）
#   redirect   リダイレクトし過ぎ・別ホストへ飛ばされた
#   robots     robots.txt による拒否
#   content    200 だが中身が読めない（保守ページ・CAPTCHA・空・Content-Type 不一致）
#   recipe     レシピの定義・実行の失敗（RecipeError）
#   parser     読めたが 1 頭も取れず 0 頭とも確定できない
#   ambiguous_empty  0 頭に見えるが肯定的な証拠が無い（前日のデータを保持する）
#   other      上記以外
KINDS = ("dns", "connect", "tls", "timeout", "protocol", "http", "redirect", "robots", "content",
         "recipe", "parser", "ambiguous_empty", "other")
# 接続系（回線断の判定に使う）
TRANSPORT_KINDS = frozenset({"dns", "connect", "tls", "timeout"})


@dataclass
class ErrorInfo:
    kind: str
    status: int | None = None
    host: str | None = None
    phase: str = "fetch"            # fetch | render | parse
    attempt: int = 1
    retry_after: float | None = None   # Retry-After（秒）。429/503 で値があれば
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    return urlsplit(url).netloc.lower() or None


def _msg(e: BaseException) -> str:
    return str(e).lower()


def classify_exception(e: BaseException, url: str | None = None, phase: str = "fetch", attempt: int = 1) -> ErrorInfo:
    """httpx の例外を ErrorInfo にする。"""
    host = host_of(url)
    m = _msg(e)
    if isinstance(e, httpx.ConnectError):
        if any(w in m for w in ("nodename nor servname", "name or service not known", "getaddrinfo",
                                "temporary failure in name resolution", "no address associated")):
            kind = "dns"
        elif any(w in m for w in ("ssl", "certificate", "tls", "handshake")):
            kind = "tls"
        else:
            kind = "connect"
    elif isinstance(e, httpx.TimeoutException):
        kind = "timeout"
    elif isinstance(e, httpx.RemoteProtocolError | httpx.ReadError | httpx.WriteError):
        kind = "protocol"
    elif isinstance(e, httpx.TooManyRedirects):
        kind = "redirect"
    elif isinstance(e, httpx.HTTPStatusError):
        return ErrorInfo("http", status=e.response.status_code, host=host, phase=phase, attempt=attempt, url=url)
    elif any(w in m for w in ("ssl", "certificate")):
        kind = "tls"
    else:
        kind = "other"
    return ErrorInfo(kind, host=host, phase=phase, attempt=attempt, url=url)


def error_to_dict(err: BaseException | None) -> dict[str, Any] | None:
    """例外から report に残す辞書を作る。ErrorInfo を持たない例外は kind=other。"""
    if err is None:
        return None
    info = getattr(err, "info", None)
    if isinstance(info, ErrorInfo):
        return info.to_dict()
    return ErrorInfo("other").to_dict()
