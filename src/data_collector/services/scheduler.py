"""
Scheduler - APScheduler によるアーカイブジョブのスケジューリング

アーカイブジョブを日次で自動実行するためのスケジューラ設定を提供します。

Note:
    APScheduler がインストールされていない場合は機能が制限されます。
    インストール: pip install apscheduler
"""

import logging
import os
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# APScheduler はオプショナル依存
try:
    from apscheduler.executors.asyncio import AsyncIOExecutor
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler がインストールされていません。スケジューラ機能は無効です。")


class ArchiveScheduler:
    """
    アーカイブスケジューラ

    APScheduler を使用してアーカイブジョブを日次実行します。
    """

    DEFAULT_HOUR = 2  # 毎日 02:00 JST
    DEFAULT_MINUTE = 0
    DEFAULT_TIMEZONE = "Asia/Tokyo"
    DEFAULT_MISFIRE_GRACE_TIME = 3600  # 1時間

    def __init__(
        self,
        database_url: str | None = None,
        hour: int | None = None,
        minute: int | None = None,
        timezone: str | None = None,
    ):
        """
        ArchiveScheduler を初期化

        Args:
            database_url: ジョブストア用データベースURL（省略時はメモリストア）
            hour: 実行時刻（時）
            minute: 実行時刻（分）
            timezone: タイムゾーン

        Raises:
            ImportError: APScheduler がインストールされていない場合
        """
        if not APSCHEDULER_AVAILABLE:
            raise ImportError(
                "APScheduler がインストールされていません。"
                "pip install apscheduler でインストールしてください。"
            )

        self.hour = hour if hour is not None else self.DEFAULT_HOUR
        self.minute = minute if minute is not None else self.DEFAULT_MINUTE
        self.timezone = timezone if timezone is not None else self.DEFAULT_TIMEZONE

        # ジョブストア設定
        jobstores = {}
        if database_url:
            jobstores["default"] = SQLAlchemyJobStore(url=database_url)

        # エグゼキュータ設定
        executors = {
            "default": AsyncIOExecutor(),
        }

        # ジョブデフォルト設定
        job_defaults = {
            "coalesce": True,  # 複数の遅延実行を1回にまとめる
            "max_instances": 1,  # 同時実行は1つのみ
            "misfire_grace_time": self.DEFAULT_MISFIRE_GRACE_TIME,
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self.timezone,
        )

        self._archive_job_func: Callable[[], Awaitable] | None = None

    def set_archive_job(self, job_func: Callable[[], Awaitable]) -> None:
        """
        アーカイブジョブ関数を設定

        Args:
            job_func: アーカイブジョブを実行する非同期関数
        """
        self._archive_job_func = job_func

    def start(self) -> None:
        """
        スケジューラを開始

        アーカイブジョブが設定されている場合、日次実行をスケジュールします。
        """
        if self._archive_job_func:
            # 既存のジョブを削除（冪等性確保）
            if self.scheduler.get_job("archive_job"):
                self.scheduler.remove_job("archive_job")

            # 日次実行ジョブを追加
            trigger = CronTrigger(
                hour=self.hour,
                minute=self.minute,
                timezone=self.timezone,
            )

            self.scheduler.add_job(
                self._archive_job_func,
                trigger=trigger,
                id="archive_job",
                name="Daily Archive Job",
                replace_existing=True,
            )

            logger.info(
                f"アーカイブジョブをスケジュール: "
                f"毎日 {self.hour:02d}:{self.minute:02d} ({self.timezone})"
            )

        self.scheduler.start()
        logger.info("スケジューラを開始しました")

    def stop(self, wait: bool = True) -> None:
        """
        スケジューラを停止

        Args:
            wait: 実行中のジョブの完了を待つか
        """
        self.scheduler.shutdown(wait=wait)
        logger.info("スケジューラを停止しました")

    def run_now(self) -> None:
        """
        アーカイブジョブを即座に実行（手動トリガー用）
        """
        if self._archive_job_func:
            self.scheduler.add_job(
                self._archive_job_func,
                id="archive_job_manual",
                name="Manual Archive Job",
                replace_existing=True,
            )
            logger.info("アーカイブジョブを手動実行しました")
        else:
            logger.warning("アーカイブジョブが設定されていません")

    @property
    def is_running(self) -> bool:
        """スケジューラが実行中かどうか"""
        return self.scheduler.running


def create_scheduler_from_env() -> ArchiveScheduler:
    """
    環境変数からスケジューラを作成

    環境変数:
        DATABASE_URL: ジョブストア用データベースURL
        ARCHIVE_SCHEDULE_HOUR: 実行時刻（時、デフォルト: 2）
        ARCHIVE_SCHEDULE_MINUTE: 実行時刻（分、デフォルト: 0）
        ARCHIVE_SCHEDULE_TIMEZONE: タイムゾーン（デフォルト: Asia/Tokyo）

    Returns:
        ArchiveScheduler: 設定済みスケジューラ
    """
    database_url = os.environ.get("DATABASE_URL")
    hour = os.environ.get("ARCHIVE_SCHEDULE_HOUR")
    minute = os.environ.get("ARCHIVE_SCHEDULE_MINUTE")
    timezone = os.environ.get("ARCHIVE_SCHEDULE_TIMEZONE")

    return ArchiveScheduler(
        database_url=database_url,
        hour=int(hour) if hour else None,
        minute=int(minute) if minute else None,
        timezone=timezone,
    )
