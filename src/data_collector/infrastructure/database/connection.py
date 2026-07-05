"""
データベース接続管理

このモジュールは PostgreSQL データベースへの接続管理を提供します。
コネクションプール、セッションライフサイクル、環境変数からの設定読み込みを担当します。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseSettings(BaseSettings):
    """
    データベース接続設定

    環境変数または .env ファイルから設定を読み込みます。
    """

    database_url: str = Field(..., description="データベース接続URL")
    pool_size: int = Field(default=5, alias="DB_POOL_SIZE", description="コネクションプールサイズ")
    max_overflow: int = Field(
        default=10, alias="DB_MAX_OVERFLOW", description="プール最大オーバーフロー数"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )


def _build_engine_kwargs(settings: "DatabaseSettings") -> dict:
    """`create_async_engine` に渡す kwargs を構築する。

    SQLite はプールパラメータ・connect_args (asyncpg 固有) を一切サポートしない
    ため、postgres 系 URL のときのみ付与する。
    """
    engine_kwargs: dict = {"echo": False, "future": True}

    if not settings.database_url.startswith("sqlite"):
        engine_kwargs["pool_size"] = settings.pool_size
        engine_kwargs["max_overflow"] = settings.max_overflow
        # Supabase の pgbouncer transaction-mode プーラー対応。
        # transaction pooling は論理セッション内の各クエリが別の物理接続に
        # routing されうるため、asyncpg 既定の prepared statement cache が
        # 前の接続で作った statement を参照し続け "prepared statement ...
        # does not exist" になる。statement_cache_size=0 で無効化して防ぐ。
        # (session-mode プーラーや直結 Postgres でもキャッシュを使わないだけで
        # 動作自体は変わらないため、常時付与して問題ない。)
        engine_kwargs["connect_args"] = {"statement_cache_size": 0}

    return engine_kwargs


class DatabaseConnection:
    """
    データベース接続マネージャー

    非同期コネクションプールとセッション管理を提供します。
    アプリケーション起動時に初期化し、終了時にクローズします。
    """

    def __init__(self, settings: DatabaseSettings):
        """
        DatabaseConnection を初期化

        Args:
            settings: データベース接続設定
        """
        self.settings = settings

        engine_kwargs = _build_engine_kwargs(settings)

        self.engine: AsyncEngine = create_async_engine(
            settings.database_url,
            **engine_kwargs,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        データベースセッションを取得

        コンテキストマネージャーとして使用し、自動的にセッションをクローズします。

        Yields:
            AsyncSession: データベースセッション

        Raises:
            DatabaseError: 接続エラー

        Example:
            async with db_connection.get_session() as session:
                result = await session.execute(select(Animal))
        """
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """
        接続プールをクローズ

        アプリケーション終了時に呼び出されます。
        """
        await self.engine.dispose()
