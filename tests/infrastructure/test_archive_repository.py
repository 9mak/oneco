"""
ArchiveRepository のテスト

アーカイブデータの読み取り専用アクセス機能をテストします。
"""

from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.domain.models import AnimalData, AnimalStatus
from src.data_collector.infrastructure.database.models import Animal, AnimalArchive, Base


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


@pytest_asyncio.fixture
async def archive_repository(async_session):
    """テスト用の ArchiveRepository を作成"""
    from src.data_collector.infrastructure.database.archive_repository import ArchiveRepository

    return ArchiveRepository(async_session)


class TestArchiveRepositoryInitialization:
    """ArchiveRepository 初期化テスト"""

    @pytest.mark.asyncio
    async def test_repository_initialization(self, async_session):
        """ArchiveRepository が正しく初期化されるか"""
        from src.data_collector.infrastructure.database.archive_repository import ArchiveRepository

        repo = ArchiveRepository(async_session)
        assert repo.session == async_session


class TestGetArchivedById:
    """get_archived_by_id メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_get_archived_by_id_returns_animal(self, archive_repository, async_session):
        """get_archived_by_id() がアーカイブから動物データを取得できるか"""
        # アーカイブテストデータを挿入
        archived_animal = AnimalArchive(
            original_id=100,
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            size="中型",
            shelter_date=date(2025, 6, 1),
            location="高知県動物愛護センター",
            phone="088-123-4567",
            image_urls=["https://example.com/img1.jpg"],
            local_image_paths=["a1/b2/hash1.jpg"],
            source_url="https://example.com/animal/archived1",
            category="adoption",
            status="adopted",
            status_changed_at=datetime(2025, 6, 15, tzinfo=UTC),
            outcome_date=date(2025, 6, 15),
            archived_at=datetime(2025, 12, 15, tzinfo=UTC),
        )
        async_session.add(archived_animal)
        await async_session.commit()
        await async_session.refresh(archived_animal)

        result = await archive_repository.get_archived_by_id(archived_animal.id)

        assert result is not None
        assert result.species == "犬"
        assert result.status == AnimalStatus.ADOPTED
        assert str(result.source_url) == "https://example.com/animal/archived1"

    @pytest.mark.asyncio
    async def test_get_archived_by_id_returns_none_if_not_found(self, archive_repository):
        """get_archived_by_id() が存在しない ID の場合 None を返すか"""
        result = await archive_repository.get_archived_by_id(99999)
        assert result is None


class TestListArchived:
    """list_archived メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_list_archived_returns_all_archived(self, archive_repository, async_session):
        """list_archived() がすべてのアーカイブデータを返すか"""
        # アーカイブテストデータを複数挿入
        for i in range(5):
            archived_animal = AnimalArchive(
                original_id=100 + i,
                species="犬" if i % 2 == 0 else "猫",
                sex="男の子",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url=f"https://example.com/animal/archived{i}",
                category="adoption",
                status="adopted",
                archived_at=datetime(2025, 12, 15, tzinfo=UTC),
            )
            async_session.add(archived_animal)
        await async_session.commit()

        result, total = await archive_repository.list_archived()

        assert len(result) == 5
        assert total == 5
        assert all(isinstance(a, AnimalData) for a in result)

    @pytest.mark.asyncio
    async def test_list_archived_filters_by_species(self, archive_repository, async_session):
        """list_archived() が species でフィルタリングできるか"""
        # 異なる種別のアーカイブデータを挿入
        async_session.add(
            AnimalArchive(
                original_id=101,
                species="犬",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url="https://example.com/archived_dog",
                category="adoption",
                status="adopted",
                archived_at=datetime.now(UTC),
            )
        )
        async_session.add(
            AnimalArchive(
                original_id=102,
                species="猫",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url="https://example.com/archived_cat",
                category="adoption",
                status="adopted",
                archived_at=datetime.now(UTC),
            )
        )
        await async_session.commit()

        result, total = await archive_repository.list_archived(species="犬")

        assert len(result) == 1
        assert total == 1
        assert result[0].species == "犬"

    @pytest.mark.asyncio
    async def test_list_archived_filters_by_archived_from(self, archive_repository, async_session):
        """list_archived() が archived_from でフィルタリングできるか"""
        # 異なる日時のアーカイブデータを挿入
        async_session.add(
            AnimalArchive(
                original_id=103,
                species="犬",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url="https://example.com/archived_old",
                category="adoption",
                status="adopted",
                archived_at=datetime(2025, 10, 1, tzinfo=UTC),
            )
        )
        async_session.add(
            AnimalArchive(
                original_id=104,
                species="猫",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url="https://example.com/archived_new",
                category="adoption",
                status="adopted",
                archived_at=datetime(2025, 12, 1, tzinfo=UTC),
            )
        )
        await async_session.commit()

        result, total = await archive_repository.list_archived(archived_from=date(2025, 11, 1))

        assert len(result) == 1
        assert total == 1
        assert str(result[0].source_url) == "https://example.com/archived_new"

    @pytest.mark.asyncio
    async def test_list_archived_filters_by_archived_to(self, archive_repository, async_session):
        """list_archived() が archived_to でフィルタリングできるか"""
        async_session.add(
            AnimalArchive(
                original_id=105,
                species="犬",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url="https://example.com/archived_early",
                category="adoption",
                status="adopted",
                archived_at=datetime(2025, 9, 1, tzinfo=UTC),
            )
        )
        async_session.add(
            AnimalArchive(
                original_id=106,
                species="猫",
                shelter_date=date(2025, 6, 1),
                location="高知県",
                source_url="https://example.com/archived_late",
                category="adoption",
                status="adopted",
                archived_at=datetime(2025, 12, 1, tzinfo=UTC),
            )
        )
        await async_session.commit()

        result, total = await archive_repository.list_archived(archived_to=date(2025, 10, 1))

        assert len(result) == 1
        assert total == 1
        assert str(result[0].source_url) == "https://example.com/archived_early"

    @pytest.mark.asyncio
    async def test_list_archived_pagination(self, archive_repository, async_session):
        """list_archived() がページネーションを正しく適用するか"""
        # アーカイブテストデータを10件挿入
        for i in range(10):
            async_session.add(
                AnimalArchive(
                    original_id=200 + i,
                    species="犬",
                    shelter_date=date(2025, 6, 1),
                    location="高知県",
                    source_url=f"https://example.com/archived_page{i}",
                    category="adoption",
                    status="adopted",
                    archived_at=datetime(2025, 12, 15, tzinfo=UTC),
                )
            )
        await async_session.commit()

        result, total = await archive_repository.list_archived(limit=3, offset=2)

        assert len(result) == 3
        assert total == 10


class TestInsertArchive:
    """insert_archive メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_insert_archive_inserts_data(self, archive_repository, async_session):
        """insert_archive() がアーカイブにデータを挿入できるか"""
        from src.data_collector.infrastructure.database.models import Animal

        # 元となる動物データを作成
        animal = Animal(
            id=500,
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            size="中型",
            shelter_date=date(2025, 6, 1),
            location="高知県動物愛護センター",
            phone="088-123-4567",
            image_urls=["https://example.com/img1.jpg"],
            local_image_paths=["a1/b2/hash1.jpg"],
            source_url="https://example.com/animal/to_archive",
            category="adoption",
            status="adopted",
            status_changed_at=datetime(2025, 6, 15, tzinfo=UTC),
            outcome_date=date(2025, 6, 15),
        )
        async_session.add(animal)
        await async_session.commit()
        await async_session.refresh(animal)

        # アーカイブに挿入
        await archive_repository.insert_archive(animal)

        # 挿入されていることを確認
        from sqlalchemy import select

        stmt = select(AnimalArchive).where(
            AnimalArchive.source_url == "https://example.com/animal/to_archive"
        )
        result = await async_session.execute(stmt)
        archived = result.scalar_one_or_none()

        assert archived is not None
        assert archived.original_id == 500
        assert archived.species == "犬"
        assert archived.status == "adopted"
        assert archived.archived_at is not None

    @pytest.mark.asyncio
    async def test_insert_archive_preserves_all_fields(self, archive_repository, async_session):
        """insert_archive() が全フィールドを保持するか"""
        animal = Animal(
            id=501,
            species="猫",
            sex="女の子",
            age_months=12,
            color="白",
            size="小型",
            shelter_date=date(2025, 5, 1),
            location="東京都",
            phone="03-1234-5678",
            image_urls=["https://example.com/img2.jpg", "https://example.com/img3.jpg"],
            local_image_paths=["c3/d4/hash2.jpg"],
            source_url="https://example.com/animal/preserve_fields",
            category="lost",
            status="returned",
            status_changed_at=datetime(2025, 5, 20, tzinfo=UTC),
            outcome_date=date(2025, 5, 20),
        )
        async_session.add(animal)
        await async_session.commit()
        await async_session.refresh(animal)

        await archive_repository.insert_archive(animal)

        from sqlalchemy import select

        stmt = select(AnimalArchive).where(AnimalArchive.original_id == 501)
        result = await async_session.execute(stmt)
        archived = result.scalar_one()

        assert archived.species == "猫"
        assert archived.sex == "女の子"
        assert archived.age_months == 12
        assert archived.color == "白"
        assert archived.size == "小型"
        assert archived.shelter_date == date(2025, 5, 1)
        assert archived.location == "東京都"
        assert archived.phone == "03-1234-5678"
        assert len(archived.image_urls) == 2
        assert archived.local_image_paths == ["c3/d4/hash2.jpg"]
        assert archived.category == "lost"
        assert archived.status == "returned"
        assert archived.outcome_date == date(2025, 5, 20)


class TestReadOnlyConstraint:
    """読み取り専用制約のテスト"""

    @pytest.mark.asyncio
    async def test_archive_repository_has_no_update_method(self, archive_repository):
        """ArchiveRepository に update メソッドがないことを確認"""
        assert not hasattr(archive_repository, "update_archive")

    @pytest.mark.asyncio
    async def test_archive_repository_has_no_delete_method(self, archive_repository):
        """ArchiveRepository に delete メソッドがないことを確認"""
        assert not hasattr(archive_repository, "delete_archive")
