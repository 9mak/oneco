"""
StatusHistoryRepository のテスト

ステータス履歴リポジトリが要件通りに実装されているかを検証します。
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Animal, AnimalStatusHistory, Base
from src.data_collector.infrastructure.database.status_history_repository import (
    StatusHistoryRepository,
    StatusHistoryEntry,
)
from src.data_collector.domain.models import AnimalStatus


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
async def repository(async_session):
    """テスト用の StatusHistoryRepository を作成"""
    return StatusHistoryRepository(async_session)


@pytest_asyncio.fixture
async def sample_animal(async_session):
    """テスト用の動物データを作成"""
    from datetime import date
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/1",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)
    return animal


class TestStatusHistoryRepository:
    """StatusHistoryRepository のテスト"""

    @pytest.mark.asyncio
    async def test_repository_initialization(self, async_session):
        """StatusHistoryRepository が正しく初期化されるか"""
        repo = StatusHistoryRepository(async_session)
        assert repo.session == async_session

    @pytest.mark.asyncio
    async def test_record_transition_creates_history_entry(
        self, repository, sample_animal
    ):
        """record_transition() がステータス履歴エントリを作成するか"""
        entry = await repository.record_transition(
            animal_id=sample_animal.id,
            old_status=AnimalStatus.SHELTERED,
            new_status=AnimalStatus.ADOPTED,
        )

        assert isinstance(entry, StatusHistoryEntry)
        assert entry.animal_id == sample_animal.id
        assert entry.old_status == AnimalStatus.SHELTERED
        assert entry.new_status == AnimalStatus.ADOPTED
        assert entry.changed_at is not None
        assert entry.id is not None

    @pytest.mark.asyncio
    async def test_record_transition_with_changed_by(
        self, repository, sample_animal
    ):
        """record_transition() が changed_by を記録するか"""
        entry = await repository.record_transition(
            animal_id=sample_animal.id,
            old_status=AnimalStatus.SHELTERED,
            new_status=AnimalStatus.ADOPTED,
            changed_by="admin@example.com",
        )

        assert entry.changed_by == "admin@example.com"

    @pytest.mark.asyncio
    async def test_record_transition_stores_in_database(
        self, repository, async_session, sample_animal
    ):
        """record_transition() がデータベースに保存されるか"""
        await repository.record_transition(
            animal_id=sample_animal.id,
            old_status=AnimalStatus.SHELTERED,
            new_status=AnimalStatus.ADOPTED,
        )

        # データベースから直接確認
        from sqlalchemy import select
        stmt = select(AnimalStatusHistory).where(
            AnimalStatusHistory.animal_id == sample_animal.id
        )
        result = await async_session.execute(stmt)
        db_entry = result.scalar_one_or_none()

        assert db_entry is not None
        assert db_entry.old_status == "sheltered"
        assert db_entry.new_status == "adopted"

    @pytest.mark.asyncio
    async def test_get_history_returns_entries_for_animal(
        self, repository, sample_animal
    ):
        """get_history() が動物のステータス履歴を返すか"""
        # 複数の履歴エントリを作成
        await repository.record_transition(
            animal_id=sample_animal.id,
            old_status=AnimalStatus.SHELTERED,
            new_status=AnimalStatus.ADOPTED,
        )
        await repository.record_transition(
            animal_id=sample_animal.id,
            old_status=AnimalStatus.ADOPTED,
            new_status=AnimalStatus.RETURNED,
        )

        history = await repository.get_history(sample_animal.id)

        assert len(history) == 2
        assert all(isinstance(e, StatusHistoryEntry) for e in history)
        # 時系列順に返されることを確認
        assert history[0].new_status == AnimalStatus.ADOPTED
        assert history[1].new_status == AnimalStatus.RETURNED

    @pytest.mark.asyncio
    async def test_get_history_returns_empty_list_if_no_history(
        self, repository, sample_animal
    ):
        """get_history() が履歴がない場合空リストを返すか"""
        history = await repository.get_history(sample_animal.id)

        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_returns_empty_list_for_nonexistent_animal(
        self, repository
    ):
        """get_history() が存在しない動物IDの場合空リストを返すか"""
        history = await repository.get_history(99999)

        assert history == []

    @pytest.mark.asyncio
    async def test_status_history_entry_dataclass(self):
        """StatusHistoryEntry データクラスが正しく定義されているか"""
        now = datetime.now(timezone.utc)
        entry = StatusHistoryEntry(
            id=1,
            animal_id=100,
            old_status=AnimalStatus.SHELTERED,
            new_status=AnimalStatus.ADOPTED,
            changed_at=now,
            changed_by="user@example.com",
        )

        assert entry.id == 1
        assert entry.animal_id == 100
        assert entry.old_status == AnimalStatus.SHELTERED
        assert entry.new_status == AnimalStatus.ADOPTED
        assert entry.changed_at == now
        assert entry.changed_by == "user@example.com"

    @pytest.mark.asyncio
    async def test_status_history_entry_dataclass_optional_changed_by(self):
        """StatusHistoryEntry の changed_by がオプショナルか"""
        now = datetime.now(timezone.utc)
        entry = StatusHistoryEntry(
            id=1,
            animal_id=100,
            old_status=AnimalStatus.SHELTERED,
            new_status=AnimalStatus.ADOPTED,
            changed_at=now,
        )

        assert entry.changed_by is None
