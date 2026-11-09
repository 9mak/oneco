"""__main__.py の卒業個体アーカイブ配線 (T428) のテスト。

ArchiveService.run_archive_job は 2026-09-19 時点でどこからも呼ばれておらず、
T427 で adopted/returned が prune で消えなくなった結果、保持期間を過ぎても
animals に無期限に溜まる状態だった。夜間収集の末尾で 1 回呼ぶ配線と、
既定 (無効) では件数を数えるだけで行を動かさない dry-run ゲートを検証する。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from data_collector.__main__ import _archive_job_enabled, run_archive_job
from data_collector.infrastructure.database.connection import DatabaseConnection, DatabaseSettings
from src.data_collector.infrastructure.database.models import Animal, AnimalArchive, Base


def _animal(source_url: str, *, status: str, days_ago: int) -> Animal:
    changed = datetime.now(UTC) - timedelta(days=days_ago)
    return Animal(
        species="犬",
        shelter_date=date(2025, 1, 1),
        location="高知県",
        source_url=source_url,
        category="adoption",
        status=status,
        status_changed_at=changed,
        outcome_date=changed.date(),
    )


@pytest.fixture
def db(tmp_path):
    """ファイル SQLite。run_archive_job は asyncio.run で自前のループを作るため、
    :memory: だとエンジンごとに別 DB になりテーブルが見えない。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'archive_wiring.db'}"

    async def _seed() -> None:
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()
        conn = DatabaseConnection(settings=DatabaseSettings(database_url=url))
        async with conn.get_session() as session:
            session.add_all(
                [
                    # 保持期間超過の卒業個体 (退避対象)
                    _animal("https://example.com/old-adopted", status="adopted", days_ago=200),
                    _animal("https://example.com/old-returned", status="returned", days_ago=181),
                    # 保持期間内の卒業個体 (まだ残す)
                    _animal("https://example.com/recent-adopted", status="adopted", days_ago=30),
                    # 死亡は退避対象外 (find_archivable_animals の仕様)
                    _animal("https://example.com/old-deceased", status="deceased", days_ago=400),
                    # 収容中
                    _animal("https://example.com/sheltered", status="sheltered", days_ago=400),
                ]
            )
        await conn.close()

    asyncio.run(_seed())
    return DatabaseConnection(settings=DatabaseSettings(database_url=url))


def _counts(db: DatabaseConnection) -> tuple[int, int]:
    async def _go() -> tuple[int, int]:
        conn = DatabaseConnection(settings=db.settings)
        try:
            async with conn.get_session() as session:
                animals = await session.scalar(select(func.count()).select_from(Animal))
                archived = await session.scalar(select(func.count()).select_from(AnimalArchive))
                return int(animals or 0), int(archived or 0)
        finally:
            await conn.close()

    return asyncio.run(_go())


def _remaining_urls(db: DatabaseConnection) -> set[str]:
    async def _go() -> set[str]:
        conn = DatabaseConnection(settings=db.settings)
        try:
            async with conn.get_session() as session:
                rows = await session.execute(select(Animal.source_url))
                return {r[0] for r in rows}
        finally:
            await conn.close()

    return asyncio.run(_go())


class TestArchiveJobGate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ONECO_ARCHIVE_JOB_ENABLED", raising=False)
        assert _archive_job_enabled() is False

    def test_enabled_when_true(self, monkeypatch):
        monkeypatch.setenv("ONECO_ARCHIVE_JOB_ENABLED", "TRUE")
        assert _archive_job_enabled() is True


class TestRunArchiveJob:
    def test_no_database_is_noop(self):
        summary = run_archive_job(None, logging.getLogger("t"), enabled=True)
        assert summary is None

    def test_dry_run_counts_but_moves_nothing(self, db):
        summary = run_archive_job(db, logging.getLogger("t"), enabled=False)

        assert summary is not None
        assert summary.enabled is False
        assert summary.candidates == 2
        assert summary.archived == 0
        assert _counts(db) == (5, 0)

    def test_enabled_moves_expired_graduates_only(self, db):
        summary = run_archive_job(db, logging.getLogger("t"), enabled=True)

        assert summary is not None
        assert summary.enabled is True
        assert summary.candidates == 2
        assert summary.archived == 2
        assert summary.errors == 0
        assert _counts(db) == (3, 2)
        assert _remaining_urls(db) == {
            "https://example.com/recent-adopted",
            "https://example.com/old-deceased",
            "https://example.com/sheltered",
        }

    def test_second_run_is_idempotent(self, db):
        run_archive_job(db, logging.getLogger("t"), enabled=True)
        summary = run_archive_job(db, logging.getLogger("t"), enabled=True)

        assert summary is not None
        assert summary.candidates == 0
        assert summary.archived == 0
        assert _counts(db) == (3, 2)

    def test_database_error_is_swallowed(self, tmp_path):
        """best-effort: アーカイブ失敗で収集パイプラインを落とさない"""
        broken = DatabaseConnection(
            settings=DatabaseSettings(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'missing-dir' / 'x.db'}"
            )
        )
        summary = run_archive_job(broken, logging.getLogger("t"), enabled=True)
        assert summary is None
