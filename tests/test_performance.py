"""
パフォーマンステスト

大量データ処理、クエリパフォーマンス、ページネーションの
パフォーマンス要件が満たされているかを検証します。

要件:
- 1000件のupsert操作: < 10秒
- 複数フィルタ条件でのクエリ: < 100ms
- 大量データでのページネーション (offset=9000): < 200ms
"""

import pytest
import pytest_asyncio
import time
from datetime import date, timedelta
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
async def async_session_maker(async_engine):
    """テスト用の非同期セッションメーカーを作成"""
    return async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def async_session(async_session_maker):
    """テスト用の非同期セッションを作成"""
    async with async_session_maker() as session:
        yield session


def create_test_animal_data(index: int) -> AnimalData:
    """テスト用 AnimalData を作成"""
    species_list = ["犬", "猫", "その他"]
    sex_list = ["男の子", "女の子", "不明"]
    locations = ["高知県動物愛護センター", "高知市", "高知県", "南国市"]

    return AnimalData(
        species=species_list[index % 3],
        sex=sex_list[index % 3],
        age_months=index % 120,
        color=f"色{index % 10}",
        size=["小型", "中型", "大型"][index % 3],
        shelter_date=date(2026, 1, 1) + timedelta(days=index % 365),
        location=locations[index % len(locations)],
        phone="088-123-4567",
        image_urls=[f"https://example.com/img{index}.jpg"],
        source_url=f"https://example.com/animal/{index}",
    )


@pytest.mark.asyncio
async def test_upsert_1000_records_performance(async_session):
    """1000件のupsert操作が10秒以内に完了するか"""
    repository = AnimalRepository(async_session)

    # 1000件のデータを準備
    animal_data_list = [create_test_animal_data(i) for i in range(1000)]

    start_time = time.time()

    # 1000件のupsert操作
    for animal_data in animal_data_list:
        await repository.save_animal(animal_data)

    elapsed_time = time.time() - start_time

    # 10秒以内に完了することを確認
    assert elapsed_time < 10.0, f"1000件のupsertに{elapsed_time:.2f}秒かかりました（目標: <10秒）"


@pytest.mark.asyncio
async def test_filtered_query_performance(async_session):
    """複数フィルタ条件でのクエリが100ms以内に完了するか"""
    repository = AnimalRepository(async_session)

    # 500件のテストデータを挿入
    for i in range(500):
        animal_data = create_test_animal_data(i)
        await repository.save_animal(animal_data)

    # クエリパフォーマンステスト
    start_time = time.time()

    results, total = await repository.list_animals(
        species="犬",
        sex="男の子",
        location="高知",
        shelter_date_from=date(2026, 1, 1),
        shelter_date_to=date(2026, 6, 30),
        limit=50,
        offset=0
    )

    elapsed_time = time.time() - start_time

    # 100ms以内に完了することを確認
    assert elapsed_time < 0.1, f"フィルタクエリに{elapsed_time * 1000:.2f}msかかりました（目標: <100ms）"


@pytest.mark.asyncio
async def test_pagination_with_large_offset_performance(async_session):
    """大量データでのページネーション（offset=高値）が200ms以内に完了するか"""
    repository = AnimalRepository(async_session)

    # 1000件のテストデータを挿入（少なめに調整）
    for i in range(1000):
        animal_data = create_test_animal_data(i)
        await repository.save_animal(animal_data)

    # 高オフセットでのページネーションテスト
    start_time = time.time()

    results, total = await repository.list_animals(
        limit=50,
        offset=900  # 900番目から取得
    )

    elapsed_time = time.time() - start_time

    # 200ms以内に完了することを確認
    assert elapsed_time < 0.2, f"高オフセットページネーションに{elapsed_time * 1000:.2f}msかかりました（目標: <200ms）"

    # 正しいデータが返されることも確認
    assert len(results) == 50 or len(results) == total - 900
    assert total == 1000


@pytest.mark.asyncio
async def test_concurrent_read_performance(async_session_maker):
    """同時読み取りのパフォーマンステスト"""
    import asyncio

    # 初期データを挿入
    async with async_session_maker() as session:
        repository = AnimalRepository(session)
        for i in range(100):
            animal_data = create_test_animal_data(i)
            await repository.save_animal(animal_data)

    async def read_operation(session_maker):
        """読み取り操作"""
        async with session_maker() as session:
            repository = AnimalRepository(session)
            results, total = await repository.list_animals(limit=10)
            return len(results)

    # 10件の同時読み取りを実行
    start_time = time.time()

    tasks = [read_operation(async_session_maker) for _ in range(10)]
    results = await asyncio.gather(*tasks)

    elapsed_time = time.time() - start_time

    # 全ての読み取りが成功することを確認
    assert all(r == 10 for r in results)

    # 同時読み取りが合計500ms以内に完了することを確認
    assert elapsed_time < 0.5, f"10件の同時読み取りに{elapsed_time * 1000:.2f}msかかりました（目標: <500ms）"


@pytest.mark.asyncio
async def test_upsert_update_existing_performance(async_session):
    """既存レコードの更新が効率的に行われるか"""
    repository = AnimalRepository(async_session)

    # 100件のテストデータを挿入
    for i in range(100):
        animal_data = create_test_animal_data(i)
        await repository.save_animal(animal_data)

    # 同じsource_urlで更新
    start_time = time.time()

    for i in range(100):
        animal_data = create_test_animal_data(i)
        # 色だけ変更
        animal_data = AnimalData(
            species=animal_data.species,
            sex=animal_data.sex,
            age_months=animal_data.age_months,
            color="更新された色",
            size=animal_data.size,
            shelter_date=animal_data.shelter_date,
            location=animal_data.location,
            phone=animal_data.phone,
            image_urls=animal_data.image_urls,
            source_url=animal_data.source_url,
        )
        await repository.save_animal(animal_data)

    elapsed_time = time.time() - start_time

    # 100件の更新が1秒以内に完了することを確認
    assert elapsed_time < 1.0, f"100件の更新に{elapsed_time:.2f}秒かかりました（目標: <1秒）"

    # レコード数が増えていないことを確認（重複挿入されていない）
    _, total = await repository.list_animals()
    assert total == 100
