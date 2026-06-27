"""外部 API トークンの失効を定期チェックする。

oneco は Groq (投稿文生成 / adapter 自己修復) と Threads (SNS 自動投稿) の
long-lived トークンに依存する。これらは GitHub Actions secrets / repo variables
に登録され、ローテや有効期限切れで静かに失効しうる。失効しても collector や
SNS publisher は fallback でそれなりに success 表示になるため、人が気づけない。

2026-06-27 に Groq key が約6週間失効に気づかず SNS 投稿が全部 fallback テンプレ文に
劣化していた事故を踏まえ、トークンの有効性を日次でチェックして失効を Discord 通知する。

判定方針:
- 200 → 有効
- 401 / 403 → 失効・無効 (= 通知対象)
- それ以外 (5xx / timeout / ネットワークエラー) → 一時障害の可能性。誤通知疲労を
  避けるため ok 扱いとし、status のみ detail に残す (uptime-check.yml と同じ思想)。
- 未設定 (None / 空) → 監視対象外 (configured=False)。通知しない。

httpx.Client を引数で受けることで、テストでは mock client を注入する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from data_collector.infrastructure.notification_client import NotificationLevel

logger = logging.getLogger(__name__)

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
THREADS_ME_URL = "https://graph.threads.net/v1.0/me"
HTTP_TIMEOUT_SEC = 10.0

# 失効と判定する HTTP status (認証エラー)
_EXPIRED_STATUSES = frozenset({401, 403})


@dataclass(frozen=True)
class SecretCheckResult:
    """1 トークンの有効性チェック結果。

    Attributes:
        name: トークン名 ("groq" / "threads")
        configured: トークンが設定されているか (未設定なら監視対象外)
        ok: 有効か (失効していないか)。configured=False のときは常に True。
        status_code: HTTP status (叩けなかった場合は None)
        detail: 人間可読の補足
    """

    name: str
    configured: bool
    ok: bool
    status_code: int | None
    detail: str


class _HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


def _classify(name: str, status_code: int) -> SecretCheckResult:
    """HTTP status から SecretCheckResult を組む (有効性判定の一元化)。"""
    if status_code in _EXPIRED_STATUSES:
        return SecretCheckResult(
            name=name,
            configured=True,
            ok=False,
            status_code=status_code,
            detail=f"HTTP {status_code} (認証エラー = 失効/無効の疑い)",
        )
    if status_code == 200:
        return SecretCheckResult(
            name=name, configured=True, ok=True, status_code=200, detail="HTTP 200 (有効)"
        )
    # 5xx / その他: 一時障害の可能性。誤通知を避けて ok 扱い (status は残す)。
    return SecretCheckResult(
        name=name,
        configured=True,
        ok=True,
        status_code=status_code,
        detail=f"HTTP {status_code} (一時障害の可能性。失効とは判定しない)",
    )


def _unconfigured(name: str) -> SecretCheckResult:
    return SecretCheckResult(
        name=name, configured=False, ok=True, status_code=None, detail="未設定 (監視対象外)"
    )


def _transient_error(name: str, exc: Exception) -> SecretCheckResult:
    return SecretCheckResult(
        name=name,
        configured=True,
        ok=True,
        status_code=None,
        detail=f"接続エラー (一時障害の可能性。失効とは判定しない): {exc}",
    )


def check_groq(api_key: str | None, *, client: _HttpClient) -> SecretCheckResult:
    """Groq API key の有効性を /models エンドポイントで確認する。"""
    if not api_key or not api_key.strip():
        return _unconfigured("groq")
    try:
        resp = client.get(
            GROQ_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=HTTP_TIMEOUT_SEC,
        )
    except Exception as exc:
        # 接続失敗 (DNS/SSL/timeout 等) は一時障害とみなし、失効判定しない
        return _transient_error("groq", exc)
    return _classify("groq", resp.status_code)


def check_threads(access_token: str | None, *, client: _HttpClient) -> SecretCheckResult:
    """Threads access_token の有効性を /me エンドポイントで確認する。"""
    if not access_token or not access_token.strip():
        return _unconfigured("threads")
    try:
        resp = client.get(
            THREADS_ME_URL,
            params={"fields": "id", "access_token": access_token},
            timeout=HTTP_TIMEOUT_SEC,
        )
    except Exception as exc:
        # 接続失敗 (DNS/SSL/timeout 等) は一時障害とみなし、失効判定しない
        return _transient_error("threads", exc)
    return _classify("threads", resp.status_code)


def evaluate(results: list[SecretCheckResult]) -> tuple[bool, str, dict[str, Any]]:
    """チェック結果を集約し、(失効あり, メッセージ, details) を返す。

    configured かつ ok=False のものだけを失効として扱う。未設定や一時障害は除外。
    """
    expired = [r for r in results if r.configured and not r.ok]
    if not expired:
        return False, "全シークレット有効", {}
    names = ", ".join(r.name for r in expired)
    message = f"シークレット失効検知: {len(expired)} 件無効 ({names})"
    details: dict[str, Any] = {r.name: r.detail for r in expired}
    return True, message, details


def maybe_notify(results: list[SecretCheckResult], notification_client: Any) -> bool:
    """失効があれば WARNING で通知し True を返す。無ければ通知せず False。"""
    has_expired, message, details = evaluate(results)
    if not has_expired:
        return False
    notification_client.send_alert(NotificationLevel.WARNING, message, details)
    return True
