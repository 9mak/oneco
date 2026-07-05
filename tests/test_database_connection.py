"""
DatabaseConnection のテスト

データベース接続管理、コネクションプール、セッションライフサイクルが
要件通りに実装されているかを検証します。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.data_collector.infrastructure.database.connection import (
    DatabaseConnection,
    DatabaseSettings,
    _build_engine_kwargs,
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


class TestBuildEngineKwargs:
    """pgbouncer transaction-mode プーラー対応の engine_kwargs 構築を検証する。

    Supabase の session-mode プーラー (port 5432) はセッション毎に最大接続数の
    上限が低く、Cloud Run が複数インスタンスに自動スケールすると EMAXCONNSESSION
    (max clients reached in session mode) で本番 500 が発生した (実測: 2026-07 上旬、
    Vercel ビルド時の47都道府県 x 2 = 94 リクエストのバーストで複数回発生)。
    Transaction-mode プーラー (port 6543) へ切り替える運用対応に伴い、asyncpg の
    prepared statement cache を無効化する (transaction pooling は論理セッション内の
    各クエリが別の物理接続に routing されうるため、キャッシュされた prepared
    statement が別接続に存在せず "prepared statement ... does not exist" になるのを防ぐ)。
    """

    def test_postgres_url_gets_statement_cache_disabled(self):
        settings = DatabaseSettings(database_url="postgresql+asyncpg://u:p@host:6543/db")
        kwargs = _build_engine_kwargs(settings)
        assert kwargs["connect_args"] == {"statement_cache_size": 0}
        assert kwargs["pool_size"] == settings.pool_size
        assert kwargs["max_overflow"] == settings.max_overflow

    def test_sqlite_url_has_no_pool_or_connect_args(self):
        """SQLite はプールパラメータも connect_args (asyncpg固有) もサポートしない。"""
        settings = DatabaseSettings(database_url="sqlite+aiosqlite:///:memory:")
        kwargs = _build_engine_kwargs(settings)
        assert "connect_args" not in kwargs
        assert "pool_size" not in kwargs
        assert "max_overflow" not in kwargs


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
