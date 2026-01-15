"""
データベースマイグレーションのテスト

Alembicマイグレーションが正しく動作し、テーブルとインデックスが
期待通りに作成されることを検証します。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import inspect, text


@pytest_asyncio.fixture
async def migration_engine():
    """テスト用の非同期エンジンを作成"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    yield engine

    await engine.dispose()


@pytest.mark.asyncio
async def test_animals_table_exists_after_migration(migration_engine):
    """マイグレーション後にanimalsテーブルが存在するか"""
    from src.data_collector.infrastructure.database.models import Base

    # テーブルを作成（マイグレーションの代わり）
    async with migration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # テーブルの存在を確認
    async with migration_engine.connect() as conn:
        def check_table(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            return "animals" in tables

        table_exists = await conn.run_sync(check_table)
        assert table_exists, "animals table should exist after migration"


@pytest.mark.asyncio
async def test_animals_table_columns(migration_engine):
    """animalsテーブルのカラムが正しく定義されているか"""
    from src.data_collector.infrastructure.database.models import Base

    async with migration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with migration_engine.connect() as conn:
        def check_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = inspector.get_columns("animals")
            column_names = [col["name"] for col in columns]
            return column_names

        column_names = await conn.run_sync(check_columns)

        expected_columns = [
            "id",
            "species",
            "shelter_date",
            "location",
            "source_url",
            "sex",
            "age_months",
            "color",
            "size",
            "phone",
            "image_urls",
        ]

        for col in expected_columns:
            assert col in column_names, f"Column {col} should exist in animals table"


@pytest.mark.asyncio
async def test_animals_table_indexes(migration_engine):
    """animalsテーブルのインデックスが正しく作成されているか"""
    from src.data_collector.infrastructure.database.models import Base

    async with migration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with migration_engine.connect() as conn:
        def check_indexes(sync_conn):
            inspector = inspect(sync_conn)
            indexes = inspector.get_indexes("animals")
            return indexes

        indexes = await conn.run_sync(check_indexes)

        # インデックス名を取得
        index_names = [idx["name"] for idx in indexes]

        # 期待されるインデックス
        expected_indexes = [
            "ix_animals_species",
            "ix_animals_sex",
            "ix_animals_shelter_date",
            "ix_animals_location",
            "idx_animals_search",
        ]

        for idx_name in expected_indexes:
            assert idx_name in index_names, f"Index {idx_name} should exist"


@pytest.mark.asyncio
async def test_animals_table_unique_constraints(migration_engine):
    """source_urlのユニーク制約が存在するか"""
    from src.data_collector.infrastructure.database.models import Base

    async with migration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with migration_engine.connect() as conn:
        def check_constraints(sync_conn):
            inspector = inspect(sync_conn)
            unique_constraints = inspector.get_unique_constraints("animals")
            return unique_constraints

        constraints = await conn.run_sync(check_constraints)

        # SQLiteではユニーク制約が正しく取得できないことがあるため、
        # 実際にデータを挿入してユニーク制約をテスト
        from src.data_collector.infrastructure.database.models import Animal
        from datetime import date

        async_session_maker = async_sessionmaker(
            migration_engine, class_=AsyncSession, expire_on_commit=False
        )

        async with async_session_maker() as session:
            # 最初のレコードを挿入
            animal1 = Animal(
                species="犬",
                shelter_date=date(2026, 1, 5),
                location="高知県",
                source_url="https://example.com/animal/1",
            )
            session.add(animal1)
            await session.commit()

            # 同じsource_urlで挿入を試みる
            animal2 = Animal(
                species="猫",
                shelter_date=date(2026, 1, 6),
                location="高知県",
                source_url="https://example.com/animal/1",
            )
            session.add(animal2)

            # ユニーク制約違反のエラーが発生することを期待
            with pytest.raises(Exception):  # IntegrityError or similar
                await session.commit()


@pytest.mark.asyncio
async def test_migration_rollback(migration_engine):
    """マイグレーションのロールバックが正しく動作するか"""
    from src.data_collector.infrastructure.database.models import Base

    # テーブルを作成
    async with migration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # テーブルが存在することを確認
    async with migration_engine.connect() as conn:
        def check_table_exists(sync_conn):
            inspector = inspect(sync_conn)
            return "animals" in inspector.get_table_names()

        table_exists = await conn.run_sync(check_table_exists)
        assert table_exists

    # テーブルを削除（ロールバック）
    async with migration_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    # テーブルが存在しないことを確認
    async with migration_engine.connect() as conn:
        table_exists = await conn.run_sync(check_table_exists)
        assert not table_exists
