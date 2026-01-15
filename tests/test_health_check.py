"""
ヘルスチェックエンドポイントのテスト

GET /health エンドポイントが要件通りに実装されているかを検証します。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.data_collector.infrastructure.database.models import Base
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


@pytest.mark.asyncio
async def test_health_check_returns_200(test_app):
    """ヘルスチェックエンドポイントがHTTP 200を返すか"""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check_response_format(test_app):
    """ヘルスチェックのレスポンス形式が正しいか"""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    data = response.json()

    assert "status" in data
    assert "timestamp" in data
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_response_is_json(test_app):
    """ヘルスチェックのレスポンスがJSON形式であるか"""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert "application/json" in response.headers["content-type"]
