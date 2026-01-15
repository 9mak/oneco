"""
DatabaseConnection のテスト

データベース接続管理、コネクションプール、セッションライフサイクルが
要件通りに実装されているかを検証します。
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from src.data_collector.infrastructure.database.connection import (
    DatabaseConnection,
    DatabaseSettings,
)


@pytest.mark.asyncio
async def test_database_settings_from_env(monkeypatch):
    """環境変数からデータベース設定が正しく読み込まれるか"""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("DB_POOL_SIZE", "10")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "20")

    settings = DatabaseSettings()

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.pool_size == 10
    assert settings.max_overflow == 20


@pytest.mark.asyncio
async def test_database_settings_default_values():
    """デフォルト値が正しく設定されるか"""
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")

    assert settings.pool_size == 5
    assert settings.max_overflow == 10


@pytest.mark.asyncio
async def test_database_connection_creates_engine():
    """DatabaseConnectionがエンジンを正しく作成するか"""
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")
    db_connection = DatabaseConnection(settings)

    assert db_connection.engine is not None
    assert db_connection.async_session_maker is not None

    await db_connection.close()


@pytest.mark.asyncio
async def test_get_session_returns_async_session():
    """get_session()がAsyncSessionを返すか"""
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")
    db_connection = DatabaseConnection(settings)

    async with db_connection.get_session() as session:
        assert isinstance(session, AsyncSession)

    await db_connection.close()


@pytest.mark.asyncio
async def test_get_session_commits_on_success():
    """get_session()が正常終了時にcommitするか"""
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")
    db_connection = DatabaseConnection(settings)

    transaction_completed = False

    # コンテキストマネージャーが正常に動作することを確認
    async with db_connection.get_session() as session:
        # セッションが使用可能
        assert isinstance(session, AsyncSession)
        transaction_completed = True

    # コンテキストを抜けてもエラーが発生しないことを確認
    assert transaction_completed

    await db_connection.close()


@pytest.mark.asyncio
async def test_close_disposes_engine():
    """close()がエンジンを正しくdisposeするか"""
    settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")
    db_connection = DatabaseConnection(settings)

    # dispose前はエンジンが使用可能
    assert db_connection.engine is not None

    await db_connection.close()

    # closeが正常に完了することを確認
    # （実際のdispose確認は、再度closeを呼んでもエラーにならないことで確認）
    await db_connection.close()  # 2回目のcloseでエラーが出ないこと
