"""
API ルートのテスト

GET /animals と GET /animals/{id} エンドポイントが
要件通りに実装されているかを検証します。
"""

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import Animal, Base


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
            category="adoption",
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
            category="adoption",
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
            category="adoption",
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


# === Task 4.1: ステータス更新 API テスト ===


@pytest_asyncio.fixture
async def animal_for_status_update(async_session):
    """ステータス更新用の動物データを作成"""
    animal = Animal(
        species="犬",
        sex="男の子",
        age_months=24,
        shelter_date=date(2026, 1, 5),
        location="高知県動物愛護センター",
        source_url="https://example.com/animal/status_test",
        category="adoption",
        status="sheltered",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)
    return animal


@pytest.mark.asyncio
async def test_update_status_success(test_app, animal_for_status_update):
    """PATCH /animals/{id}/status が正常にステータスを更新するか"""
    animal_id = animal_for_status_update.id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(
            f"/animals/{animal_id}/status",
            json={"status": "adopted"},
            headers={"X-Internal-Token": "test-internal-token"},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert data["animal"]["status"] == "adopted"
    assert data["animal"]["id"] == animal_id


@pytest.mark.asyncio
async def test_update_status_with_outcome_date(test_app, animal_for_status_update):
    """PATCH /animals/{id}/status が outcome_date を受け付けるか"""
    animal_id = animal_for_status_update.id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(
            f"/animals/{animal_id}/status",
            json={"status": "adopted", "outcome_date": "2026-01-20"},
            headers={"X-Internal-Token": "test-internal-token"},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["animal"]["outcome_date"] == "2026-01-20"


@pytest.mark.asyncio
async def test_update_status_invalid_transition(test_app, async_session):
    """PATCH /animals/{id}/status が不正な遷移で 422 を返すか"""
    # deceased 状態の動物を作成
    animal = Animal(
        species="犬",
        shelter_date=date(2026, 1, 5),
        location="高知県",
        source_url="https://example.com/animal/deceased_test",
        category="adoption",
        status="deceased",
    )
    async_session.add(animal)
    await async_session.commit()
    await async_session.refresh(animal)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(
            f"/animals/{animal.id}/status",
            json={"status": "sheltered"},
            headers={"X-Internal-Token": "test-internal-token"},
        )

    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_update_status_not_found(test_app, async_session):
    """PATCH /animals/{id}/status が存在しない動物で 404 を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(
            "/animals/99999/status",
            json={"status": "adopted"},
            headers={"X-Internal-Token": "test-internal-token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_status_invalid_status_value(test_app, animal_for_status_update):
    """PATCH /animals/{id}/status が無効なステータス値で 422 を返すか"""
    animal_id = animal_for_status_update.id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(
            f"/animals/{animal_id}/status",
            json={"status": "invalid_status"},
            headers={"X-Internal-Token": "test-internal-token"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_status_requires_auth_token(test_app, animal_for_status_update):
    """PATCH /animals/{id}/status は X-Internal-Token なしで 401 を返す"""
    animal_id = animal_for_status_update.id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(f"/animals/{animal_id}/status", json={"status": "adopted"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_status_rejects_invalid_token(test_app, animal_for_status_update):
    """PATCH /animals/{id}/status は不正な X-Internal-Token で 401 を返す"""
    animal_id = animal_for_status_update.id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.patch(
            f"/animals/{animal_id}/status",
            json={"status": "adopted"},
            headers={"X-Internal-Token": "wrong-token"},
        )

    assert response.status_code == 401


# === Task 4.2: 既存 API のステータスフィルタリング対応テスト ===


@pytest_asyncio.fixture
async def animals_with_different_statuses(async_session):
    """異なるステータスの動物データを作成"""
    animals = [
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/animal/filter1",
            category="adoption",
            status="sheltered",
        ),
        Animal(
            species="猫",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/animal/filter2",
            category="adoption",
            status="adopted",
        ),
        Animal(
            species="犬",
            shelter_date=date(2026, 1, 7),
            location="高知県",
            source_url="https://example.com/animal/filter3",
            category="adoption",
            status="sheltered",
        ),
    ]
    for animal in animals:
        async_session.add(animal)
    await async_session.commit()
    return animals


@pytest.mark.asyncio
async def test_list_animals_filters_by_status_api(test_app, animals_with_different_statuses):
    """GET /animals?status=sheltered がステータスでフィルタリングするか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?status=sheltered")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 2
    assert data["meta"]["total_count"] == 2
    assert all(item["status"] == "sheltered" for item in data["items"])


@pytest.mark.asyncio
async def test_list_animals_without_status_returns_all_api(
    test_app, animals_with_different_statuses
):
    """GET /animals でステータス指定なしの場合全ステータスを返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals")

    assert response.status_code == 200
    data = response.json()

    assert data["meta"]["total_count"] == 3


@pytest.mark.asyncio
async def test_list_animals_invalid_status_returns_400(test_app, animals_with_different_statuses):
    """GET /animals?status=invalid が 400 を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals?status=invalid")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_animal_includes_status_fields(
    test_app, animals_with_different_statuses, async_session
):
    """GET /animals/{id} がステータスフィールドを含むか"""
    from sqlalchemy import select

    stmt = select(Animal).limit(1)
    result = await async_session.execute(stmt)
    animal = result.scalar_one()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(f"/animals/{animal.id}")

    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] == "sheltered"


# === Task 12.1: アーカイブデータ参照 API テスト ===


@pytest_asyncio.fixture
async def archived_animals(async_session):
    """アーカイブされた動物データを作成"""
    from datetime import datetime

    from src.data_collector.infrastructure.database.models import AnimalArchive

    archives = [
        AnimalArchive(
            original_id=100,
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            size="中型",
            shelter_date=date(2025, 6, 1),
            location="高知県動物愛護センター",
            phone="088-123-4567",
            image_urls=["https://example.com/archive1.jpg"],
            source_url="https://example.com/animal/archive1",
            category="adoption",
            status="adopted",
            archived_at=datetime(2026, 1, 10, 10, 0, 0),
        ),
        AnimalArchive(
            original_id=101,
            species="猫",
            sex="女の子",
            age_months=12,
            color="白",
            size="小型",
            shelter_date=date(2025, 5, 15),
            location="高知市保健所",
            phone="088-999-8888",
            image_urls=["https://example.com/archive2.jpg"],
            source_url="https://example.com/animal/archive2",
            category="adoption",
            status="returned",
            archived_at=datetime(2026, 1, 15, 14, 30, 0),
        ),
        AnimalArchive(
            original_id=102,
            species="犬",
            sex="女の子",
            age_months=36,
            color="黒",
            size="大型",
            shelter_date=date(2025, 4, 20),
            location="高知県動物愛護センター",
            phone="088-111-2222",
            image_urls=[],
            source_url="https://example.com/animal/archive3",
            category="adoption",
            status="deceased",
            archived_at=datetime(2026, 1, 20, 9, 0, 0),
        ),
    ]

    for archive in archives:
        async_session.add(archive)
    await async_session.commit()

    for archive in archives:
        await async_session.refresh(archive)

    return archives


@pytest.mark.asyncio
async def test_list_archived_animals_returns_all(test_app, archived_animals):
    """GET /archive/animals が全てのアーカイブ動物を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/archive/animals")

    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "meta" in data
    assert len(data["items"]) == 3
    assert data["meta"]["total_count"] == 3


@pytest.mark.asyncio
async def test_list_archived_animals_filters_by_species(test_app, archived_animals):
    """GET /archive/animals?species=犬 が犬のみを返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/archive/animals?species=犬")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 2
    assert all(item["species"] == "犬" for item in data["items"])


@pytest.mark.asyncio
async def test_list_archived_animals_pagination(test_app, archived_animals):
    """GET /archive/animals?limit=2&offset=1 がページネーションを適用するか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/archive/animals?limit=2&offset=1")

    assert response.status_code == 200
    data = response.json()

    assert len(data["items"]) == 2
    assert data["meta"]["total_count"] == 3
    assert data["meta"]["limit"] == 2
    assert data["meta"]["offset"] == 1


@pytest.mark.asyncio
async def test_list_archived_animals_includes_archive_fields(test_app, archived_animals):
    """GET /archive/animals がアーカイブ固有フィールドを含むか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/archive/animals")

    assert response.status_code == 200
    data = response.json()

    # アーカイブ固有フィールドの確認
    for item in data["items"]:
        assert "original_id" in item
        assert "archived_at" in item
        assert item["original_id"] >= 100


@pytest.mark.asyncio
async def test_get_archived_animal_by_id(test_app, archived_animals, async_session):
    """GET /archive/animals/{id} が指定されたIDのアーカイブを返すか"""
    archive_id = archived_animals[0].id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(f"/archive/animals/{archive_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == archive_id
    assert data["original_id"] == 100
    assert data["species"] == "犬"
    assert "archived_at" in data


@pytest.mark.asyncio
async def test_get_archived_animal_not_found(test_app, archived_animals):
    """GET /archive/animals/{id} が存在しないIDの場合に 404 を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/archive/animals/99999")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_archive_api_is_read_only(test_app, archived_animals):
    """アーカイブ API が読み取り専用であることを確認（POST/PATCH/DELETE が無い）"""
    archive_id = archived_animals[0].id

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # POST は 405 Method Not Allowed
        post_response = await client.post("/archive/animals", json={})
        # PATCH は 405 Method Not Allowed
        patch_response = await client.patch(f"/archive/animals/{archive_id}", json={})
        # DELETE は 405 Method Not Allowed
        delete_response = await client.delete(f"/archive/animals/{archive_id}")

    assert post_response.status_code == 405
    assert patch_response.status_code == 405
    assert delete_response.status_code == 405
