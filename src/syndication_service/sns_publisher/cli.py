"""SNS digest publisher CLI エントリ (GitHub Actions cron 用)

`python -m syndication_service.sns_publisher` で前日 (JST) の新着まとめを
1 回投稿する。`--dry-run` を渡すと集計と文面を stdout に出すだけで投稿・
ログ記録のいずれも行わない (THREADS_PUBLISH_DRY_RUN env より優先する)。

責務:
  - env から secrets / 設定を読み取る
  - threads_client / repo / digest_log を組み立てる
  - publish_daily_digest() を 1 回呼ぶ (対象日は実行日の前日・JST)
  - 結果を Discord 通知 (DISCORD_WEBHOOK_URL があれば)
  - exit code: posted/dry_run/disabled/no_new_animals/already_posted=0、
    no_api_client/publish_error=1
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .post_log import DEFAULT_DIGEST_LOG_PATH, DigestLog
from .publisher import DigestPublishResult, publish_daily_digest
from .threads_client import ThreadsClient

logger = logging.getLogger(__name__)

_JST = ZoneInfo("Asia/Tokyo")

# exit code = 1 にすべき reason (CI で notify されるもの)
_FAILURE_REASONS: frozenset[str] = frozenset({"no_database", "no_api_client"})


def build_threads_client(env: dict[str, str]) -> ThreadsClient | None:
    """env に THREADS_ACCESS_TOKEN と THREADS_USER_ID が揃っているときだけ作る。"""
    token = env.get("THREADS_ACCESS_TOKEN")
    user_id = env.get("THREADS_USER_ID")
    if not token or not user_id:
        return None
    return ThreadsClient(user_id=user_id, access_token=token)


def result_to_exit_code(result: DigestPublishResult) -> int:
    """failure reason は 1、それ以外は 0。"""
    if result.reason is None:
        return 0
    head = result.reason.split(":", 1)[0]
    if head in _FAILURE_REASONS:
        return 1
    if head == "publish_error":
        return 1
    return 0


def format_summary(result: DigestPublishResult) -> str:
    """Discord に投稿する整形済みメッセージ。"""
    head = (result.reason or "").split(":", 1)[0]

    if result.posted:
        return (
            f":white_check_mark: Threads に日次まとめを投稿しました "
            f"({result.stats.target_date if result.stats else '?'})\n```\n{result.text}\n```"
        )
    if head == "dry_run":
        return (
            f":mag: Threads dry-run (投稿しません)\n```\n{result.text}\n```"
            if result.text
            else ":mag: Threads dry-run: 集計結果なし"
        )
    if head == "disabled":
        return ":zzz: SNS digest publisher disabled (THREADS_PUBLISH_ENABLED!=true)"
    if head == "no_new_animals":
        return ":information_source: 前日の新着なし (投稿スキップ)"
    if head == "already_posted":
        return ":information_source: 対象日は投稿済み (二重投稿防止)"
    if head == "no_api_client":
        return (
            ":warning: dry_run=false だが Threads client 未構築 (no_api_client)。"
            "THREADS_ACCESS_TOKEN / THREADS_USER_ID 設定を確認"
        )
    if head == "publish_error":
        err = (result.reason or "").split(":", 1)[1] if ":" in (result.reason or "") else ""
        return f":x: 投稿失敗 (publish_error: {err})"
    return f"unknown reason: {result.reason}"


async def _run_async(env: dict[str, str], *, cli_dry_run: bool | None) -> DigestPublishResult:
    """DB 接続を貼って publish_daily_digest を 1 回呼ぶ。対象日は実行日の前日 (JST)。"""
    from data_collector.infrastructure.database.connection import (
        DatabaseConnection,
        DatabaseSettings,
    )
    from data_collector.infrastructure.database.repository import AnimalRepository

    database_url = env.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set; cannot collect digest")
        return DigestPublishResult(
            posted=False, dry_run=False, stats=None, text=None, reason="no_database"
        )

    db_settings = DatabaseSettings(database_url=database_url)
    db_connection = DatabaseConnection(settings=db_settings)

    digest_log_path = Path(env.get("SNS_DIGEST_LOG_PATH", str(DEFAULT_DIGEST_LOG_PATH)))
    digest_log = DigestLog(path=digest_log_path)

    threads_client = build_threads_client(env)

    run_env = dict(env)
    if cli_dry_run is not None:
        run_env["THREADS_PUBLISH_DRY_RUN"] = "true" if cli_dry_run else "false"

    target_date_jst = (datetime.now(UTC).astimezone(_JST) - timedelta(days=1)).date()

    async with db_connection.get_session() as session:
        repo = AnimalRepository(session)
        return await publish_daily_digest(
            repo=repo,
            digest_log=digest_log,
            target_date_jst=target_date_jst,
            env=run_env,
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
    args = sys.argv[1:] if argv is None else argv
    cli_dry_run = True if "--dry-run" in args else None

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    env = dict(os.environ)
    result = asyncio.run(_run_async(env, cli_dry_run=cli_dry_run))
    summary = format_summary(result)
    logger.info(summary)
    _send_discord(env, summary)
    return result_to_exit_code(result)


if __name__ == "__main__":
    sys.exit(main())
