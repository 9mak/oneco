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
async def test_get_animal_id_by_source_url_returns_id(repository, async_session):
    """get_animal_id_by_source_url()が一致するsource_urlのidを返すか"""
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/200",
        category="adoption",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    result = await repository.get_animal_id_by_source_url("https://example.com/animal/200")

    assert result == animal.id


@pytest.mark.asyncio
async def test_get_animal_id_by_source_url_returns_none_if_not_found(repository):
    """get_animal_id_by_source_url()が一致するレコードなしの場合Noneを返すか"""
    result = await repository.get_animal_id_by_source_url("https://example.com/no-such-animal")

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
async def test_list_animals_location_wildcard_is_literal(repository, async_session):
    """location の % が LIKE ワイルドカードとして解釈されない（リテラル一致）。

    エスケープが無いと location=% で全件マッチしてしまう。
    """
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
            location="徳島県",
            source_url="https://example.com/cat",
            category="adoption",
        )
    )
    await async_session.commit()

    # 単独の '%' をリテラルとして扱えば 0 件 (全件マッチではない)
    result, total = await repository.list_animals(location="%")
    assert total == 0
    assert result == []

    # 通常の部分一致は引き続き動作
    result, total = await repository.list_animals(location="高知")
    assert total == 1
    assert result[0].location == "高知県"


@pytest.mark.asyncio
async def test_list_animals_q_underscore_is_literal(repository, async_session):
    """q の _ が任意 1 文字に化けない（リテラル一致）。"""
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="A_B センター",
            source_url="https://example.com/lit",
            category="adoption",
        )
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="AXB センター",
            source_url="https://example.com/wild",
            category="adoption",
        )
    )
    await async_session.commit()

    # '_' をリテラルとして扱えば AXB はヒットしない
    result, total = await repository.list_animals(q="A_B")
    assert total == 1
    assert result[0].location == "A_B センター"


@pytest.mark.asyncio
async def test_save_animal_records_source_site(repository, async_session):
    """save_animal は渡された source_site を記録する（消滅同期削除のスコープ用）"""
    from sqlalchemy import select

    data = AnimalData(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/site-tagged",
        category="adoption",
    )
    await repository.save_animal(data, source_site="高知県動物愛護センター")

    orm = (
        await async_session.execute(
            select(Animal).where(Animal.source_url == "https://example.com/site-tagged")
        )
    ).scalar_one()
    assert orm.source_site == "高知県動物愛護センター"


@pytest.mark.asyncio
async def test_prune_disappeared_removes_only_gone_within_site(repository, async_session):
    """収集で見つからなかった動物だけを、対象サイトに限って削除する（ソースと同期）"""
    from sqlalchemy import select

    site = "高知サイト"
    other = "徳島サイト"
    async_session.add_all(
        [
            Animal(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://ex.com/keep",
                category="adoption",
                source_site=site,
            ),
            Animal(
                species="猫",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://ex.com/gone",
                category="adoption",
                source_site=site,
            ),
            Animal(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="徳島県",
                source_url="https://ex.com/other-site",
                category="adoption",
                source_site=other,
            ),
        ]
    )
    await async_session.commit()

    removed = await repository.prune_disappeared(site, {"https://ex.com/keep"})

    assert removed == 1
    urls = {r.source_url for r in (await async_session.execute(select(Animal))).scalars().all()}
    assert "https://ex.com/keep" in urls  # 今回も見つかった → 残る
    assert "https://ex.com/gone" not in urls  # 消えた → 削除
    assert "https://ex.com/other-site" in urls  # 別サイト → 触らない


@pytest.mark.asyncio
async def test_prune_disappeared_empty_seen_is_noop(repository, async_session):
    """seen が空（収集0件 / adapter 破損の可能性）のときは安全に何もしない"""
    from sqlalchemy import select

    site = "高知サイト"
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://ex.com/safe",
            category="adoption",
            source_site=site,
        )
    )
    await async_session.commit()

    removed = await repository.prune_disappeared(site, set())

    assert removed == 0
    remaining = (await async_session.execute(select(Animal))).scalars().all()
    assert len(remaining) == 1  # 全消しされない


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
async def test_list_animals_excludes_deceased_by_default(repository, async_session):
    """list_animals() は既定で死亡(deceased)個体を公開対象から除外する。

    deceased の非公開はフロント制御だけでなくデータ境界で強制する。これにより
    公開API/フィード/直リンクから死亡個体を列挙・閲覧できる穴を塞ぐ（補足監査
    セキュリティ/誤情報リスク）。adopted/returned はアーカイブで見せるため除外しない。
    内部用途は include_non_public=True で全件取得できる。
    """
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

    # 既定: deceased を除外（sheltered + adopted の 2 件）
    result, total = await repository.list_animals()
    assert total == 2
    statuses = [a.status for a in result]
    assert AnimalStatus.SHELTERED in statuses
    assert AnimalStatus.ADOPTED in statuses
    assert AnimalStatus.DECEASED not in statuses

    # 内部用途: include_non_public=True なら deceased も含めて全件返す
    result_all, total_all = await repository.list_animals(include_non_public=True)
    assert total_all == 3
    assert AnimalStatus.DECEASED in [a.status for a in result_all]


@pytest.mark.asyncio
async def test_list_animals_orm_excludes_deceased_by_default(repository, async_session):
    """list_animals_orm()（公開ポータル一覧の経路）も既定で deceased を除外する。"""
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/orm_sheltered",
            category="adoption",
            status="sheltered",
        )
    )
    async_session.add(
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/orm_deceased",
            category="adoption",
            status="deceased",
        )
    )
    await async_session.commit()

    result, total = await repository.list_animals_orm()
    assert total == 1
    assert all(a.status != "deceased" for a in result)

    _result_all, total_all = await repository.list_animals_orm(include_non_public=True)
    assert total_all == 2


@pytest.mark.asyncio
async def test_get_animal_by_id_orm_hides_deceased_by_default(repository, async_session):
    """get_animal_by_id_orm() は既定で deceased を None 扱い（→ルート層で404）。

    内部の status 更新・画像パス更新・削除フローは include_non_public=True で取得する。
    """
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/orm_by_id_deceased",
        category="adoption",
        status="deceased",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    # 公開: deceased は取得不可（None）
    assert await repository.get_animal_by_id_orm(animal.id) is None
    # 内部: include_non_public=True で取得可能
    got = await repository.get_animal_by_id_orm(animal.id, include_non_public=True)
    assert got is not None
    assert got.status == "deceased"


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


# === animal-identity-fields Slice 0: 個体識別4フィールドの空配線 ===


@pytest.mark.asyncio
async def test_save_and_get_preserves_identity_fields(repository):
    """breed/name/description/management_number が保存→取得で保持される（往復）。"""
    data = AnimalData(
        species="犬",
        sex="男の子",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/identity1",
        category="adoption",
        breed="柴犬",
        name="ポチ",
        description="人懐っこい性格です。",
        management_number="R7-249",
    )

    saved = await repository.save_animal(data)

    assert saved.breed == "柴犬"
    assert saved.name == "ポチ"
    assert saved.description == "人懐っこい性格です。"
    assert saved.management_number == "R7-249"


@pytest.mark.asyncio
async def test_identity_fields_default_to_none(repository):
    """個体識別フィールドを省略すると None で保存・取得される（後方互換）。"""
    data = AnimalData(
        species="猫",
        sex="不明",
        shelter_date=date(2026, 1, 6),
        location="高知県",
        source_url="https://example.com/identity2",
        category="adoption",
    )

    saved = await repository.save_animal(data)

    assert saved.breed is None
    assert saved.name is None
    assert saved.description is None
    assert saved.management_number is None


@pytest.mark.asyncio
async def test_identity_fields_overwrite_on_resave(repository):
    """再収集で個体識別フィールドは無条件上書きされる（ソースから消えた値が残留しない）。"""
    base = {
        "species": "犬",
        "sex": "男の子",
        "shelter_date": date(2026, 1, 5),
        "location": "高知県",
        "source_url": "https://example.com/identity3",
        "category": "adoption",
    }
    await repository.save_animal(AnimalData(**base, breed="チワワ", name="チャチャ"))

    # 次回収集で breed/name がソースから消えた → None で上書きされる
    resaved = await repository.save_animal(AnimalData(**base))

    assert resaved.breed is None
    assert resaved.name is None


@pytest.mark.asyncio
async def test_breed_search_absorbs_kana_variants(repository, async_session):
    """品種(breed)検索はカタカナ↔ひらがなの揺れを吸収する（Slice 1）。"""
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/breed-search1",
            category="adoption",
            breed="チワワ",
        )
    )
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/breed-search2",
            category="adoption",
            breed="しばいぬ",
        )
    )
    await async_session.commit()

    # ひらがな検索 → カタカナ保存にヒット
    res, total = await repository.list_animals_orm(q="ちわわ")
    assert total == 1
    assert res[0].breed == "チワワ"

    # カタカナ検索 → ひらがな保存にヒット
    res2, total2 = await repository.list_animals_orm(q="シバイヌ")
    assert total2 == 1
    assert res2[0].breed == "しばいぬ"

    # 部分一致も効く
    res3, total3 = await repository.list_animals_orm(q="チワ")
    assert total3 == 1
    assert res3[0].breed == "チワワ"
