"""
FastAPI アプリケーション

REST APIを提供するFastAPIアプリケーションを初期化します。
CORS設定、ライフサイクルイベント、エラーハンドラーを含みます。
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.data_collector.infrastructure.database.connection import (
    DatabaseConnection,
    DatabaseSettings,
)
from src.data_collector.infrastructure.logging_config import setup_logging, get_logger

# ロギングを設定
setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = get_logger(__name__)

# グローバルな DatabaseConnection インスタンス
db_connection: DatabaseConnection = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    アプリケーションライフサイクル管理

    起動時: データベース接続を初期化
    終了時: データベース接続をクローズ
    """
    global db_connection

    # 起動時: データベース接続を初期化
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    settings = DatabaseSettings(database_url=database_url)
    db_connection = DatabaseConnection(settings)

    # データベース接続テスト
    try:
        async with db_connection.get_session() as session:
            # 接続テストが成功すればOK
            logger.info("Database connection test succeeded")
    except Exception as e:
        # 接続失敗時はログに記録
        logger.error(f"Database connection test failed: {e}", exc_info=True)
        raise

    yield

    # 終了時: データベース接続をクローズ
    await db_connection.close()


def create_app() -> FastAPI:
    """
    FastAPIアプリケーションを作成

    Returns:
        FastAPI: 設定済みのFastAPIインスタンス
    """
    app = FastAPI(
        title="Animal Repository API",
        description="保護動物データを提供するREST API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS設定
    allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ルーター登録
    from src.data_collector.infrastructure.api.routes import router
    app.include_router(router)

    return app
