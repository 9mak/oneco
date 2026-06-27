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
        return self._publish(container_id)

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
            raise ThreadsPostError(f"container creation failed: {_redact_token(str(exc))}") from exc

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
            raise ThreadsPostError(f"publish failed: {_redact_token(str(exc))}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise ThreadsPostError(f"publish response not JSON: {resp.text!r}") from exc

        if not isinstance(data, dict) or "id" not in data:
            raise ThreadsPostError(f"publish response missing 'id': {data!r}")
        return str(data["id"])
