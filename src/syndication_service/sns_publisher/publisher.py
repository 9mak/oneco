"""SNS publisher orchestrator (T151 設計 / T160・日次まとめ版)

前日 (JST) の新着をまとめて Threads へ 1 投稿する。個体 1 件ずつの選定・
LLM 生成・PII モデレーションは撤去した (定型文のみ・事実のみのため不要)。

- kill switch THREADS_PUBLISH_ENABLED (default false): 厳守。
- dry_run THREADS_PUBLISH_DRY_RUN (default true): 集計と文面を確認するだけで
  投稿しない・ログにも記録しない段階リリース用。
- 同一日付の二重投稿は DigestLog (post_log.py) が防ぐ。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from .digest import DigestStats, collect_daily_digest
from .digest_text import build_digest_text
from .post_log import DigestLog

logger = logging.getLogger(__name__)

_SITE_URL_ENV_VARS = ("SITE_URL", "FRONTEND_URL", "NEXT_PUBLIC_SITE_URL")
_DEFAULT_SITE_URL = "https://oneco.example"


def _resolve_site_url(env: dict[str, str]) -> str:
    for var in _SITE_URL_ENV_VARS:
        value = env.get(var, "").strip().rstrip("/")
        if value:
            return value
    return _DEFAULT_SITE_URL


def _truthy(env: dict[str, str], key: str, *, default: str = "false") -> bool:
    return env.get(key, default).strip().lower() == "true"


class _DigestRepo(Protocol):
    async def list_animals_first_seen_between(
        self, *, start: datetime, end: datetime
    ) -> list[Any]: ...


class _ThreadsClient(Protocol):
    def post(self, text: str, *, image_url: str | None = None, candidate: Any = None) -> str: ...


@dataclass(frozen=True)
class DigestPublishResult:
    """publish_daily_digest() の戻り値。Discord 通知や cron の終了コード判断に使う。"""

    posted: bool  # 実際に Threads へ POST した
    dry_run: bool
    stats: DigestStats | None
    text: str | None
    reason: (
        str | None
    )  # disabled / no_new_animals / already_posted / dry_run / no_api_client / publish_error:*


async def publish_daily_digest(
    *,
    repo: _DigestRepo,
    digest_log: DigestLog,
    target_date_jst: date,
    env: dict[str, str] | None = None,
    threads_client: _ThreadsClient | None = None,
) -> DigestPublishResult:
    """target_date_jst (JST) の新着まとめを 1 回投稿する。

    Returns:
        DigestPublishResult
    """
    env_map = dict(os.environ) if env is None else dict(env)

    # 1. kill switch
    if not _truthy(env_map, "THREADS_PUBLISH_ENABLED"):
        logger.info("SNS digest publisher disabled (THREADS_PUBLISH_ENABLED!=true)")
        return DigestPublishResult(
            posted=False, dry_run=False, stats=None, text=None, reason="disabled"
        )

    dry_run = _truthy(env_map, "THREADS_PUBLISH_DRY_RUN", default="true")
    date_str = target_date_jst.isoformat()

    # 2. 同一日付の二重投稿防止
    if digest_log.is_posted(date_str):
        logger.info("SNS digest publisher: %s already posted", date_str)
        return DigestPublishResult(
            posted=False, dry_run=dry_run, stats=None, text=None, reason="already_posted"
        )

    # 3. 集計
    stats = await collect_daily_digest(repo, target_date_jst=target_date_jst)
    if stats is None:
        logger.info("SNS digest publisher: no new animals on %s", date_str)
        return DigestPublishResult(
            posted=False, dry_run=dry_run, stats=None, text=None, reason="no_new_animals"
        )

    # 4. 文面組み立て (定型文のみ、LLM 不使用)
    site_url = _resolve_site_url(env_map)
    text = build_digest_text(stats, site_url=site_url)

    # 5. dry_run: 集計と文面を確認するだけ。ログにも記録しない
    #    (実運用の投稿判断に影響を与えないため)。
    if dry_run:
        return DigestPublishResult(
            posted=False, dry_run=True, stats=stats, text=text, reason="dry_run"
        )

    # 6. wet: Threads API client が無ければ no_api_client で安全停止
    if threads_client is None:
        logger.warning(
            "SNS digest publisher: dry_run=false but threads_client is None; not posting"
        )
        return DigestPublishResult(
            posted=False, dry_run=False, stats=stats, text=text, reason="no_api_client"
        )

    # 7. 実投稿 (画像なし固定)
    try:
        post_id = threads_client.post(text, image_url=None)
    except Exception as exc:
        logger.error("SNS digest publisher: post failed date=%s err=%s", date_str, exc)
        return DigestPublishResult(
            posted=False,
            dry_run=False,
            stats=stats,
            text=text,
            reason=f"publish_error:{type(exc).__name__}",
        )

    digest_log.record(
        date_str=date_str,
        post_id=post_id,
        posted_at=datetime.now(UTC).isoformat(),
    )
    return DigestPublishResult(posted=True, dry_run=False, stats=stats, text=text, reason=None)
