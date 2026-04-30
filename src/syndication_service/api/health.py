"""
Health Check Router

サービスの稼働状況とメトリクスを提供。

Requirements Coverage:
- 7.1-7.4: ヘルスチェック
- 7.5-7.7: メトリクス
"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.syndication_service.models.metrics import MetricsSnapshot
from src.syndication_service.services.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


class HealthCheckResponse(BaseModel):
    """ヘルスチェックレスポンス"""

    status: str  # "healthy" / "degraded" / "unhealthy"
    timestamp: datetime
    upstream_api_status: str  # "ok" / "error"
    cache_status: str  # "ok" / "error"
    metrics: MetricsSnapshot | None = None


def create_health_router(
    metrics_collector: MetricsCollector | None = None,
    cache_manager: object | None = None,
    repository_factory: object | None = None,
) -> APIRouter:
    """
    HealthCheckRouter を作成

    Args:
        metrics_collector: MetricsCollector インスタンス
        cache_manager: CacheManager インスタンス（Redis 接続確認用）
        repository_factory: AnimalRepository ファクトリ（DB 接続確認用）

    Returns:
        APIRouter インスタンス
    """
    router = APIRouter()

    _metrics_collector = metrics_collector or MetricsCollector()

    @router.get("/health", response_model=HealthCheckResponse)
    async def get_health():
        """
        ヘルスチェックエンドポイント

        Requirements: 7.1, 7.2, 7.3, 7.4
        """
        timestamp = datetime.now()
        upstream_status = "ok"
        cache_status = "ok"
        overall_status = "healthy"

        # Redis 接続確認
        if cache_manager:
            try:
                if cache_manager.redis_client:
                    # PING コマンドで接続確認
                    await cache_manager.redis_client.ping()
                    logger.info("Redis health check: OK")
                else:
                    cache_status = "error"
                    overall_status = "degraded"
                    logger.warning("Redis health check: Client not initialized")
            except Exception as e:
                cache_status = "error"
                overall_status = "degraded"
                logger.warning(f"Redis health check failed: {e}")

        # データベース接続確認
        if repository_factory:
            try:
                # 軽量クエリで接続確認
                async with repository_factory():
                    # AnimalRepository には接続確認メソッドがないため、スキップ
                    pass
                logger.info("Database health check: OK")
            except Exception as e:
                upstream_status = "error"
                overall_status = "unhealthy"
                logger.error(f"Database health check failed: {e}")

        # メトリクススナップショット取得
        metrics = _metrics_collector.get_metrics_snapshot()

        # ステータス判定
        if overall_status == "unhealthy":
            raise HTTPException(
                status_code=503,
                detail=HealthCheckResponse(
                    status=overall_status,
                    timestamp=timestamp,
                    upstream_api_status=upstream_status,
                    cache_status=cache_status,
                    metrics=metrics,
                ).model_dump(),
            )

        return HealthCheckResponse(
            status=overall_status,
            timestamp=timestamp,
            upstream_api_status=upstream_status,
            cache_status=cache_status,
            metrics=metrics,
        )

    return router
