"""
Syndication Service API Routes

RSS/Atom フィードエンドポイントを提供。

Requirements Coverage:
- 1.1, 1.2: RSS/Atom エンドポイント
- 2.1-2.8: フィルタリング条件
- 4.5-4.7: キャッシング + ETag
- 6.1-6.7: アーカイブフィード
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import Response as FastAPIResponse

from src.data_collector.infrastructure.database.archive_repository import ArchiveRepository
from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.syndication_service.middleware.rate_limiter import DEFAULT_RATE_LIMIT
from src.syndication_service.models.schemas import ArchiveFeedQueryParams, FeedQueryParams
from src.syndication_service.services.cache_manager import CacheManager
from src.syndication_service.services.feed_generator import FeedGenerationError, FeedGenerator
from src.syndication_service.services.input_validator import InputValidator
from src.syndication_service.services.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)


async def get_animal_repository() -> AnimalRepository:
    """AnimalRepository の依存性注入（共有 db_connection を使用）"""
    import src.data_collector.infrastructure.api.app as app_module

    async with app_module.db_connection.get_session() as session:
        yield AnimalRepository(session)


async def get_archive_repository() -> ArchiveRepository:
    """ArchiveRepository の依存性注入（共有 db_connection を使用）"""
    import src.data_collector.infrastructure.api.app as app_module

    async with app_module.db_connection.get_session() as session:
        yield ArchiveRepository(session)


def create_syndication_router(
    feed_generator: FeedGenerator | None = None,
    cache_manager: CacheManager | None = None,
    metrics_collector: MetricsCollector | None = None,
    limiter: object | None = None,
) -> APIRouter:
    """
    SyndicationRouter を作成

    Args:
        feed_generator: FeedGenerator インスタンス（テスト用）
        cache_manager: CacheManager インスタンス（テスト用）
        metrics_collector: MetricsCollector インスタンス（テスト用）
        limiter: slowapi.Limiter インスタンス（オプション、レート制限用）

    Returns:
        APIRouter インスタンス
    """
    router = APIRouter()

    # デフォルトインスタンス
    _feed_generator = feed_generator or FeedGenerator()
    _cache_manager = cache_manager or CacheManager(redis_url="redis://localhost:6379/0")
    _metrics_collector = metrics_collector or MetricsCollector()
    _limiter = limiter  # Optional rate limiter

    def apply_rate_limit(func):
        """Apply rate limit decorator if limiter is available."""
        if _limiter is not None:
            return _limiter.limit(DEFAULT_RATE_LIMIT)(func)
        return func

    @router.get("/rss", response_class=FastAPIResponse)
    @apply_rate_limit
    async def get_rss_feed(
        request: Request,
        response: Response,
        species: str | None = Query(None, description="種別フィルタ"),
        category: str | None = Query(None, description="カテゴリフィルタ"),
        location: str | None = Query(None, description="地域フィルタ"),
        status: str | None = Query(None, description="ステータスフィルタ"),
        sex: str | None = Query(None, description="性別フィルタ"),
        limit: int = Query(50, ge=1, le=100, description="アイテム数"),
        if_none_match: str | None = Header(None, alias="If-None-Match"),
        repository: AnimalRepository = Depends(get_animal_repository),
    ):
        """
        RSS 2.0 フィードを取得

        Requirements: 1.1, 1.6, 2.1-2.8, 3.1-3.3, 4.5-4.7
        """
        # クエリパラメータを構築
        params = FeedQueryParams(
            species=species,
            category=category,
            location=location,
            status=status,
            sex=sex,
            limit=limit,
        )

        # バリデーション
        InputValidator.validate_query_params(params.to_dict())

        # キャッシュチェック
        filter_dict = params.to_dict()
        feed_xml, etag, is_304 = await _cache_manager.get_cached_feed(
            "rss", filter_dict, if_none_match
        )

        if is_304:
            # 304 Not Modified
            _metrics_collector.record_cache_hit()
            return Response(
                content="",
                status_code=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        if feed_xml:
            # キャッシュヒット
            _metrics_collector.record_cache_hit()
            return Response(
                content=feed_xml,
                media_type="application/rss+xml; charset=utf-8",
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        # キャッシュミス: データ取得
        _metrics_collector.record_cache_miss()

        # AnimalRepository からデータ取得
        animals, _total = await repository.list_animals(
            species=params.species,
            category=params.category,
            location=params.location,
            status=params.status,
            sex=params.sex,
            limit=params.limit,
        )

        # RSS フィード生成
        try:
            feed_xml = _feed_generator.generate_rss(animals, filter_dict)
        except FeedGenerationError as e:
            logger.error(f"RSS フィード生成エラー: {e}")
            raise HTTPException(status_code=500, detail="フィード生成に失敗しました")

        # キャッシュ保存
        etag = await _cache_manager.save_cached_feed("rss", filter_dict, feed_xml)

        # メトリクス記録
        _metrics_collector.record_feed_generation(datetime.now())

        return Response(
            content=feed_xml,
            media_type="application/rss+xml; charset=utf-8",
            headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
        )

    @router.get("/atom", response_class=FastAPIResponse)
    @apply_rate_limit
    async def get_atom_feed(
        request: Request,
        response: Response,
        species: str | None = Query(None, description="種別フィルタ"),
        category: str | None = Query(None, description="カテゴリフィルタ"),
        location: str | None = Query(None, description="地域フィルタ"),
        status: str | None = Query(None, description="ステータスフィルタ"),
        sex: str | None = Query(None, description="性別フィルタ"),
        limit: int = Query(50, ge=1, le=100, description="アイテム数"),
        if_none_match: str | None = Header(None, alias="If-None-Match"),
        repository: AnimalRepository = Depends(get_animal_repository),
    ):
        """
        Atom 1.0 フィードを取得

        Requirements: 1.2, 1.6, 2.1-2.8, 3.1-3.3, 4.5-4.7
        """
        # クエリパラメータを構築
        params = FeedQueryParams(
            species=species,
            category=category,
            location=location,
            status=status,
            sex=sex,
            limit=limit,
        )

        # バリデーション
        InputValidator.validate_query_params(params.to_dict())

        # キャッシュチェック
        filter_dict = params.to_dict()
        feed_xml, etag, is_304 = await _cache_manager.get_cached_feed(
            "atom", filter_dict, if_none_match
        )

        if is_304:
            # 304 Not Modified
            _metrics_collector.record_cache_hit()
            return Response(
                content="",
                status_code=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        if feed_xml:
            # キャッシュヒット
            _metrics_collector.record_cache_hit()
            return Response(
                content=feed_xml,
                media_type="application/atom+xml; charset=utf-8",
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        # キャッシュミス: データ取得
        _metrics_collector.record_cache_miss()

        # AnimalRepository からデータ取得
        animals, _total = await repository.list_animals(
            species=params.species,
            category=params.category,
            location=params.location,
            status=params.status,
            sex=params.sex,
            limit=params.limit,
        )

        # Atom フィード生成
        try:
            feed_xml = _feed_generator.generate_atom(animals, filter_dict)
        except FeedGenerationError as e:
            logger.error(f"Atom フィード生成エラー: {e}")
            raise HTTPException(status_code=500, detail="フィード生成に失敗しました")

        # キャッシュ保存
        etag = await _cache_manager.save_cached_feed("atom", filter_dict, feed_xml)

        # メトリクス記録
        _metrics_collector.record_feed_generation(datetime.now())

        return Response(
            content=feed_xml,
            media_type="application/atom+xml; charset=utf-8",
            headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
        )

    @router.get("/archive/rss", response_class=FastAPIResponse)
    @apply_rate_limit
    async def get_archive_rss_feed(
        request: Request,
        response: Response,
        species: str | None = Query(None, description="種別フィルタ"),
        location: str | None = Query(None, description="地域フィルタ"),
        archived_from: str | None = Query(None, description="アーカイブ開始日 (YYYY-MM-DD)"),
        archived_to: str | None = Query(None, description="アーカイブ終了日 (YYYY-MM-DD)"),
        limit: int = Query(50, ge=1, le=100, description="アイテム数"),
        if_none_match: str | None = Header(None, alias="If-None-Match"),
        repository: ArchiveRepository = Depends(get_archive_repository),
    ):
        """
        アーカイブ RSS 2.0 フィードを取得

        Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7
        """
        from datetime import date as Date

        # 日付文字列をパース
        archived_from_date = Date.fromisoformat(archived_from) if archived_from else None
        archived_to_date = Date.fromisoformat(archived_to) if archived_to else None

        # クエリパラメータを構築
        params = ArchiveFeedQueryParams(
            species=species,
            location=location,
            archived_from=archived_from_date,
            archived_to=archived_to_date,
            limit=limit,
        )

        # バリデーション
        InputValidator.validate_query_params(params.to_dict())

        # キャッシュチェック
        filter_dict = params.to_dict()
        feed_xml, etag, is_304 = await _cache_manager.get_cached_feed(
            "archive_rss", filter_dict, if_none_match
        )

        if is_304:
            # 304 Not Modified
            _metrics_collector.record_cache_hit()
            return Response(
                content="",
                status_code=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        if feed_xml:
            # キャッシュヒット
            _metrics_collector.record_cache_hit()
            return Response(
                content=feed_xml,
                media_type="application/rss+xml; charset=utf-8",
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        # キャッシュミス: データ取得
        _metrics_collector.record_cache_miss()

        # ArchiveRepository からデータ取得
        archived_animals, _total = await repository.list_archived(
            species=params.species,
            archived_from=params.archived_from,
            archived_to=params.archived_to,
            limit=params.limit,
        )

        # RSS フィード生成（feed_type="archive"）
        try:
            feed_xml = _feed_generator.generate_rss(
                archived_animals, filter_dict, feed_type="archive"
            )
        except FeedGenerationError as e:
            logger.error(f"アーカイブ RSS フィード生成エラー: {e}")
            raise HTTPException(status_code=500, detail="フィード生成に失敗しました")

        # キャッシュ保存
        etag = await _cache_manager.save_cached_feed("archive_rss", filter_dict, feed_xml)

        # メトリクス記録
        _metrics_collector.record_feed_generation(datetime.now())

        return Response(
            content=feed_xml,
            media_type="application/rss+xml; charset=utf-8",
            headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
        )

    @router.get("/archive/atom", response_class=FastAPIResponse)
    @apply_rate_limit
    async def get_archive_atom_feed(
        request: Request,
        response: Response,
        species: str | None = Query(None, description="種別フィルタ"),
        location: str | None = Query(None, description="地域フィルタ"),
        archived_from: str | None = Query(None, description="アーカイブ開始日 (YYYY-MM-DD)"),
        archived_to: str | None = Query(None, description="アーカイブ終了日 (YYYY-MM-DD)"),
        limit: int = Query(50, ge=1, le=100, description="アイテム数"),
        if_none_match: str | None = Header(None, alias="If-None-Match"),
        repository: ArchiveRepository = Depends(get_archive_repository),
    ):
        """
        アーカイブ Atom 1.0 フィードを取得

        Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
        """
        from datetime import date as Date

        # 日付文字列をパース
        archived_from_date = Date.fromisoformat(archived_from) if archived_from else None
        archived_to_date = Date.fromisoformat(archived_to) if archived_to else None

        # クエリパラメータを構築
        params = ArchiveFeedQueryParams(
            species=species,
            location=location,
            archived_from=archived_from_date,
            archived_to=archived_to_date,
            limit=limit,
        )

        # バリデーション
        InputValidator.validate_query_params(params.to_dict())

        # キャッシュチェック
        filter_dict = params.to_dict()
        feed_xml, etag, is_304 = await _cache_manager.get_cached_feed(
            "archive_atom", filter_dict, if_none_match
        )

        if is_304:
            # 304 Not Modified
            _metrics_collector.record_cache_hit()
            return Response(
                content="",
                status_code=304,
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        if feed_xml:
            # キャッシュヒット
            _metrics_collector.record_cache_hit()
            return Response(
                content=feed_xml,
                media_type="application/atom+xml; charset=utf-8",
                headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
            )

        # キャッシュミス: データ取得
        _metrics_collector.record_cache_miss()

        # ArchiveRepository からデータ取得
        archived_animals, _total = await repository.list_archived(
            species=params.species,
            archived_from=params.archived_from,
            archived_to=params.archived_to,
            limit=params.limit,
        )

        # Atom フィード生成（feed_type="archive"）
        try:
            feed_xml = _feed_generator.generate_atom(
                archived_animals, filter_dict, feed_type="archive"
            )
        except FeedGenerationError as e:
            logger.error(f"アーカイブ Atom フィード生成エラー: {e}")
            raise HTTPException(status_code=500, detail="フィード生成に失敗しました")

        # キャッシュ保存
        etag = await _cache_manager.save_cached_feed("archive_atom", filter_dict, feed_xml)

        # メトリクス記録
        _metrics_collector.record_feed_generation(datetime.now())

        return Response(
            content=feed_xml,
            media_type="application/atom+xml; charset=utf-8",
            headers={"ETag": etag, "Cache-Control": "public, max-age=300"},
        )

    return router
