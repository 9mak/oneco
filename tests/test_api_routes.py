"""
API ルートのテスト

GET /animals と GET /animals/{id} エンドポイントが
要件通りに実装されているかを検証します。
"""

import pytest
import pytest_asyncio
from datetime import date
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Animal, Base
from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session


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
async def test_app(async_session):
    """テスト用のFastAPIアプリケーションを作成"""
    app = create_app()

    # 依存性をオーバーライド
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    return app


@pytest_asyncio.fixture
async def populated_session(async_session):
    """テストデータが投入されたセッションを返す"""
    # テストデータを投入
    animals = [
        Animal(
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
        ),
        Animal(
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
        ),
        Animal(
            species="犬",
            sex="女の子",
            age_months=36,
            color="黒",
            size="大型",
            shelter_date=date(2026, 1, 7),
            location="高知市",
            phone="088-111-2222",
            image_urls=[],
            source_url="https://example.com/animal/3",
        ),
    ]

    for animal in animals:
        async_session.add(animal)
    await async_session.commit()

    # IDを取得するためにリフレッシュ
    for animal in animals:
        await async_session.refresh(animal)

    return async_session


@pytest.mark.asyncio
async def test_list_animals_returns_all_animals(test_app, populated_session):
    """GET /animals が全ての動物を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals")

    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "meta" in data
    assert len(data["items"]) == 3
    assert data["meta"]["total_count"] == 3


@pytest.mark.asyncio
async def test_list_animals_filters_by_species(test_app, populated_session):
    """GET /animals?species=犬 が犬のみを返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?species=犬")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 2
    assert all(item["species"] == "犬" for item in data["items"])
    assert data["meta"]["total_count"] == 2


@pytest.mark.asyncio
async def test_list_animals_filters_by_sex(test_app, populated_session):
    """GET /animals?sex=女の子 が女の子のみを返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?sex=女の子")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 2
    assert all(item["sex"] == "女の子" for item in data["items"])


@pytest.mark.asyncio
async def test_list_animals_filters_by_location(test_app, populated_session):
    """GET /animals?location=高知市 が部分一致で検索するか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?location=高知市")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 1
    assert data["items"][0]["location"] == "高知市"


@pytest.mark.asyncio
async def test_list_animals_pagination(test_app, populated_session):
    """GET /animals?limit=2&offset=1 がページネーションを適用するか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?limit=2&offset=1")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 2
    assert data["meta"]["total_count"] == 3
    assert data["meta"]["limit"] == 2
    assert data["meta"]["offset"] == 1
    assert data["meta"]["current_page"] == 2


@pytest.mark.asyncio
async def test_list_animals_pagination_meta(test_app, populated_session):
    """ページネーションメタデータが正しく計算されるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?limit=2&offset=0")

    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["current_page"] == 1
    assert data["meta"]["total_pages"] == 2
    assert data["meta"]["has_next"] is True


@pytest.mark.asyncio
async def test_list_animals_limit_validation(test_app, populated_session):
    """limitが1000を超える場合にHTTP 422を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?limit=1001")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_animals_offset_validation(test_app, populated_session):
    """offsetが負の値の場合にHTTP 422を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?offset=-1")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_animal_by_id_returns_animal(test_app, populated_session):
    """GET /animals/{id} が指定されたIDの動物を返すか"""
    # 最初の動物のIDを取得
    from sqlalchemy import select

    stmt = select(Animal).limit(1)
    result = await populated_session.execute(stmt)
    animal = result.scalar_one()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(f"/animals/{animal.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == animal.id
    assert data["species"] == animal.species
    assert data["source_url"] == animal.source_url


@pytest.mark.asyncio
async def test_get_animal_by_id_not_found(test_app, populated_session):
    """GET /animals/{id} が存在しないIDの場合にHTTP 404を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals/99999")

    assert response.status_code == 404
    data = response.json()

    assert "detail" in data


@pytest.mark.asyncio
async def test_list_animals_empty_result(test_app, async_session):
    """データが0件の場合に空の配列を返すか"""
    # データを投入しないセッションを使用
    app = create_app()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/animals")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 0
    assert data["meta"]["total_count"] == 0


@pytest.mark.asyncio
async def test_list_animals_returns_json_content_type(test_app, populated_session):
    """レスポンスがJSON形式であるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_get_animal_returns_json_content_type(test_app, populated_session):
    """レスポンスがJSON形式であるか"""
    from sqlalchemy import select

    stmt = select(Animal).limit(1)
    result = await populated_session.execute(stmt)
    animal = result.scalar_one()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(f"/animals/{animal.id}")

    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
