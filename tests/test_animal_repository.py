"""
AnimalRepository のテスト

Repository パターンによるデータアクセス層が要件通りに実装されているかを検証します。
upsert、取得、フィルタリング、ページネーション機能をテストします。
"""

import pytest
import pytest_asyncio
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Animal, Base
from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.data_collector.domain.models import AnimalData


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
    """テスト用のAnimalRepositoryを作成"""
    return AnimalRepository(async_session)


@pytest.mark.asyncio
async def test_repository_initialization(async_session):
    """AnimalRepositoryが正しく初期化されるか"""
    repo = AnimalRepository(async_session)
    assert repo.session == async_session


@pytest.mark.asyncio
async def test_to_orm_converts_pydantic_to_sqlalchemy(repository):
    """Pydantic AnimalDataをSQLAlchemy Animalに変換できるか"""
    animal_data = AnimalData(
        species="犬",
        sex="男の子",
        age_months=24,
        color="茶色",
        size="中型",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        phone="088-123-4567",
        image_urls=["https://example.com/img1.jpg"],
        source_url="https://example.com/animal/1",
    )

    orm_animal = repository._to_orm(animal_data)

    assert isinstance(orm_animal, Animal)
    assert orm_animal.species == "犬"
    assert orm_animal.sex == "男の子"
    assert orm_animal.age_months == 24
    assert orm_animal.shelter_date == date(2026, 1, 5)
    assert orm_animal.source_url == "https://example.com/animal/1"


@pytest.mark.asyncio
async def test_to_pydantic_converts_sqlalchemy_to_pydantic(repository):
    """SQLAlchemy AnimalをPydantic AnimalDataに変換できるか"""
    orm_animal = Animal(
        id=1,
        species="猫",
        sex="女の子",
        age_months=12,
        color="白",
        size="小型",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        phone="088-999-8888",
        image_urls=["https://example.com/img2.jpg"],
        source_url="https://example.com/animal/2",
    )

    animal_data = repository._to_pydantic(orm_animal)

    assert isinstance(animal_data, AnimalData)
    assert animal_data.species == "猫"
    assert animal_data.sex == "女の子"
    assert animal_data.age_months == 12
    assert str(animal_data.source_url) == "https://example.com/animal/2"


@pytest.mark.asyncio
async def test_save_animal_inserts_new_record(repository, async_session):
    """save_animal()が新規レコードを挿入できるか"""
    animal_data = AnimalData(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/new",
    )

    result = await repository.save_animal(animal_data)

    assert result is not None
    assert result.species == "犬"
    assert str(result.source_url) == "https://example.com/animal/new"

    # データベースに保存されていることを確認
    from sqlalchemy import select

    stmt = select(Animal).where(Animal.source_url == "https://example.com/animal/new")
    db_result = await async_session.execute(stmt)
    db_animal = db_result.scalar_one_or_none()

    assert db_animal is not None
    assert db_animal.species == "犬"


@pytest.mark.asyncio
async def test_save_animal_updates_existing_record(repository, async_session):
    """save_animal()が既存レコードを更新できるか（upsert）"""
    # 既存レコードを挿入
    existing_animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/existing",
        color="茶色",
    )
    async_session.add(existing_animal)
    await async_session.commit()

    # 同じsource_urlで異なるデータを保存
    animal_data = AnimalData(
        species="犬",
        shelter_date=date(2026, 1, 6),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/existing",
        color="黒",
    )

    result = await repository.save_animal(animal_data)

    assert result.color == "黒"
    assert result.shelter_date == date(2026, 1, 6)

    # データベースのレコードが更新されていることを確認
    from sqlalchemy import select

    stmt = select(Animal).where(
        Animal.source_url == "https://example.com/animal/existing"
    )
    db_result = await async_session.execute(stmt)
    animals = db_result.scalars().all()

    # 重複せず1件のみ存在
    assert len(animals) == 1
    assert animals[0].color == "黒"


@pytest.mark.asyncio
async def test_get_animal_by_id_returns_animal(repository, async_session):
    """get_animal_by_id()が指定IDの動物を返すか"""
    # テストデータを挿入
    animal = Animal(
        species="猫",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/100",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    result = await repository.get_animal_by_id(animal.id)

    assert result is not None
    assert result.species == "猫"
    assert str(result.source_url) == "https://example.com/animal/100"


@pytest.mark.asyncio
async def test_get_animal_by_id_returns_none_if_not_found(repository):
    """get_animal_by_id()が存在しないIDの場合Noneを返すか"""
    result = await repository.get_animal_by_id(99999)

    assert result is None


@pytest.mark.asyncio
async def test_list_animals_returns_all_animals(repository, async_session):
    """list_animals()が全ての動物を返すか"""
    # テストデータを挿入
    animals = [
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url=f"https://example.com/animal/{i}",
        )
        for i in range(5)
    ]
    for animal in animals:
        async_session.add(animal)
    await async_session.commit()

    result, total = await repository.list_animals()

    assert len(result) == 5
    assert total == 5
    assert all(isinstance(a, AnimalData) for a in result)


@pytest.mark.asyncio
async def test_list_animals_filters_by_species(repository, async_session):
    """list_animals()がspeciesでフィルタリングできるか"""
    # テストデータを挿入
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/dog",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/cat",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals(species="犬")

    assert len(result) == 1
    assert total == 1
    assert result[0].species == "犬"


@pytest.mark.asyncio
async def test_list_animals_pagination(repository, async_session):
    """list_animals()がページネーションを正しく適用するか"""
    # テストデータを10件挿入
    for i in range(10):
        async_session.add(
            Animal(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url=f"https://example.com/animal/{i}",
            )
        )
    await async_session.commit()

    # limit=3, offset=2でテスト
    result, total = await repository.list_animals(limit=3, offset=2)

    assert len(result) == 3
    assert total == 10
