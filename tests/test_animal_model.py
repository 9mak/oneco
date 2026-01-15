"""
SQLAlchemy Animal モデルのテスト

Animal テーブルのスキーマ定義、制約、インデックスが要件通りに
実装されているかを検証します。
"""

import pytest
import pytest_asyncio
from datetime import date
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Animal, Base


@pytest_asyncio.fixture
async def async_engine():
    """テスト用の非同期エンジンを作成"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # テーブル作成
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


@pytest.mark.asyncio
async def test_animal_table_exists(async_engine):
    """animalsテーブルが存在することを確認"""
    async with async_engine.connect() as conn:
        result = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).has_table("animals")
        )
        assert result is True


@pytest.mark.asyncio
async def test_animal_required_fields(async_session):
    """必須フィールド（species, shelter_date, location, source_url）が正しく設定されているか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/1",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.id is not None
    assert animal.species == "犬"
    assert animal.shelter_date == date(2026, 1, 5)
    assert animal.location == "高知県動物愛護センター"
    assert animal.source_url == "https://example.com/animal/1"


@pytest.mark.asyncio
async def test_animal_optional_fields(async_session):
    """オプショナルフィールドがNoneを許容するか"""
    animal = Animal(
        species="猫",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/2",
        sex="女の子",
        age_months=None,
        color=None,
        size=None,
        phone=None,
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.age_months is None
    assert animal.color is None
    assert animal.size is None
    assert animal.phone is None


@pytest.mark.asyncio
async def test_animal_default_values(async_session):
    """デフォルト値（sex='不明', image_urls=[]）が適用されるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/3",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.sex == "不明"
    assert animal.image_urls == []


@pytest.mark.asyncio
async def test_animal_image_urls_as_list(async_session):
    """image_urlsが配列として格納されるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/4",
        image_urls=["https://example.com/img1.jpg", "https://example.com/img2.jpg"],
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert len(animal.image_urls) == 2
    assert animal.image_urls[0] == "https://example.com/img1.jpg"
    assert animal.image_urls[1] == "https://example.com/img2.jpg"


@pytest.mark.asyncio
async def test_animal_source_url_unique_constraint(async_session):
    """source_urlのUNIQUE制約が機能するか"""
    from sqlalchemy.exc import IntegrityError

    animal1 = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/same",
    )
    async_session.add(animal1)
    await async_session.commit()

    animal2 = Animal(
        species="猫",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        source_url="https://example.com/animal/same",  # 同じURL
    )
    async_session.add(animal2)

    with pytest.raises(IntegrityError):
        await async_session.commit()


@pytest.mark.asyncio
async def test_animal_auto_increment_id(async_session):
    """IDが自動インクリメントされるか"""
    animal1 = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/5",
    )
    animal2 = Animal(
        species="猫",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        source_url="https://example.com/animal/6",
    )

    async_session.add(animal1)
    async_session.add(animal2)
    await async_session.commit()
    await async_session.refresh(animal1)
    await async_session.refresh(animal2)

    assert animal1.id is not None
    assert animal2.id is not None
    assert animal2.id > animal1.id
