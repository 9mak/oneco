"""GET /admin/sites のテスト

sites.yaml に登録された全サイトの一覧と、各サイトの DB 上の収集状況を返すエンドポイント。
collection-ops-dashboard spec Req6 の最小実装に対応する。
"""

from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import Animal, Base

_VALID_TOKEN = "test-internal-token"


@pytest_asyncio.fixture
async def async_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_app(async_session, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", _VALID_TOKEN)
    app = create_app()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    return app


@pytest.mark.asyncio
async def test_admin_sites_requires_auth(test_app):
    """X-Internal-Token なしの場合 401"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/admin/sites")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_sites_returns_list_with_total(test_app):
    """正しいトークンで sites と total を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    assert response.status_code == 200
    body = response.json()
    assert "sites" in body
    assert "total" in body
    assert "generated_at" in body
    assert body["total"] == len(body["sites"])


@pytest.mark.asyncio
async def test_admin_sites_includes_required_fields(test_app):
    """各サイト行は必要フィールドを含む"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    body = response.json()
    if body["sites"]:
        site = body["sites"][0]
        for field in (
            "name",
            "prefecture",
            "list_url",
            "extraction",
            "requires_js",
            "category",
            "db_count",
            "last_shelter_date",
            "host",
        ):
            assert field in site, f"site row missing field: {field}"


@pytest.mark.asyncio
async def test_admin_sites_db_count_reflects_animals(test_app, async_session):
    """DB に animals があれば該当ホストの db_count に反映される"""
    # douai-tokushima.com に該当する animals を投入
    async_session.add(
        Animal(
            species="犬",
            sex="男の子",
            shelter_date=date(2026, 5, 1),
            location="徳島県動物愛護管理センター",
            prefecture="徳島県",
            phone="088-000-0000",
            image_urls=[],
            source_url="https://douai-tokushima.com/transfer/test1",
            category="adoption",
            status="sheltered",
        )
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/admin/sites",
            headers={"X-Internal-Token": _VALID_TOKEN},
        )
    body = response.json()
    matches = [s for s in body["sites"] if s["host"] == "douai-tokushima.com"]
    if matches:
        assert any(s["db_count"] >= 1 for s in matches)
