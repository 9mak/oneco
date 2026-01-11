"""CLI エントリーポイント"""

import sys
import logging
import os

from .orchestration.collector_service import CollectorService
from .adapters.kochi_adapter import KochiAdapter
from .domain.diff_detector import DiffDetector
from .infrastructure.snapshot_store import SnapshotStore
from .infrastructure.output_writer import OutputWriter
from .infrastructure.notification_client import NotificationClient


def main():
    """
    CLI エントリーポイント

    Usage:
        python -m data_collector

    Exit codes:
        0: 成功
        1: 失敗

    Requirements: 6.1
    """
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    try:
        # 依存関係の初期化
        adapter = KochiAdapter()
        snapshot_store = SnapshotStore()
        diff_detector = DiffDetector(snapshot_store)
        output_writer = OutputWriter()

        # 通知設定を環境変数から読み込み
        notification_config = {
            "email": os.environ.get("NOTIFICATION_EMAIL", ""),
            "slack_webhook_url": os.environ.get("SLACK_WEBHOOK_URL", "")
        }
        notification_client = NotificationClient(notification_config)

        # CollectorService の初期化
        service = CollectorService(
            adapter=adapter,
            diff_detector=diff_detector,
            output_writer=output_writer,
            notification_client=notification_client,
            snapshot_store=snapshot_store
        )

        # 収集実行
        logger.info("Starting data collection...")
        result = service.run_collection()

        # 結果ログ出力
        if result.success:
            logger.info(
                f"Collection completed successfully: "
                f"{result.total_collected} animals collected, "
                f"{result.new_count} new, "
                f"{result.updated_count} updated, "
                f"{result.deleted_count} deleted candidates"
            )
            sys.exit(0)
        else:
            logger.error(
                f"Collection failed: {', '.join(result.errors)}"
            )
            sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
