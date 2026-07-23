"""SNS publisher orchestrator (Threads 本命)

design.md 5.2 pipeline 全段を 1 関数 publish_one() で束ねる。

- kill switch THREADS_PUBLISH_ENABLED (default false): 厳守。secrets が揃う前に
  事故投稿しないため。
- dry_run THREADS_PUBLISH_DRY_RUN (default true): 段階リリース。
  Threads client が無い (= 本 PR の状態) でも moderate まで通すことで、
  「実本番では何が投稿候補になるか」を post_log で確認できる。
- Threads API client (実投稿): 次 PR (access token 取得後)。本 PR では client=None
  経路 (no_api_client / dry_run の return) のみ実装。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

from data_collector.domain.models import AnimalData, AnimalStatus

from .candidate_selector import select_candidate
from .moderator import moderate_post
from .post_log import PostLog

logger = logging.getLogger(__name__)

# oneco 本体の base URL。feed_generator._resolve_base_url() と同じ優先順。
_SITE_URL_ENV_VARS = ("SITE_URL", "FRONTEND_URL", "NEXT_PUBLIC_SITE_URL")
_DEFAULT_SITE_URL = "https://oneco.example"


def _resolve_site_url(env: dict[str, str]) -> str:
    for var in _SITE_URL_ENV_VARS:
        value = env.get(var, "").strip().rstrip("/")
        if value:
            return value
    return _DEFAULT_SITE_URL


def _build_oneco_url(animal_id: int | None, env: dict[str, str], *, platform: str) -> str | None:
    """SNS 集客導線: oneco 側の動物詳細ページ URL を組み立てる。

    animal_id が引けない (未同期・削除済み等) 場合は None を返し、
    text_generator 側は自治体公式リンクのみで投稿する (従来動作)。
    """
    if animal_id is None:
        return None
    base = _resolve_site_url(env)
    query = urlencode({"utm_source": platform, "utm_medium": "sns_post"})
    return f"{base}/animals/{animal_id}?{query}"


@dataclass(frozen=True)
class PublishResult:
    """publish_one() の戻り値。Discord 通知や次 run の判断に使う。"""

    posted: bool  # 実際に Threads/X へ POST した
    dry_run: bool
    platform: str
    candidate: AnimalData | None
    text: str | None
    reason: (
        str | None
    )  # disabled / no_candidate / moderation_failed:* / dry_run / no_api_client / publish_error:*


class _AnimalsRepo(Protocol):
    async def list_animals(
        self,
        *,
        status: AnimalStatus | None = ...,
        include_non_public: bool = ...,
        limit: int = ...,
        offset: int = ...,
        **kwargs: object,
    ) -> tuple[list[AnimalData], int]: ...

    async def get_animal_id_by_source_url(self, source_url: str) -> int | None: ...


class _TextGen(Protocol):
    def generate(
        self, animal: AnimalData, *, platform: str, oneco_url: str | None = None
    ) -> str: ...


def _truthy(env: dict[str, str], key: str, *, default: str = "false") -> bool:
    return env.get(key, default).strip().lower() == "true"


async def publish_one(
    *,
    repo: _AnimalsRepo,
    generator: _TextGen,
    post_log: PostLog,
    platform: str = "threads",
    env: dict[str, str] | None = None,
    threads_client: Any | None = None,
) -> PublishResult:
    """投稿候補 1 件のパイプラインを実行する。

    Returns:
        PublishResult: 結果。Discord 通知や cron の終了コード判断に使う。
    """
    env_map = dict(os.environ) if env is None else dict(env)

    # 1. kill switch
    if not _truthy(env_map, "THREADS_PUBLISH_ENABLED"):
        logger.info("SNS publisher disabled (THREADS_PUBLISH_ENABLED!=true)")
        return PublishResult(
            posted=False,
            dry_run=False,
            platform=platform,
            candidate=None,
            text=None,
            reason="disabled",
        )

    dry_run = _truthy(env_map, "THREADS_PUBLISH_DRY_RUN", default="true")

    # 2. select candidate
    candidate = await select_candidate(repo, already_posted_urls=post_log.posted_urls())
    if candidate is None:
        logger.info("SNS publisher: no candidate")
        return PublishResult(
            posted=False,
            dry_run=dry_run,
            platform=platform,
            candidate=None,
            text=None,
            reason="no_candidate",
        )

    # 3. generate text (oneco 詳細ページへの導線を可能なら添える)
    animal_id = await repo.get_animal_id_by_source_url(str(candidate.source_url))
    oneco_url = _build_oneco_url(animal_id, env_map, platform=platform)
    text = generator.generate(candidate, platform=platform, oneco_url=oneco_url)

    # 4. moderate (二重防御)
    mod = moderate_post(text, candidate, platform=platform)
    if not mod.ok:
        logger.warning(
            "SNS publisher: moderation rejected url=%s reasons=%s",
            candidate.source_url,
            mod.reasons,
        )
        return PublishResult(
            posted=False,
            dry_run=dry_run,
            platform=platform,
            candidate=candidate,
            text=text,
            reason=f"moderation_failed:{','.join(mod.reasons)}",
        )

    final_text = mod.text

    # 5. dry_run: 記録のみで投稿しない
    if dry_run:
        post_log.record(
            url=str(candidate.source_url),
            platform=platform,
            text=final_text,
            dry_run=True,
        )
        return PublishResult(
            posted=False,
            dry_run=True,
            platform=platform,
            candidate=candidate,
            text=final_text,
            reason="dry_run",
        )

    # 6. wet: Threads API client が無ければ no_api_client で安全停止
    #    (次 PR で client を注入する。本 PR では到達しない設計)
    if threads_client is None:
        logger.warning("SNS publisher: dry_run=false but threads_client is None; not posting")
        return PublishResult(
            posted=False,
            dry_run=False,
            platform=platform,
            candidate=candidate,
            text=final_text,
            reason="no_api_client",
        )

    # 7. 実投稿 (次 PR で client.post を実装)
    try:
        threads_client.post(final_text, candidate=candidate)
    except Exception as exc:
        # 上流 API の全例外を捕捉して post_log を汚さない
        logger.error("SNS publisher: post failed url=%s err=%s", candidate.source_url, exc)
        return PublishResult(
            posted=False,
            dry_run=False,
            platform=platform,
            candidate=candidate,
            text=final_text,
            reason=f"publish_error:{type(exc).__name__}",
        )

    post_log.record(
        url=str(candidate.source_url),
        platform=platform,
        text=final_text,
        dry_run=False,
    )
    return PublishResult(
        posted=True,
        dry_run=False,
        platform=platform,
        candidate=candidate,
        text=final_text,
        reason=None,
    )
