"""
FastAPI アプリケーション

REST APIを提供するFastAPIアプリケーションを初期化します。
CORS設定、ライフサイクルイベント、エラーハンドラーを含みます。
"""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.data_collector.infrastructure.database.connection import (
    DatabaseConnection,
    DatabaseSettings,
)
from src.data_collector.infrastructure.logging_config import get_logger, setup_logging

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
        async with db_connection.get_session():
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

    # CORS 設定
    # 公開 GET API のため認証クッキーは不要 → allow_credentials=False
    # CORS_ORIGINS 環境変数で許可ドメインを明示する。未設定なら local dev 想定の安全なデフォルト
    cors_env = os.getenv("CORS_ORIGINS", "").strip()
    if cors_env == "*":
        # 明示的に全開放を要求された場合のみ。allow_credentials は False を強制
        allowed_origins = ["*"]
    elif cors_env:
        allowed_origins = [o.strip() for o in cors_env.split(",") if o.strip()]
    else:
        # デフォルトは local dev 限定（本番は env で明示設定すること）
        allowed_origins = ["http://localhost:3000", "http://localhost:3002"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS", "PATCH"],
        allow_headers=["Content-Type", "X-Internal-Token"],
    )

    # ルーター登録
    from src.data_collector.infrastructure.api.routes import archive_router, router

    app.include_router(router)
    app.include_router(archive_router)

    # Syndication Service ルーター登録
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    from src.syndication_service.api.health import create_health_router
    from src.syndication_service.api.routes import create_syndication_router
    from src.syndication_service.middleware.rate_limiter import (
        create_limiter,
        rate_limit_error_handler,
    )
    from src.syndication_service.services.cache_manager import CacheManager
    from src.syndication_service.services.feed_generator import FeedGenerator
    from src.syndication_service.services.metrics_collector import MetricsCollector

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    feed_generator = FeedGenerator()
    cache_manager = CacheManager(redis_url=redis_url)
    metrics_collector = MetricsCollector()

    # Rate limiter 初期化（Redis 障害時は None → graceful degradation）
    limiter = create_limiter(redis_url=redis_url)
    if limiter:
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)
        app.add_middleware(SlowAPIMiddleware)

    syndication_router = create_syndication_router(
        feed_generator=feed_generator,
        cache_manager=cache_manager,
        metrics_collector=metrics_collector,
        limiter=limiter,
    )
    app.include_router(syndication_router, prefix="/feeds", tags=["syndication"])

    # Health Check ルーター登録（syndication-service）
    health_router = create_health_router(
        metrics_collector=metrics_collector, cache_manager=cache_manager
    )
    app.include_router(health_router, tags=["health"])

    return app
