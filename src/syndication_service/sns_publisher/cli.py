"""SNS publisher CLI エントリ (GitHub Actions cron 用)

`python -m syndication_service.sns_publisher` で 1 件投稿を試みる。

責務:
  - env から secrets / 設定を読み取る
  - generator / threads_client / repo / post_log を組み立てる
  - publish_one() を 1 回呼ぶ
  - 結果を Discord 通知 (DISCORD_WEBHOOK_URL があれば)
  - exit code: posted/dry_run/disabled/no_candidate=0、moderation_failed/publish_error/no_api_client=1

ユニットテストは pure pieces (build_generator / build_threads_client /
format_summary / result_to_exit_code) のみカバー。実 DB / 実 API は
manual smoke test に委ねる。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from .publisher import PublishResult, publish_one
from .text_generator import TextGenerator
from .threads_client import ThreadsClient

logger = logging.getLogger(__name__)

_DEFAULT_POST_LOG_PATH = Path("data/sns_posts.yaml")

# exit code = 1 にすべき reason (CI で notify されるもの)
_FAILURE_REASONS: frozenset[str] = frozenset({"no_api_client", "no_database"})


def build_generator(env: dict[str, str]) -> TextGenerator:
    """env から TextGenerator を組み立てる。GROQ_API_KEY 未設定なら fallback only。"""
    api_key = env.get("GROQ_API_KEY")
    if not api_key:
        return TextGenerator(client=None)
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not available; using fallback-only generator")
        return TextGenerator(client=None)
    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    return TextGenerator(client=client)


def build_threads_client(env: dict[str, str]) -> ThreadsClient | None:
    """env に THREADS_ACCESS_TOKEN と THREADS_USER_ID が揃っているときだけ作る。"""
    token = env.get("THREADS_ACCESS_TOKEN")
    user_id = env.get("THREADS_USER_ID")
    if not token or not user_id:
        return None
    return ThreadsClient(user_id=user_id, access_token=token)


def result_to_exit_code(result: PublishResult) -> int:
    """failure reason は 1、それ以外は 0。"""
    if result.reason is None:
        return 0
    head = result.reason.split(":", 1)[0]
    if head in _FAILURE_REASONS:
        return 1
    if head in {"moderation_failed", "publish_error"}:
        return 1
    return 0


def format_summary(result: PublishResult) -> str:
    """Discord に投稿する整形済みメッセージ。"""
    head = (result.reason or "").split(":", 1)[0]
    url = str(result.candidate.source_url) if result.candidate else "(なし)"

    if result.posted:
        return f":white_check_mark: Threads に投稿しました\nURL: {url}\n```\n{result.text}\n```"
    if head == "dry_run":
        return f":mag: Threads dry-run (post_log に記録のみ)\nURL: {url}\n```\n{result.text}\n```"
    if head == "disabled":
        return ":zzz: SNS publisher disabled (THREADS_PUBLISH_ENABLED!=true)"
    if head == "no_candidate":
        return ":information_source: 投稿候補なし (全件投稿済 or image_urls 不足)"
    if head == "moderation_failed":
        reasons = (result.reason or "").split(":", 1)[1] if ":" in (result.reason or "") else ""
        return f":warning: モデレーション失敗 ({reasons})\nURL: {url}"
    if head == "no_api_client":
        return ":warning: dry_run=false だが Threads client 未構築 (no_api_client)。THREADS_ACCESS_TOKEN / THREADS_USER_ID 設定を確認"
    if head == "publish_error":
        err = (result.reason or "").split(":", 1)[1] if ":" in (result.reason or "") else ""
        return f":x: 投稿失敗 (publish_error: {err})\nURL: {url}"
    return f"unknown reason: {result.reason}"


async def _run_async(env: dict[str, str]) -> PublishResult:
    """DB 接続を貼って publish_one を 1 回呼ぶ。"""
    from data_collector.infrastructure.database.connection import (
        DatabaseConnection,
        DatabaseSettings,
    )
    from data_collector.infrastructure.database.repository import AnimalRepository

    from .post_log import PostLog

    database_url = env.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set; cannot select candidate")
        return PublishResult(
            posted=False,
            dry_run=False,
            platform="threads",
            candidate=None,
            text=None,
            reason="no_database",
        )

    db_settings = DatabaseSettings(database_url=database_url)
    db_connection = DatabaseConnection(settings=db_settings)

    post_log_path = Path(env.get("SNS_POST_LOG_PATH", str(_DEFAULT_POST_LOG_PATH)))
    post_log = PostLog(path=post_log_path)

    generator = build_generator(env)
    threads_client = build_threads_client(env)

    async with db_connection.get_session() as session:
        repo = AnimalRepository(session)
        return await publish_one(
            repo=repo,
            generator=generator,
            post_log=post_log,
            platform="threads",
            env=env,
            threads_client=threads_client,
        )


def _send_discord(env: dict[str, str], message: str) -> None:
    """DISCORD_WEBHOOK_URL があれば best-effort で送信。"""
    webhook = env.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    try:
        import requests

        requests.post(webhook, json={"content": message}, timeout=10)
    except Exception as exc:
        logger.warning("Discord notification failed: %s", exc)


def main(argv: list[str] | None = None) -> int:
    del argv  # 引数は env 経由のみ
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    env = dict(os.environ)
    result = asyncio.run(_run_async(env))
    summary = format_summary(result)
    logger.info(summary)
    _send_discord(env, summary)
    return result_to_exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
