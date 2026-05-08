"""
GET /admin/stats エンドポイントのテスト

ダッシュボード用の集計データを返すエンドポイント。
既存の X-Internal-Token 認証を再利用する。
"""

from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.infrastructure.database.models import (
    Animal,
    Base,
    ImageHash,
)


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


@pytest_asyncio.fixture
async def populated_for_stats(async_session):
    """統計テスト用のデータを投入"""
    animals = [
        # 高知県 sheltered 犬 adoption
        Animal(
            species="犬",
            sex="男の子",
            shelter_date=date(2026, 5, 1),
            location="高知県動物愛護センター",
            prefecture="高知県",
            source_url="https://example.com/kochi/1",
            category="adoption",
            status="sheltered",
        ),
        # 高知県 sheltered 猫 adoption
        Animal(
            species="猫",
            sex="女の子",
            shelter_date=date(2026, 5, 2),
            location="高知県",
            prefecture="高知県",
            source_url="https://example.com/kochi/2",
            category="adoption",
            status="sheltered",
        ),
        # 徳島県 sheltered 犬 lost
        Animal(
            species="犬",
            sex="不明",
            shelter_date=date(2026, 5, 3),
            location="徳島県",
            prefecture="徳島県",
            source_url="https://example.com/toku/1",
            category="lost",
            status="sheltered",
        ),
        # 徳島県 adopted 猫 adoption
        Animal(
            species="猫",
            sex="男の子",
            shelter_date=date(2026, 4, 1),
            location="徳島県",
            prefecture="徳島県",
            source_url="https://example.com/toku/2",
            category="adoption",
            status="adopted",
        ),
        # prefecture None（古いデータ想定）
        Animal(
            species="犬",
            sex="不明",
            shelter_date=date(2026, 4, 15),
            location="不明",
            prefecture=None,
            source_url="https://example.com/unknown/1",
            category="adoption",
            status="sheltered",
        ),
    ]
    for a in animals:
        async_session.add(a)

    # ImageHash 2件
    async_session.add(
        ImageHash(
            hash="a" * 64,
            local_path="cache/aa/aaa.jpg",
            file_size=1024,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
    )
    async_session.add(
        ImageHash(
            hash="b" * 64,
            local_path="cache/bb/bbb.jpg",
            file_size=2048,
            created_at=datetime(2026, 5, 7, tzinfo=timezone.utc),
        )
    )

    await async_session.commit()
    return async_session


HEADERS = {"X-Internal-Token": "test-internal-token"}


@pytest.mark.asyncio
async def test_admin_stats_requires_auth(test_app):
    """/admin/stats は X-Internal-Token なしで 401 を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_stats_invalid_token(test_app):
    """/admin/stats は不正な X-Internal-Token で 401 を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers={"X-Internal-Token": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_stats_returns_total_counts(test_app, populated_for_stats):
    """/admin/stats が件数集計を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()

    assert data["total_animals"] == 5
    assert data["by_status"]["sheltered"] == 4
    assert data["by_status"]["adopted"] == 1
    # 未出現ステータスもキー自体は存在し0で埋める
    assert data["by_status"].get("returned", 0) == 0
    assert data["by_status"].get("deceased", 0) == 0


@pytest.mark.asyncio
async def test_admin_stats_returns_prefecture_breakdown(test_app, populated_for_stats):
    """/admin/stats が県別集計を件数降順で返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers=HEADERS)

    data = resp.json()
    by_pref = data["by_prefecture"]
    assert isinstance(by_pref, list)
    # 高知県 2 / 徳島県 2 / unknown 1 が含まれる
    pref_map = {row["prefecture"]: row["count"] for row in by_pref}
    assert pref_map.get("高知県") == 2
    assert pref_map.get("徳島県") == 2
    # None の県は "(未分類)" にまとめる
    assert pref_map.get("(未分類)") == 1
    # 件数降順ソート
    counts = [row["count"] for row in by_pref]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
async def test_admin_stats_returns_species_and_category(test_app, populated_for_stats):
    """/admin/stats が species/category 集計を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers=HEADERS)

    data = resp.json()
    assert data["by_species"]["犬"] == 3
    assert data["by_species"]["猫"] == 2
    assert data["by_category"]["adoption"] == 4
    assert data["by_category"]["lost"] == 1


@pytest.mark.asyncio
async def test_admin_stats_returns_image_hash_summary(test_app, populated_for_stats):
    """/admin/stats が image_hashes 統計を返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers=HEADERS)

    data = resp.json()
    img = data["image_hash_summary"]
    assert img["total"] == 2
    assert img["oldest"] is not None
    assert img["newest"] is not None
    assert img["oldest"] <= img["newest"]


@pytest.mark.asyncio
async def test_admin_stats_returns_generated_at(test_app, populated_for_stats):
    """/admin/stats が generated_at タイムスタンプを返す"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers=HEADERS)

    data = resp.json()
    assert "generated_at" in data
    # ISO 8601 形式としてパース可能
    datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_admin_stats_empty_db(test_app):
    """空DBでも正常に統計を返す（0件で）"""
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/admin/stats", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_animals"] == 0
    assert data["by_prefecture"] == []
    assert data["image_hash_summary"]["total"] == 0
    assert data["image_hash_summary"]["oldest"] is None
    assert data["image_hash_summary"]["newest"] is None
