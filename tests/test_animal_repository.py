"""
AnimalRepository のテスト

Repository パターンによるデータアクセス層が要件通りに実装されているかを検証します。
upsert、取得、フィルタリング、ページネーション機能をテストします。
"""

from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.domain.models import AnimalData, AnimalStatus
from src.data_collector.domain.status_transition import StatusTransitionError
from src.data_collector.infrastructure.database.models import Animal, AnimalStatusHistory, Base
from src.data_collector.infrastructure.database.repository import AnimalRepository


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
        category="adoption",
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
        category="adoption",
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
        category="adoption",
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
        category="adoption",
    )

    result = await repository.save_animal(animal_data)

    assert result.color == "黒"
    assert result.shelter_date == date(2026, 1, 6)

    # データベースのレコードが更新されていることを確認
    from sqlalchemy import select

    stmt = select(Animal).where(Animal.source_url == "https://example.com/animal/existing")
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
        category="adoption",
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
            category="adoption",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/cat",
            category="adoption",
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


@pytest.mark.asyncio
async def test_to_orm_includes_category(repository):
    """_to_orm()がcategoryフィールドを含むか"""
    animal_data = AnimalData(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/with-category",
        category="adoption",
    )

    orm_animal = repository._to_orm(animal_data)

    assert orm_animal.category == "adoption"


@pytest.mark.asyncio
async def test_to_pydantic_includes_category(repository):
    """_to_pydantic()がcategoryフィールドを含むか"""
    orm_animal = Animal(
        species="猫",
        sex="女の子",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        source_url="https://example.com/animal/with-category-orm",
        category="lost",
    )

    animal_data = repository._to_pydantic(orm_animal)

    assert animal_data.category == "lost"


@pytest.mark.asyncio
async def test_list_animals_filters_by_category_adoption(repository, async_session):
    """list_animals()がcategory='adoption'でフィルタリングできるか"""
    # テストデータを挿入
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/adoption1",
            category="adoption",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/lost1",
            category="lost",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals(category="adoption")

    assert len(result) == 1
    assert total == 1
    assert result[0].category == "adoption"


@pytest.mark.asyncio
async def test_list_animals_filters_by_category_lost(repository, async_session):
    """list_animals()がcategory='lost'でフィルタリングできるか"""
    # テストデータを挿入
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/adoption2",
            category="adoption",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/lost2",
            category="lost",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals(category="lost")

    assert len(result) == 1
    assert total == 1
    assert result[0].category == "lost"


@pytest.mark.asyncio
async def test_list_animals_without_category_returns_all(repository, async_session):
    """list_animals()でcategoryを省略すると全カテゴリが返却されるか"""
    # テストデータを挿入
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/adoption3",
            category="adoption",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/lost3",
            category="lost",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals()

    assert len(result) == 2
    assert total == 2
    categories = [a.category for a in result]
    assert "adoption" in categories
    assert "lost" in categories


# === Task 3.2: update_status() テスト ===


@pytest.mark.asyncio
async def test_update_status_changes_animal_status(repository, async_session):
    """update_status() が動物のステータスを変更できるか"""
    # テストデータを挿入
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/status1",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    result = await repository.update_status(
        animal_id=animal.id,
        new_status=AnimalStatus.ADOPTED,
    )

    assert result.status == AnimalStatus.ADOPTED
    assert result.status_changed_at is not None


@pytest.mark.asyncio
async def test_update_status_sets_outcome_date_for_adopted(repository, async_session):
    """update_status() が adopted の場合 outcome_date を設定するか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/status2",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    outcome = date(2026, 1, 20)
    result = await repository.update_status(
        animal_id=animal.id,
        new_status=AnimalStatus.ADOPTED,
        outcome_date=outcome,
    )

    assert result.outcome_date == outcome


@pytest.mark.asyncio
async def test_update_status_sets_outcome_date_for_returned(repository, async_session):
    """update_status() が returned の場合 outcome_date を設定するか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/status3",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    outcome = date(2026, 1, 20)
    result = await repository.update_status(
        animal_id=animal.id,
        new_status=AnimalStatus.RETURNED,
        outcome_date=outcome,
    )

    assert result.outcome_date == outcome


@pytest.mark.asyncio
async def test_update_status_records_history(repository, async_session):
    """update_status() がステータス履歴を記録するか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/status4",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    await repository.update_status(
        animal_id=animal.id,
        new_status=AnimalStatus.ADOPTED,
    )

    # 履歴が記録されていることを確認
    from sqlalchemy import select

    stmt = select(AnimalStatusHistory).where(AnimalStatusHistory.animal_id == animal.id)
    result = await async_session.execute(stmt)
    history = result.scalar_one_or_none()

    assert history is not None
    assert history.old_status == "sheltered"
    assert history.new_status == "adopted"


@pytest.mark.asyncio
async def test_update_status_raises_on_invalid_transition(repository, async_session):
    """update_status() が不正な遷移で StatusTransitionError を発生させるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/status5",
        category="adoption",
        status="deceased",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    with pytest.raises(StatusTransitionError):
        await repository.update_status(
            animal_id=animal.id,
            new_status=AnimalStatus.SHELTERED,
        )


@pytest.mark.asyncio
async def test_update_status_raises_on_not_found(repository):
    """update_status() が存在しない動物で例外を発生させるか"""
    with pytest.raises(Exception):  # NotFoundError
        await repository.update_status(
            animal_id=99999,
            new_status=AnimalStatus.ADOPTED,
        )


@pytest.mark.asyncio
async def test_update_status_atomic_with_history(repository, async_session):
    """update_status() がステータス更新と履歴記録を原子的に実行するか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/status6",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    # ステータスを複数回更新
    await repository.update_status(animal.id, AnimalStatus.ADOPTED)
    await repository.update_status(animal.id, AnimalStatus.RETURNED)

    # 履歴が2件記録されていることを確認
    from sqlalchemy import func, select

    stmt = (
        select(func.count())
        .select_from(AnimalStatusHistory)
        .where(AnimalStatusHistory.animal_id == animal.id)
    )
    result = await async_session.execute(stmt)
    count = result.scalar()

    assert count == 2


# === Task 3.3: ステータスフィルタリングテスト ===


@pytest.mark.asyncio
async def test_list_animals_filters_by_status(repository, async_session):
    """list_animals() が status パラメータでフィルタリングできるか"""
    # テストデータを挿入（異なるステータス）
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/status_filter1",
            category="adoption",
            status="sheltered",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/status_filter2",
            category="adoption",
            status="adopted",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals(status=AnimalStatus.SHELTERED)

    assert len(result) == 1
    assert total == 1
    assert result[0].status == AnimalStatus.SHELTERED


@pytest.mark.asyncio
async def test_list_animals_by_status_returns_filtered_animals(repository, async_session):
    """list_animals_by_status() がステータスでフィルタリングできるか"""
    # テストデータを挿入
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/by_status1",
            category="adoption",
            status="sheltered",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/by_status2",
            category="adoption",
            status="adopted",
        )
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 7),
            location="高知県",
            source_url="https://example.com/by_status3",
            category="adoption",
            status="adopted",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals_by_status(AnimalStatus.ADOPTED)

    assert len(result) == 2
    assert total == 2
    assert all(a.status == AnimalStatus.ADOPTED for a in result)


@pytest.mark.asyncio
async def test_list_animals_by_status_with_pagination(repository, async_session):
    """list_animals_by_status() がページネーションを正しく適用するか"""
    # テストデータを10件挿入（全て sheltered）
    for i in range(10):
        async_session.add(
            Animal(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url=f"https://example.com/by_status_page{i}",
                category="adoption",
                status="sheltered",
            )
        )
    await async_session.commit()

    result, total = await repository.list_animals_by_status(
        AnimalStatus.SHELTERED, limit=3, offset=2
    )

    assert len(result) == 3
    assert total == 10


@pytest.mark.asyncio
async def test_list_animals_without_status_returns_all(repository, async_session):
    """list_animals() で status を省略すると全ステータスが返却されるか"""
    # テストデータを挿入（異なるステータス）
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/no_status1",
            category="adoption",
            status="sheltered",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/no_status2",
            category="adoption",
            status="adopted",
        )
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 7),
            location="高知県",
            source_url="https://example.com/no_status3",
            category="adoption",
            status="deceased",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals()

    assert total == 3
    statuses = [a.status for a in result]
    assert AnimalStatus.SHELTERED in statuses
    assert AnimalStatus.ADOPTED in statuses
    assert AnimalStatus.DECEASED in statuses


# === Task 8.1: update_local_image_paths() テスト ===


@pytest.mark.asyncio
async def test_update_local_image_paths_sets_paths(repository, async_session):
    """update_local_image_paths() がローカル画像パスを設定できるか"""
    # テストデータを挿入
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/image_paths1",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    paths = ["a1/b2/hash1.jpg", "c3/d4/hash2.png"]
    result = await repository.update_local_image_paths(animal.id, paths)

    assert result.local_image_paths == paths


@pytest.mark.asyncio
async def test_update_local_image_paths_updates_existing(repository, async_session):
    """update_local_image_paths() が既存パスを更新できるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/image_paths2",
        category="adoption",
        status="sheltered",
        local_image_paths=["old/path.jpg"],
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    new_paths = ["new/path1.jpg", "new/path2.png"]
    result = await repository.update_local_image_paths(animal.id, new_paths)

    assert result.local_image_paths == new_paths


@pytest.mark.asyncio
async def test_update_local_image_paths_empty_list(repository, async_session):
    """update_local_image_paths() が空リストを設定できるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/image_paths3",
        category="adoption",
        status="sheltered",
        local_image_paths=["existing/path.jpg"],
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    result = await repository.update_local_image_paths(animal.id, [])

    # 空リストは None として返却される（設計上の動作）
    assert result.local_image_paths is None or result.local_image_paths == []


@pytest.mark.asyncio
async def test_update_local_image_paths_raises_on_not_found(repository):
    """update_local_image_paths() が存在しない動物で例外を発生させるか"""
    from src.data_collector.infrastructure.database.repository import NotFoundError

    with pytest.raises(NotFoundError):
        await repository.update_local_image_paths(99999, ["path.jpg"])


# === Task 9.2: find_archivable_animals() テスト ===


@pytest.mark.asyncio
async def test_find_archivable_animals_returns_animals_past_retention(repository, async_session):
    """find_archivable_animals() が保持期間経過の動物を返すか"""
    from datetime import timedelta

    # 200日前に譲渡された動物（180日保持期間を超過）
    old_outcome_date = date.today() - timedelta(days=200)
    old_status_changed_at = datetime(
        old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/archivable1",
            category="adoption",
            status="adopted",
            status_changed_at=old_status_changed_at,
            outcome_date=old_outcome_date,
        )
    )

    # 100日前に譲渡された動物（まだ保持期間内）
    recent_outcome_date = date.today() - timedelta(days=100)
    recent_status_changed_at = datetime(
        recent_outcome_date.year, recent_outcome_date.month, recent_outcome_date.day, tzinfo=UTC
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2025, 3, 1),
            location="高知県",
            source_url="https://example.com/not_archivable1",
            category="adoption",
            status="adopted",
            status_changed_at=recent_status_changed_at,
            outcome_date=recent_outcome_date,
        )
    )

    # 収容中の動物（アーカイブ対象外）
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/sheltered1",
            category="adoption",
            status="sheltered",
        )
    )
    await async_session.commit()

    result = await repository.find_archivable_animals(retention_days=180)

    assert len(result) == 1
    assert str(result[0].source_url) == "https://example.com/archivable1"


@pytest.mark.asyncio
async def test_find_archivable_animals_includes_returned_status(repository, async_session):
    """find_archivable_animals() が returned ステータスも含むか"""
    from datetime import timedelta

    # 200日前に返還された動物
    old_outcome_date = date.today() - timedelta(days=200)
    old_status_changed_at = datetime(
        old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/returned_archivable",
            category="adoption",
            status="returned",
            status_changed_at=old_status_changed_at,
            outcome_date=old_outcome_date,
        )
    )
    await async_session.commit()

    result = await repository.find_archivable_animals(retention_days=180)

    assert len(result) == 1
    assert result[0].status == AnimalStatus.RETURNED


@pytest.mark.asyncio
async def test_find_archivable_animals_respects_limit(repository, async_session):
    """find_archivable_animals() が limit を正しく適用するか"""
    from datetime import timedelta

    # 200日前に譲渡された動物を5件作成
    old_outcome_date = date.today() - timedelta(days=200)
    old_status_changed_at = datetime(
        old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
    )
    for i in range(5):
        async_session.add(
            Animal(
                species="犬",
                shelter_date=date(2025, 1, 1),
                location="高知県",
                source_url=f"https://example.com/archivable_limit{i}",
                category="adoption",
                status="adopted",
                status_changed_at=old_status_changed_at,
                outcome_date=old_outcome_date,
            )
        )
    await async_session.commit()

    result = await repository.find_archivable_animals(retention_days=180, limit=3)

    assert len(result) == 3


@pytest.mark.asyncio
async def test_find_archivable_animals_custom_retention_days(repository, async_session):
    """find_archivable_animals() がカスタム保持期間を適用するか"""
    from datetime import timedelta

    # 50日前に譲渡された動物
    outcome_date = date.today() - timedelta(days=50)
    status_changed_at = datetime(
        outcome_date.year, outcome_date.month, outcome_date.day, tzinfo=UTC
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/custom_retention",
            category="adoption",
            status="adopted",
            status_changed_at=status_changed_at,
            outcome_date=outcome_date,
        )
    )
    await async_session.commit()

    # 30日保持期間を指定（50日前は対象）
    result = await repository.find_archivable_animals(retention_days=30)
    assert len(result) == 1

    # 60日保持期間を指定（50日前は対象外）
    result = await repository.find_archivable_animals(retention_days=60)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_find_archivable_animals_returns_orm_models(repository, async_session):
    """find_archivable_animals() が ORM モデルのリストを返すか"""
    from datetime import timedelta

    old_outcome_date = date.today() - timedelta(days=200)
    old_status_changed_at = datetime(
        old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/orm_test",
            category="adoption",
            status="adopted",
            status_changed_at=old_status_changed_at,
            outcome_date=old_outcome_date,
        )
    )
    await async_session.commit()

    result = await repository.find_archivable_animals(retention_days=180)

    assert len(result) == 1
    assert isinstance(result[0], Animal)


@pytest.mark.asyncio
async def test_find_archivable_animals_excludes_deceased(repository, async_session):
    """find_archivable_animals() が deceased ステータスを除外するか"""
    from datetime import timedelta

    # 200日前に死亡した動物（アーカイブ対象外）
    old_status_changed_at = datetime.now(UTC) - timedelta(days=200)
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/deceased_test",
            category="adoption",
            status="deceased",
            status_changed_at=old_status_changed_at,
        )
    )
    await async_session.commit()

    result = await repository.find_archivable_animals(retention_days=180)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_delete_animal_removes_record(repository, async_session):
    """delete_animal() が動物レコードを削除できるか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2025, 1, 1),
        location="高知県",
        source_url="https://example.com/to_delete",
        category="adoption",
        status="adopted",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    await repository.delete_animal(animal.id)

    # 削除されていることを確認
    from sqlalchemy import select

    stmt = select(Animal).where(Animal.id == animal.id)
    result = await async_session.execute(stmt)
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_animal_raises_on_not_found(repository):
    """delete_animal() が存在しない動物で例外を発生させるか"""
    from src.data_collector.infrastructure.database.repository import NotFoundError

    with pytest.raises(NotFoundError):
        await repository.delete_animal(99999)


@pytest.mark.asyncio
async def test_get_status_counts_returns_counts_by_status(repository, async_session):
    """get_status_counts() がステータス別の件数を返すか"""
    # 異なるステータスの動物を挿入
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/count1",
            category="adoption",
            status="sheltered",
        )
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/count2",
            category="adoption",
            status="sheltered",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/count3",
            category="adoption",
            status="adopted",
        )
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/count4",
            category="adoption",
            status="deceased",
        )
    )
    await async_session.commit()

    result = await repository.get_status_counts()

    assert result["sheltered"] == 2
    assert result["adopted"] == 1
    assert result["deceased"] == 1
    assert result.get("returned", 0) == 0
