"""Threads API client (Meta Graph API ラッパー)

design.md 5.5 準拠。requests 直叩き (依存最小)。

投稿は 2 段:
  1. POST /{user_id}/threads          → media container 作成
  2. POST /{user_id}/threads_publish  → publish (creation_id 渡し)

OAuth long-lived access_token を環境変数 / Keychain から外側で取得し、
コンストラクタで渡す。本クライアントは token 取得経路には関与しない。

レート制限 (250 投稿/24h) は oneco の想定 1-3 件/日では問題にならないため、
リトライは入れない。エラーは ThreadsPostError として publisher へ伝播し、
publisher 側で post_log に汚染を残さず PublishResult.reason に記録される。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from typing import Any

import requests

logger = logging.getLogger(__name__)

# access_token はクエリ文字列で渡すため、requests が 4xx/5xx 時に投げる
# HTTPError のメッセージには解決済み URL (= ?access_token=<値>...) が
# そのまま埋まる。これを ThreadsPostError に転記すると publisher のログ
# (GitHub Actions ログ) に long-lived token が露出する。値部分だけを伏字化する。
_TOKEN_QUERY_RE = re.compile(r"(access_token=)[^&\s]+", re.IGNORECASE)


def _redact_token(message: str) -> str:
    """文字列中の `access_token=<値>` を `access_token=<redacted>` に伏字化する。"""
    return _TOKEN_QUERY_RE.sub(r"\1<redacted>", message)


_RESPONSE_BODY_MAX_LEN = 500


def _response_body_snippet(response: requests.Response | None) -> str:
    """HTTPError.response からエラーボディを抽出する (400 vs 500 の原因切り分け用)。

    Meta Graph API のエラーレスポンスは `{"error": {"message": ..., "code": ...}}`
    形式で原因 (レート制限/パラメータ不正/一時障害等) を含む。従来は
    requests.HTTPError の str() (ステータスコードのみ) しかログに残らず、
    400 と 500 を同じ扱いでしか観測できなかった (2026-07-16 間欠失敗の調査難航)。
    """
    if response is None:
        return ""
    try:
        text = response.text
    except Exception:
        return ""
    if not text:
        return ""
    return f" body={_redact_token(text[:_RESPONSE_BODY_MAX_LEN])}"


class ThreadsPostError(Exception):
    """Threads 投稿の上流エラー (HTTP / レスポンス形式)"""


class ThreadsClient:
    def __init__(
        self,
        *,
        user_id: str,
        access_token: str,
        session: requests.Session | None = None,
        base_url: str = "https://graph.threads.net/v1.0",
        timeout: float = 15.0,
        poll_interval_sec: float = 2.0,
        poll_max_attempts: int = 10,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user_id:
            raise ValueError("user_id must be non-empty")
        if not access_token:
            raise ValueError("access_token must be non-empty")
        self._user_id = user_id
        self._access_token = access_token
        self._session = session or requests.Session()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # container が publish 可能 (status=FINISHED) になるまでのポーリング設定。
        # sleep は注入可能 (テストで no-op 化してハングを防ぐ)。
        self._poll_interval_sec = poll_interval_sec
        self._poll_max_attempts = poll_max_attempts
        self._sleep = sleep

    def post(
        self,
        text: str,
        *,
        image_url: str | None = None,
        candidate: Any = None,
    ) -> str:
        """Threads にテキスト (または画像 + テキスト) を投稿する。

        Args:
            text: 投稿本文
            image_url: 画像 URL (任意。指定時は media_type=IMAGE)
            candidate: publisher 互換のためのプレースホルダ。本クライアントは未使用

        Returns:
            published thread id

        Raises:
            ThreadsPostError: HTTP エラー / 想定外のレスポンス形式
        """
        del candidate  # publisher 互換
        container_id = self._create_container(text, image_url=image_url)
        # container が FINISHED になるまで待ってから publish。作成直後に publish すると
        # status=IN_PROGRESS のまま叩いて 400 Bad Request になる間欠失敗を防ぐ。
        self._wait_until_ready(container_id)
        return self._publish(container_id)

    def _wait_until_ready(self, container_id: str) -> None:
        """media container が publish 可能 (status=FINISHED) になるまでポーリングする。

        Threads は container 作成後に非同期で処理する。作成直後に publish すると
        status=IN_PROGRESS のまま叩いて 400 Bad Request になることがある (wet 化後
        7run 中 1 失敗の間欠失敗の原因)。FINISHED を待ってから publish して安定させる。

        Raises:
            ThreadsPostError: status=ERROR/EXPIRED、HTTP エラー、または規定回数
                ポーリングしても FINISHED にならなかった場合。
        """
        url = f"{self._base_url}/{container_id}"
        params = {"fields": "status", "access_token": self._access_token}
        for attempt in range(self._poll_max_attempts):
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout)
                resp.raise_for_status()
            except requests.RequestException as exc:
                body = _response_body_snippet(getattr(exc, "response", None))
                raise ThreadsPostError(
                    f"container status check failed: {_redact_token(str(exc))}{body}"
                ) from exc

            try:
                data = resp.json()
            except ValueError as exc:
                raise ThreadsPostError(f"status response not JSON: {resp.text!r}") from exc

            status = data.get("status") if isinstance(data, dict) else None
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ThreadsPostError(f"container not publishable: status={status}")
            # IN_PROGRESS / 不明 → 待って再試行 (最終試行後は待たない)
            if attempt < self._poll_max_attempts - 1:
                self._sleep(self._poll_interval_sec)
        raise ThreadsPostError(f"container not FINISHED after {self._poll_max_attempts} polls")

    def _create_container(self, text: str, *, image_url: str | None) -> str:
        url = f"{self._base_url}/{self._user_id}/threads"
        params: dict[str, str] = {
            "access_token": self._access_token,
            "text": text,
            "media_type": "IMAGE" if image_url else "TEXT",
        }
        if image_url:
            params["image_url"] = image_url

        try:
            resp = self._session.post(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            body = _response_body_snippet(getattr(exc, "response", None))
            raise ThreadsPostError(
                f"container creation failed: {_redact_token(str(exc))}{body}"
            ) from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise ThreadsPostError(f"container response not JSON: {resp.text!r}") from exc

        if not isinstance(data, dict) or "id" not in data:
            raise ThreadsPostError(f"container response missing 'id': {data!r}")
        return str(data["id"])

    def _publish(self, container_id: str) -> str:
        url = f"{self._base_url}/{self._user_id}/threads_publish"
        params = {
            "access_token": self._access_token,
            "creation_id": container_id,
        }

        try:
            resp = self._session.post(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            body = _response_body_snippet(getattr(exc, "response", None))
            raise ThreadsPostError(f"publish failed: {_redact_token(str(exc))}{body}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise ThreadsPostError(f"publish response not JSON: {resp.text!r}") from exc

        if not isinstance(data, dict) or "id" not in data:
            raise ThreadsPostError(f"publish response missing 'id': {data!r}")
        return str(data["id"])
