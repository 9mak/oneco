#!/usr/bin/env python3
"""外部 API トークン (Groq / Threads) の失効を日次チェックして Discord 通知する CLI。

ロジック本体は src/data_collector/infrastructure/secret_health.py (テスト対象)。
本スクリプトは env を読んで呼び出す薄いラッパー。

使い方:
    GROQ_API_KEY=... THREADS_ACCESS_TOKEN=... DISCORD_WEBHOOK_URL=... \
        python3 scripts/monitoring/check_secret_health.py

終了コード:
    0: 全トークン有効 (または未設定で監視対象外)
    1: 1 件以上の失効を検知 (CI status も failure にして GitHub 上に残す二重ガード)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import httpx

# プロジェクトルートを sys.path に追加 (scripts/monitoring/check_robots.py と同パターン)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.data_collector.infrastructure.notification_client import (  # noqa: E402
    NotificationClient,
)
from src.data_collector.infrastructure.secret_health import (  # noqa: E402
    check_groq,
    check_threads,
    evaluate,
    maybe_notify,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("check_secret_health")


def main() -> int:
    groq_key = os.environ.get("GROQ_API_KEY")
    threads_token = os.environ.get("THREADS_ACCESS_TOKEN")
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")

    with httpx.Client(follow_redirects=True) as client:
        results = [
            check_groq(groq_key, client=client),
            check_threads(threads_token, client=client),
        ]

    for r in results:
        if not r.configured:
            logger.info(f"[{r.name}] {r.detail}")
        elif r.ok:
            logger.info(f"[{r.name}] OK: {r.detail}")
        else:
            logger.error(f"[{r.name}] 失効: {r.detail}")

    has_expired, message, _ = evaluate(results)
    if not has_expired:
        logger.info("全シークレット有効")
        return 0

    # Discord 通知 (webhook 未設定なら NotificationClient が no-op)
    config: dict = {}
    if discord_webhook:
        config["discord_webhook_url"] = discord_webhook
    notification_client = NotificationClient(config)
    maybe_notify(results, notification_client)

    logger.error(message)
    return 1


if __name__ == "__main__":
    sys.exit(main())
