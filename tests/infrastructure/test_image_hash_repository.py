"""ImageHashRepository のユニットテスト"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.data_collector.infrastructure.database.models import Base, ImageHash
from src.data_collector.infrastructure.database.image_hash_repository import (
    ImageHashRepository,
)


@pytest_asyncio.fixture
async def async_engine():
    """テスト用の非同期エンジンを作成"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """テスト用の非同期セッションを作成"""
    async_session_maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session
        await session.rollback()


class TestImageHashRepository:
    """ImageHashRepository のテストケース"""

    @pytest.fixture
    def sample_hash(self) -> str:
        """サンプルSHA-256ハッシュ"""
        return "a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd"

    @pytest.fixture
    def sample_path(self) -> str:
        """サンプルパス"""
        return "a1/b2/a1b2c3d4e5f6789012345678901234567890123456789012345678901234abcd.jpg"

    # === find_by_hash() のテスト ===

    @pytest.mark.asyncio
    async def test_find_by_hash_returns_none_for_nonexistent(
        self, async_session: AsyncSession, sample_hash: str
    ):
        """find_by_hash() が存在しないハッシュに対して None を返すことを確認"""
        repo = ImageHashRepository(async_session)

        result = await repo.find_by_hash(sample_hash)

        assert result is None

    @pytest.mark.asyncio
    async def test_find_by_hash_returns_record(
        self, async_session: AsyncSession, sample_hash: str, sample_path: str
    ):
        """find_by_hash() が存在するハッシュのレコードを返すことを確認"""
        repo = ImageHashRepository(async_session)
        # 事前にレコードを作成
        await repo.register(sample_hash, sample_path, 1024)
        await async_session.commit()

        result = await repo.find_by_hash(sample_hash)

        assert result is not None
        assert result.hash == sample_hash
        assert result.local_path == sample_path
        assert result.file_size == 1024

    # === register() のテスト ===

    @pytest.mark.asyncio
    async def test_register_creates_new_record(
        self, async_session: AsyncSession, sample_hash: str, sample_path: str
    ):
        """register() が新しいレコードを作成することを確認"""
        repo = ImageHashRepository(async_session)

        result = await repo.register(sample_hash, sample_path, 2048)
        await async_session.commit()

        assert result is not None
        assert result.hash == sample_hash
        assert result.local_path == sample_path
        assert result.file_size == 2048
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_register_returns_existing_record(
        self, async_session: AsyncSession, sample_hash: str, sample_path: str
    ):
        """register() が既存レコードに対して同じレコードを返すことを確認"""
        repo = ImageHashRepository(async_session)

        # 1回目の登録
        first = await repo.register(sample_hash, sample_path, 1024)
        await async_session.commit()

        # 2回目の登録（同じハッシュ）
        second = await repo.register(sample_hash, "different/path.jpg", 2048)
        await async_session.commit()

        # 最初のレコードが返される
        assert second.id == first.id
        assert second.local_path == sample_path  # パスは変わらない
        assert second.file_size == 1024  # サイズも変わらない

    # === check_duplicate() のテスト ===

    @pytest.mark.asyncio
    async def test_check_duplicate_returns_none_for_new_hash(
        self, async_session: AsyncSession, sample_hash: str
    ):
        """check_duplicate() が新規ハッシュに対して None を返すことを確認"""
        repo = ImageHashRepository(async_session)

        result = await repo.check_duplicate(sample_hash)

        assert result is None

    @pytest.mark.asyncio
    async def test_check_duplicate_returns_path_for_existing(
        self, async_session: AsyncSession, sample_hash: str, sample_path: str
    ):
        """check_duplicate() が既存ハッシュに対してパスを返すことを確認"""
        repo = ImageHashRepository(async_session)
        await repo.register(sample_hash, sample_path, 1024)
        await async_session.commit()

        result = await repo.check_duplicate(sample_hash)

        assert result == sample_path

    # === delete() のテスト ===

    @pytest.mark.asyncio
    async def test_delete_removes_record(
        self, async_session: AsyncSession, sample_hash: str, sample_path: str
    ):
        """delete() がレコードを削除することを確認"""
        repo = ImageHashRepository(async_session)
        await repo.register(sample_hash, sample_path, 1024)
        await async_session.commit()

        result = await repo.delete(sample_hash)
        await async_session.commit()

        assert result is True
        # 削除後は見つからない
        found = await repo.find_by_hash(sample_hash)
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_returns_false_for_nonexistent(
        self, async_session: AsyncSession, sample_hash: str
    ):
        """delete() が存在しないハッシュに対して False を返すことを確認"""
        repo = ImageHashRepository(async_session)

        result = await repo.delete(sample_hash)

        assert result is False

    # === count() のテスト ===

    @pytest.mark.asyncio
    async def test_count_returns_zero_for_empty(self, async_session: AsyncSession):
        """count() が空の場合に 0 を返すことを確認"""
        repo = ImageHashRepository(async_session)

        result = await repo.count()

        assert result == 0

    @pytest.mark.asyncio
    async def test_count_returns_correct_count(self, async_session: AsyncSession):
        """count() が正しい件数を返すことを確認"""
        repo = ImageHashRepository(async_session)
        # 3つのレコードを登録
        for i in range(3):
            hash_val = f"hash{i}" + "0" * 59
            await repo.register(hash_val, f"path{i}.jpg", 100 * (i + 1))
        await async_session.commit()

        result = await repo.count()

        assert result == 3

    # === total_size() のテスト ===

    @pytest.mark.asyncio
    async def test_total_size_returns_zero_for_empty(self, async_session: AsyncSession):
        """total_size() が空の場合に 0 を返すことを確認"""
        repo = ImageHashRepository(async_session)

        result = await repo.total_size()

        assert result == 0

    @pytest.mark.asyncio
    async def test_total_size_returns_sum_of_sizes(self, async_session: AsyncSession):
        """total_size() がサイズの合計を返すことを確認"""
        repo = ImageHashRepository(async_session)
        # 異なるサイズで3つのレコードを登録
        for i in range(3):
            hash_val = f"hash{i}" + "0" * 59
            await repo.register(hash_val, f"path{i}.jpg", 100 * (i + 1))
        await async_session.commit()

        result = await repo.total_size()

        assert result == 100 + 200 + 300  # 600
