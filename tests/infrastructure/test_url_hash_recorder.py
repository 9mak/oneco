"""URLHashRecorder のユニットテスト

Phase 1 MVP: 画像URLのSHA-256ハッシュをimage_hashesテーブルに記録する。
ファイル本体のダウンロードはせず、URL文字列のハッシュのみを蓄積することで
将来の重複検出（複数自治体での同一URL掲載など）の足場にする。
"""

import hashlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.database.image_hash_repository import (
    ImageHashRepository,
)
from src.data_collector.infrastructure.database.models import Base
from src.data_collector.infrastructure.url_hash_recorder import URLHashRecorder


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


class TestComputeUrlHash:
    def test_returns_64_char_hex(self):
        h = URLHashRecorder.compute_url_hash("https://example.com/cat.jpg")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_is_deterministic(self):
        url = "https://example.com/cat.jpg"
        assert URLHashRecorder.compute_url_hash(url) == URLHashRecorder.compute_url_hash(url)

    def test_matches_sha256_of_url(self):
        url = "https://example.com/cat.jpg"
        expected = hashlib.sha256(url.encode("utf-8")).hexdigest()
        assert URLHashRecorder.compute_url_hash(url) == expected

    def test_different_urls_produce_different_hashes(self):
        h1 = URLHashRecorder.compute_url_hash("https://example.com/a.jpg")
        h2 = URLHashRecorder.compute_url_hash("https://example.com/b.jpg")
        assert h1 != h2


class TestRecordUrls:
    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self, async_session: AsyncSession):
        recorder = URLHashRecorder(async_session)
        result = await recorder.record_urls([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_new_urls_are_registered(self, async_session: AsyncSession):
        recorder = URLHashRecorder(async_session)
        urls = ["https://example.com/a.jpg", "https://example.com/b.jpg"]

        result = await recorder.record_urls(urls)
        await async_session.commit()

        assert result == {urls[0]: True, urls[1]: True}

        repo = ImageHashRepository(async_session)
        assert await repo.count() == 2

    @pytest.mark.asyncio
    async def test_existing_url_is_not_reregistered(self, async_session: AsyncSession):
        recorder = URLHashRecorder(async_session)
        url = "https://example.com/dup.jpg"

        first = await recorder.record_urls([url])
        await async_session.commit()
        assert first == {url: True}

        second = await recorder.record_urls([url])
        await async_session.commit()
        assert second == {url: False}

        repo = ImageHashRepository(async_session)
        assert await repo.count() == 1

    @pytest.mark.asyncio
    async def test_duplicates_within_batch_handled(self, async_session: AsyncSession):
        """同一バッチ内に重複URLがあっても1件だけ登録される"""
        recorder = URLHashRecorder(async_session)
        url = "https://example.com/same.jpg"

        result = await recorder.record_urls([url, url])
        await async_session.commit()

        assert result[url] is True
        repo = ImageHashRepository(async_session)
        assert await repo.count() == 1

    @pytest.mark.asyncio
    async def test_empty_strings_are_skipped(self, async_session: AsyncSession):
        recorder = URLHashRecorder(async_session)

        result = await recorder.record_urls(["", "https://example.com/x.jpg"])
        await async_session.commit()

        assert "" not in result
        assert result["https://example.com/x.jpg"] is True
        repo = ImageHashRepository(async_session)
        assert await repo.count() == 1

    @pytest.mark.asyncio
    async def test_stored_record_uses_url_as_local_path(self, async_session: AsyncSession):
        """Phase 1 MVP: ファイル未ダウンロード状態で local_path に URL を保存"""
        recorder = URLHashRecorder(async_session)
        url = "https://example.com/cat.jpg"

        await recorder.record_urls([url])
        await async_session.commit()

        repo = ImageHashRepository(async_session)
        record = await repo.find_by_hash(URLHashRecorder.compute_url_hash(url))
        assert record is not None
        assert record.local_path == url
        assert record.file_size == 0
