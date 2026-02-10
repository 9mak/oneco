"""
Shared fixtures for syndication service tests.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.syndication_service.api.routes import create_syndication_router, get_animal_repository, get_archive_repository
from src.syndication_service.services.feed_generator import FeedGenerator
from src.syndication_service.services.cache_manager import CacheManager
from src.syndication_service.services.metrics_collector import MetricsCollector
from src.syndication_service.middleware.rate_limiter import create_limiter, rate_limit_error_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware


@pytest.fixture
def mock_animal_repo():
    """Mock AnimalRepository"""
    mock = AsyncMock()
    # list_animals / list_archived は (List[AnimalData], int) タプルを返す
    mock.list_animals = AsyncMock(return_value=([], 0))
    mock.list_archived = AsyncMock(return_value=([], 0))
    return mock


@pytest.fixture
def mock_cache_manager():
    """Mock CacheManager"""
    mock = MagicMock(spec=CacheManager)
    # Configure mock to return cache miss by default
    mock.get_cached_feed = AsyncMock(return_value=(None, None, False))
    mock.save_cached_feed = AsyncMock(return_value='"test_etag"')
    return mock


@pytest.fixture
def app(mock_animal_repo, mock_cache_manager):
    """テスト用 FastAPI アプリ"""
    app = FastAPI()

    # Rate limiter をメモリストレージで初期化（テスト用）
    limiter = create_limiter(redis_url="memory://")
    if limiter:
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)
        app.add_middleware(SlowAPIMiddleware)

    # Mock dependencies
    feed_generator = FeedGenerator()
    metrics_collector = MetricsCollector()

    router = create_syndication_router(
        feed_generator=feed_generator,
        cache_manager=mock_cache_manager,
        metrics_collector=metrics_collector,
        limiter=limiter
    )

    app.include_router(router, prefix="/feeds")

    # Override dependencies
    async def override_get_animal_repository():
        yield mock_animal_repo

    async def override_get_archive_repository():
        yield mock_animal_repo  # Same mock for archive endpoints

    app.dependency_overrides[get_animal_repository] = override_get_animal_repository
    app.dependency_overrides[get_archive_repository] = override_get_archive_repository

    return app


@pytest.fixture
def client(app):
    """テスト用クライアント"""
    return TestClient(app)
