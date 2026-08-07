"""
ヘルスチェックエンドポイントのテスト

GET /health エンドポイントが要件通りに実装されているかを検証します。
"""

from datetime import date, datetime, timezone

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


@pytest.mark.asyncio
async def test_health_check_returns_200(test_app):
    """ヘルスチェックエンドポイントがHTTP 200を返すか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check_response_format(test_app):
    """ヘルスチェックのレスポンス形式が正しいか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    data = response.json()

    assert "status" in data
    assert "timestamp" in data
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_response_is_json(test_app):
    """ヘルスチェックのレスポンスがJSON形式であるか"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    assert "application/json" in response.headers["content-type"]


# === 収集鮮度 (last_collected_at) ===
#
# 「収集が丸ごと落ちた」を外形監視から検知できるようにするためのフィールド。
# 2026-08-06 の GitHub Actions 障害では Data Collector の job が runner を確保
# できず steps が1つも実行されないまま cancelled になり、job 内の通知ステップも
# 走らないため完全に無音で1日分の収集が飛んだ。原因ベース (ワークフローの失敗を
# 見る) ではなく症状ベース (公開データが古くなっていないか見る) で検知する。


@pytest.mark.asyncio
async def test_health_check_includes_last_collected_at_key(test_app):
    """データが1件も無くても last_collected_at キー自体は必ず返す

    監視側がキーの有無で分岐せずに済むようにする。値は None。
    """
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    data = response.json()

    assert "last_collected_at" in data
    assert data["last_collected_at"] is None


@pytest.mark.asyncio
async def test_health_check_returns_max_last_collected_at(test_app, async_session):
    """複数個体があるとき last_collected_at の最大値を返す"""
    async_session.add_all(
        [
            Animal(
                species="犬",
                shelter_date=date(2026, 8, 1),
                location="テストセンター",
                source_url="https://example.com/animal/old",
                category="adoption",
                last_collected_at=datetime(2026, 8, 5, 16, 57, 20, tzinfo=timezone.utc),
            ),
            Animal(
                species="猫",
                shelter_date=date(2026, 8, 2),
                location="テストセンター",
                source_url="https://example.com/animal/new",
                category="adoption",
                last_collected_at=datetime(2026, 8, 7, 2, 8, 10, tzinfo=timezone.utc),
            ),
        ]
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    data = response.json()

    assert data["status"] == "healthy"
    assert data["last_collected_at"] is not None
    assert data["last_collected_at"].startswith("2026-08-07T02:08:10")


@pytest.mark.asyncio
async def test_health_check_ignores_animals_without_last_collected_at(test_app, async_session):
    """last_collected_at が NULL の個体しか無ければ None を返す

    収集が一度も成功していない状態と、古い収集が残っている状態を混同しない。
    """
    async_session.add(
        Animal(
            species="犬",
            shelter_date=date(2026, 8, 1),
            location="テストセンター",
            source_url="https://example.com/animal/never-collected",
            category="adoption",
            last_collected_at=None,
        )
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")

    assert response.json()["last_collected_at"] is None
