"""
SyndicationRouter 統合テスト

TDD アプローチ:
- GET /feeds/rss エンドポイント
- GET /feeds/atom エンドポイント
- Cache-Control / ETag ヘッダー
- 空フィード処理
- アーカイブフィード
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from src.data_collector.domain.models import AnimalData, AnimalStatus
from src.syndication_service.api.routes import create_syndication_router
from src.syndication_service.services.cache_manager import CacheManager
from src.syndication_service.services.feed_generator import FeedGenerator
from src.syndication_service.services.metrics_collector import MetricsCollector


@pytest.fixture
def mock_animal_repo():
    """Mock AnimalRepository"""
    return AsyncMock()


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
    from src.syndication_service.api.routes import get_animal_repository

    app = FastAPI()

    # Mock dependencies
    feed_generator = FeedGenerator()
    metrics_collector = MetricsCollector()

    router = create_syndication_router(
        feed_generator=feed_generator,
        cache_manager=mock_cache_manager,
        metrics_collector=metrics_collector,
    )

    app.include_router(router, prefix="/feeds")

    # Override dependency
    async def override_get_animal_repository():
        yield mock_animal_repo

    app.dependency_overrides[get_animal_repository] = override_get_animal_repository

    return app


@pytest.fixture
def client(app):
    """テスト用クライアント"""
    return TestClient(app)


@pytest.fixture
def sample_animals():
    """テスト用動物データ"""
    return [
        AnimalData(
            species="犬",
            shelter_date=date(2026, 1, 1),
            location="高知県",
            source_url=HttpUrl("https://kochi-apc.com/jouto/detail/123"),
            category="adoption",
            sex="男の子",
            status=AnimalStatus.SHELTERED,
        ),
    ]


class TestFeedQueryParams:
    """Task 6.1: FeedQueryParams スキーマテスト"""

    def test_feed_query_params_default_limit(self, client):
        """limit パラメータのデフォルト値が 50 であること"""
        from src.syndication_service.models.schemas import FeedQueryParams

        params = FeedQueryParams()
        assert params.limit == 50

    def test_feed_query_params_limit_validation(self):
        """limit パラメータが 1~100 の範囲でバリデーションされること"""
        from pydantic import ValidationError

        from src.syndication_service.models.schemas import FeedQueryParams

        # 正常値
        params = FeedQueryParams(limit=50)
        assert params.limit == 50

        # 最小値
        params = FeedQueryParams(limit=1)
        assert params.limit == 1

        # 最大値
        params = FeedQueryParams(limit=100)
        assert params.limit == 100

        # 範囲外（0以下）
        with pytest.raises(ValidationError):
            FeedQueryParams(limit=0)

        # 範囲外（101以上）
        with pytest.raises(ValidationError):
            FeedQueryParams(limit=101)

    def test_feed_query_params_to_dict(self):
        """to_dict() メソッドが None 値を除外すること"""
        from src.syndication_service.models.schemas import FeedQueryParams

        params = FeedQueryParams(species="犬", location="高知", limit=50)
        result = params.to_dict()

        assert result == {"species": "犬", "location": "高知", "limit": 50}
        assert "category" not in result  # None 値は除外


class TestRSSEndpoint:
    """Task 6.2: GET /feeds/rss エンドポイントテスト"""

    def test_get_rss_feed_returns_xml(self, client, mock_animal_repo, sample_animals):
        """GET /feeds/rss が RSS XML を返すこと"""
        # Mock repository response
        mock_animal_repo.list_animals.return_value = (sample_animals, len(sample_animals))

        response = client.get("/feeds/rss")

        assert response.status_code == 200
        assert "application/rss+xml" in response.headers["content-type"]
        assert "<?xml" in response.text
        assert "<rss" in response.text

    def test_get_rss_feed_with_filter_params(self, client, mock_animal_repo, sample_animals):
        """フィルタパラメータが正しく適用されること"""
        # Mock repository response
        mock_animal_repo.list_animals.return_value = (sample_animals, len(sample_animals))

        response = client.get("/feeds/rss?species=犬&location=高知")

        assert response.status_code == 200
        # フィルタ条件がタイトルに反映されている
        assert "犬" in response.text
        assert "高知" in response.text

    def test_get_rss_feed_invalid_limit(self, client):
        """limit が 100 を超える場合、400 エラーを返すこと"""
        response = client.get("/feeds/rss?limit=200")

        assert response.status_code == 422  # Pydantic validation error


class TestAtomEndpoint:
    """Task 6.3: GET /feeds/atom エンドポイントテスト"""

    def test_get_atom_feed_returns_xml(self, client, mock_animal_repo, sample_animals):
        """GET /feeds/atom が Atom XML を返すこと"""
        # Mock repository response
        mock_animal_repo.list_animals.return_value = (sample_animals, len(sample_animals))

        response = client.get("/feeds/atom")

        assert response.status_code == 200
        assert "application/atom+xml" in response.headers["content-type"]
        assert "<?xml" in response.text
        assert "<feed" in response.text


class TestCacheControlAndETag:
    """Task 6.4: Cache-Control と ETag ヘッダーテスト"""

    def test_response_has_cache_control_header(self, client, mock_animal_repo, sample_animals):
        """レスポンスに Cache-Control ヘッダーが含まれること"""
        # Mock repository response
        mock_animal_repo.list_animals.return_value = (sample_animals, len(sample_animals))

        response = client.get("/feeds/rss")

        assert response.status_code == 200
        assert "Cache-Control" in response.headers
        assert "max-age=300" in response.headers["Cache-Control"]

    def test_response_has_etag_header(self, client, mock_animal_repo, sample_animals):
        """レスポンスに ETag ヘッダーが含まれること"""
        # Mock repository response
        mock_animal_repo.list_animals.return_value = (sample_animals, len(sample_animals))

        response = client.get("/feeds/rss")

        assert response.status_code == 200
        assert "ETag" in response.headers
        assert response.headers["ETag"].startswith('"')


class TestEmptyFeed:
    """Task 6.5: 空フィード処理テスト"""

    def test_empty_feed_returns_200(self, client, mock_animal_repo):
        """動物データが0件の場合、200 OK を返すこと"""
        # Mock repository response
        mock_animal_repo.list_animals.return_value = ([], 0)  # 0件

        response = client.get("/feeds/rss?species=犬&location=存在しない地域")

        assert response.status_code == 200
        assert "<item>" not in response.text  # アイテムは0件


class TestArchiveFeedQueryParams:
    """Task 7.1: ArchiveFeedQueryParams スキーマテスト"""

    def test_archive_query_params_date_validation(self):
        """日付パラメータが正しくバリデーションされること"""
        from src.syndication_service.models.schemas import ArchiveFeedQueryParams

        params = ArchiveFeedQueryParams(
            archived_from=date(2026, 1, 1), archived_to=date(2026, 1, 31)
        )

        assert params.archived_from == date(2026, 1, 1)
        assert params.archived_to == date(2026, 1, 31)

    def test_archive_query_params_to_dict(self):
        """to_dict() が日付を文字列に変換すること"""
        from src.syndication_service.models.schemas import ArchiveFeedQueryParams

        params = ArchiveFeedQueryParams(species="犬", archived_from=date(2026, 1, 1))
        result = params.to_dict()

        assert result["species"] == "犬"
        assert result["archived_from"] == "2026-01-01"
