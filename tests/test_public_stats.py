"""GET /public/stats のテスト

公開メトリクス API は認証不要、CORS 開放で動作する必要がある。
Phase 2 クラファン訴求とトップ OG 画像のソースとして使用される。
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import Animal, Base


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
async def test_app(async_session):
    app = create_app()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    return app


def _make_animal(*, prefecture: str | None, status: str = "sheltered", days_ago: int = 0) -> Animal:
    return Animal(
        species="犬",
        sex="男の子",
        age_months=24,
        color="茶色",
        size="中型",
        shelter_date=(datetime.now().date() - timedelta(days=days_ago)),
        location=f"{prefecture or '未設定'}センター",
        prefecture=prefecture,
        phone="088-000-0000",
        image_urls=[],
        source_url=f"https://example.com/{prefecture}-{days_ago}",
        category="adoption",
        status=status,
    )


@pytest.mark.asyncio
async def test_public_stats_returns_zero_counts_when_empty(test_app):
    """データ無し時は全てゼロ、avg_waiting_days は None"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/public/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_animals"] == 0
    assert body["municipality_count"] == 0
    assert body["avg_waiting_days"] is None
    assert isinstance(body["site_count"], int)


@pytest.mark.asyncio
async def test_public_stats_counts_total_animals(test_app, async_session):
    """累計件数は status を問わず全件カウントする（公開メトリクス）"""
    async_session.add_all(
        [
            _make_animal(prefecture="高知県"),
            _make_animal(prefecture="徳島県", status="adopted"),
            _make_animal(prefecture=None),
        ]
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/public/stats")
    body = response.json()
    assert body["total_animals"] == 3


@pytest.mark.asyncio
async def test_public_stats_municipality_count_is_distinct_prefecture(test_app, async_session):
    """対応自治体数は distinct prefecture（NULL 除外）"""
    async_session.add_all(
        [
            _make_animal(prefecture="高知県"),
            _make_animal(prefecture="高知県"),  # 重複
            _make_animal(prefecture="徳島県"),
            _make_animal(prefecture=None),  # 除外
        ]
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/public/stats")
    assert response.json()["municipality_count"] == 2


@pytest.mark.asyncio
async def test_public_stats_avg_waiting_days_only_for_sheltered(test_app, async_session):
    """平均待機日数は status='sheltered' のみを対象に集計する"""
    async_session.add_all(
        [
            _make_animal(prefecture="高知県", status="sheltered", days_ago=10),
            _make_animal(prefecture="高知県", status="sheltered", days_ago=20),
            _make_animal(prefecture="高知県", status="adopted", days_ago=1000),  # 除外
        ]
    )
    await async_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/public/stats")
    avg = response.json()["avg_waiting_days"]
    assert avg is not None
    assert 10 <= avg <= 30  # SQLite は ms 単位の誤差があるためレンジ判定


@pytest.mark.asyncio
async def test_public_stats_does_not_require_auth(test_app):
    """認証ヘッダ無しで 200 を返す（CORS 開放 + 公開エンドポイント）"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/public/stats")
    assert response.status_code == 200
    assert "total_animals" in response.json()
