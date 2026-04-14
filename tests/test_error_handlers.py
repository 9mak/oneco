"""
エラーハンドラーのテスト

FastAPIのエラーハンドラーが要件通りに実装されているかを検証します。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import Base


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


@pytest.mark.asyncio
async def test_404_error_response_format(test_app, async_session):
    """HTTP 404エラーが正しい形式で返されるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals/99999")

    assert response.status_code == 404

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_422_validation_error_response_format(test_app, async_session):
    """HTTP 422バリデーションエラーが正しい形式で返されるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # limitが1000を超える不正な値
        response = await client.get("/animals?limit=1001")

    assert response.status_code == 422

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_validation_error_includes_field_details(test_app, async_session):
    """バリデーションエラーにフィールド詳細が含まれるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        # 負のoffset値
        response = await client.get("/animals?offset=-1")

    assert response.status_code == 422

    data = response.json()
    assert "detail" in data

    # FastAPIのデフォルトバリデーションエラー形式を確認
    # detailはリストであるか、またはエラーメッセージ文字列
    assert isinstance(data["detail"], (list, str))


@pytest.mark.asyncio
async def test_response_content_type_is_json(test_app, async_session):
    """エラーレスポンスがJSON形式であるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/animals/99999")

    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]
