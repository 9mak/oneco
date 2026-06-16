"""prefecture バックフィル (歴史的 NULL orphan 補完) のテスト

2026-05-22 の site_config.prefecture フォールバック導入より前に収集され
prefecture=NULL のまま残った 36 件 (source_url が 404 で再収集されない orphan) を
source_url ホストから一度だけ補完する。冪等性・対象限定・非該当不変を検証する。
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    yield eng
    await eng.dispose()


@pytest.mark.asyncio
async def test_backfill_fills_null_prefecture_by_host(engine):
    """NULL prefecture をホスト→都道府県で補完し、既存値・非該当は触らない。冪等。"""
    from src.data_collector.infrastructure.database.models import Animal, Base
    from src.data_collector.infrastructure.database.prefecture_backfill import (
        backfill_null_prefectures,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [
                # NULL + 該当ホスト → 埋まる
                Animal(
                    species="猫",
                    shelter_date=date(2026, 5, 13),
                    location="x",
                    source_url="https://www.aniwel-pref.okinawa/animal/1",
                    category="sheltered",
                    prefecture=None,
                ),
                Animal(
                    species="犬",
                    shelter_date=date(2026, 4, 1),
                    location="y",
                    source_url="https://animal-net.pref.nagasaki.jp/animal/no-1/",
                    category="sheltered",
                    prefecture=None,
                ),
                # 空文字 + 該当ホスト → 埋まる
                Animal(
                    species="猫",
                    shelter_date=date(2026, 5, 12),
                    location="z",
                    source_url="https://www.city.naha.okinawa.jp/a/3",
                    category="sheltered",
                    prefecture="",
                ),
                # 既に prefecture あり → 上書きされない (冪等)
                Animal(
                    species="猫",
                    shelter_date=date(2026, 6, 1),
                    location="w",
                    source_url="https://www.kumamoto-doubutuaigo.jp/a/2",
                    category="sheltered",
                    prefecture="熊本県",
                ),
                # 非該当ホストの NULL → 触らない
                Animal(
                    species="犬",
                    shelter_date=date(2026, 6, 1),
                    location="v",
                    source_url="https://example.com/x",
                    category="sheltered",
                    prefecture=None,
                ),
            ]
        )
        await session.commit()

    async with engine.begin() as conn:
        affected = await conn.run_sync(backfill_null_prefectures)
    assert affected == 3

    async with maker() as session:
        rows = (await session.execute(select(Animal))).scalars().all()
        by_url = {a.source_url: a.prefecture for a in rows}
    assert by_url["https://www.aniwel-pref.okinawa/animal/1"] == "沖縄県"
    assert by_url["https://animal-net.pref.nagasaki.jp/animal/no-1/"] == "長崎県"
    assert by_url["https://www.city.naha.okinawa.jp/a/3"] == "沖縄県"
    assert by_url["https://www.kumamoto-doubutuaigo.jp/a/2"] == "熊本県"  # 不変
    assert by_url["https://example.com/x"] is None  # 非該当は不変

    # 冪等性: 2 回目は 0 件
    async with engine.begin() as conn:
        again = await conn.run_sync(backfill_null_prefectures)
    assert again == 0


def test_mapping_is_one_to_one_per_host():
    """同一ホストが複数の都道府県に対応しない (1:1) ことを保証する。"""
    from src.data_collector.infrastructure.database.prefecture_backfill import (
        PREFECTURE_BY_HOST,
    )

    seen: dict[str, str] = {}
    for host, prefecture in PREFECTURE_BY_HOST:
        if host in seen:
            assert seen[host] == prefecture, f"host {host} が複数県に対応"
        seen[host] = prefecture
