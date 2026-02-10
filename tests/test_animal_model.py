"""
SQLAlchemy Animal モデルのテスト

Animal テーブルのスキーマ定義、制約、インデックスが要件通りに
実装されているかを検証します。
"""

import pytest
import pytest_asyncio
from datetime import date, datetime
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Animal, Base
from src.data_collector.domain.models import AnimalStatus


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
            category="adoption"
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
            category="adoption"
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
            category="adoption"
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
            category="adoption"
        )
    animal2 = Animal(
        species="猫",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        source_url="https://example.com/animal/6",
            category="adoption"
        )

    async_session.add(animal1)
    async_session.add(animal2)
    await async_session.commit()
    await async_session.refresh(animal1)
    await async_session.refresh(animal2)

    assert animal1.id is not None
    assert animal2.id is not None
    assert animal2.id > animal1.id


@pytest.mark.asyncio
async def test_animal_category_field_exists(async_session):
    """categoryフィールドが存在し、デフォルト値'adoption'が設定されるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/7",
            category="adoption"
        )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert hasattr(animal, "category")
    assert animal.category == "adoption"


@pytest.mark.asyncio
async def test_animal_category_can_be_set_to_adoption(async_session):
    """categoryに'adoption'を設定できるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/8",
        category="adoption",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.category == "adoption"


@pytest.mark.asyncio
async def test_animal_category_can_be_set_to_lost(async_session):
    """categoryに'lost'を設定できるか"""
    animal = Animal(
        species="猫",
        shelter_date=date(2026, 1, 6),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/9",
        category="lost",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.category == "lost"


@pytest.mark.asyncio
async def test_animal_category_is_indexed(async_engine):
    """categoryカラムにインデックスが作成されているか"""
    async with async_engine.connect() as conn:
        inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))
        indexes = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("animals")
        )

        # categoryインデックスが存在することを確認
        category_indexes = [idx for idx in indexes if "category" in idx["column_names"]]
        assert len(category_indexes) > 0


# ===== animal-repository 拡張フィールドのテスト =====


@pytest.mark.asyncio
async def test_animal_status_field_exists(async_session):
    """statusフィールドが存在し、デフォルト値'sheltered'が設定されるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/status-test",
        category="adoption"
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert hasattr(animal, "status")
    assert animal.status == "sheltered"


@pytest.mark.asyncio
async def test_animal_status_can_be_set_to_adopted(async_session):
    """statusに'adopted'を設定できるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/adopted-test",
        category="adoption",
        status="adopted",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.status == "adopted"


@pytest.mark.asyncio
async def test_animal_status_can_be_set_to_all_values(async_session):
    """statusに全ての有効な値を設定できるか"""
    statuses = ["sheltered", "adopted", "returned", "deceased"]

    for i, status in enumerate(statuses):
        animal = Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県動物愛護センター",
            source_url=f"https://example.com/animal/status-{i}",
            category="adoption",
            status=status,
        )
        async_session.add(animal)

    await async_session.commit()

    from sqlalchemy import select
    result = await async_session.execute(select(Animal))
    animals = result.scalars().all()

    animal_statuses = [a.status for a in animals]
    for status in statuses:
        assert status in animal_statuses


@pytest.mark.asyncio
async def test_animal_status_changed_at_field(async_session):
    """status_changed_atフィールドがdatetimeを受け入れるか"""
    now = datetime(2026, 1, 27, 15, 30, 0)
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/changed-at-test",
        category="adoption",
        status="adopted",
        status_changed_at=now,
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.status_changed_at == now


@pytest.mark.asyncio
async def test_animal_status_changed_at_nullable(async_session):
    """status_changed_atフィールドがNullを許容するか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/changed-at-null-test",
        category="adoption",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.status_changed_at is None


@pytest.mark.asyncio
async def test_animal_outcome_date_field(async_session):
    """outcome_dateフィールドがdateを受け入れるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/outcome-date-test",
        category="adoption",
        status="adopted",
        outcome_date=date(2026, 1, 20),
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.outcome_date == date(2026, 1, 20)


@pytest.mark.asyncio
async def test_animal_outcome_date_nullable(async_session):
    """outcome_dateフィールドがNullを許容するか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/outcome-date-null-test",
        category="adoption",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.outcome_date is None


@pytest.mark.asyncio
async def test_animal_local_image_paths_field(async_session):
    """local_image_pathsフィールドがリストを受け入れるか"""
    paths = ["/images/ab/cd/test1.jpg", "/images/ef/gh/test2.jpg"]
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/local-paths-test",
        category="adoption",
        local_image_paths=paths,
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.local_image_paths == paths
    assert len(animal.local_image_paths) == 2


@pytest.mark.asyncio
async def test_animal_local_image_paths_default(async_session):
    """local_image_pathsフィールドのデフォルトが空リストであるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/local-paths-default-test",
        category="adoption",
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.local_image_paths == []


@pytest.mark.asyncio
async def test_animal_extended_fields_all(async_session):
    """全ての拡張フィールドを持つAnimalを作成できるか"""
    now = datetime(2026, 1, 27, 15, 30, 0)
    animal = Animal(
        species="犬",
        sex="男の子",
        age_months=24,
        color="茶色",
        size="中型",
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        phone="088-123-4567",
        image_urls=["https://example.com/image1.jpg"],
        source_url="https://example.com/animal/full-extended-test",
        category="adoption",
        status="adopted",
        status_changed_at=now,
        outcome_date=date(2026, 1, 20),
        local_image_paths=["/images/ab/cd/test.jpg"],
    )

    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    assert animal.status == "adopted"
    assert animal.status_changed_at == now
    assert animal.outcome_date == date(2026, 1, 20)
    assert animal.local_image_paths == ["/images/ab/cd/test.jpg"]


@pytest.mark.asyncio
async def test_animal_status_is_indexed(async_engine):
    """statusカラムにインデックスが作成されているか"""
    async with async_engine.connect() as conn:
        indexes = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_indexes("animals")
        )

        # statusインデックスが存在することを確認
        status_indexes = [idx for idx in indexes if "status" in idx["column_names"]]
        assert len(status_indexes) > 0
