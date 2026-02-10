"""
CacheManager Service

Redis によるフィードキャッシングと ETag 管理。

Requirements Coverage:
- 4.1, 4.2: キャッシュ取得/保存
- 4.3: キャッシュキー生成
- 4.6, 4.7: ETag 生成と If-None-Match 処理
- 5.1, 5.2: Redis 障害時の graceful degradation
"""

import hashlib
import json
import logging
from typing import Optional, Tuple, Literal
import redis.asyncio as redis


logger = logging.getLogger(__name__)


class CacheManager:
    """Redis キャッシュマネージャー"""

    CACHE_TTL = 300  # 5分

    def __init__(self, redis_url: str):
        """
        CacheManager を初期化

        Args:
            redis_url: Redis 接続 URL（例: redis://localhost:6379/0）
        """
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Redis クライアントを初期化"""
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            logger.info(f"Redis client initialized: {self.redis_url}")
        except Exception as e:
            logger.warning(f"Redis 初期化に失敗しました（キャッシュなしで動作）: {e}")
            self.redis_client = None

    async def get_cached_feed(
        self,
        format: Literal["rss", "atom"],
        filter_params: dict,
        if_none_match: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], bool]:
        """
        キャッシュからフィードを取得

        Args:
            format: "rss" または "atom"
            filter_params: フィルタ条件（キャッシュキー生成用）
            if_none_match: If-None-Match ヘッダー値（ETag）

        Returns:
            (feed_xml, etag, is_304)
            - feed_xml: キャッシュされたフィード XML（None の場合はキャッシュミス）
            - etag: 生成された ETag
            - is_304: If-None-Match が一致した場合 True（304 返却）
        """
        if self.redis_client is None:
            # Redis が利用不可の場合、キャッシュミス
            return None, None, False

        try:
            cache_key = self._generate_cache_key(format, filter_params)
            etag = self._generate_etag(cache_key)

            # If-None-Match ヘッダーチェック
            if if_none_match and if_none_match == etag:
                # ETag 一致: 304 Not Modified
                logger.info(f"Cache ETag match (304): {cache_key}")
                return None, etag, True

            # Redis からキャッシュ取得
            cached_feed = await self.redis_client.get(cache_key)

            if cached_feed:
                logger.info(f"Cache hit: {cache_key}")
                return cached_feed, etag, False
            else:
                logger.info(f"Cache miss: {cache_key}")
                return None, None, False

        except Exception as e:
            # Redis エラー時は graceful degradation（キャッシュミスとして扱う）
            logger.warning(f"Redis エラーが発生しました（キャッシュミス扱い）: {e}")
            return None, None, False

    async def save_cached_feed(
        self,
        format: Literal["rss", "atom"],
        filter_params: dict,
        feed_xml: str
    ) -> str:
        """
        フィードを Redis にキャッシュ

        Args:
            format: "rss" または "atom"
            filter_params: フィルタ条件（キャッシュキー生成用）
            feed_xml: フィード XML 文字列

        Returns:
            etag: 生成された ETag
        """
        cache_key = self._generate_cache_key(format, filter_params)
        etag = self._generate_etag(cache_key)

        if self.redis_client is None:
            # Redis が利用不可の場合、ETag のみ返却（キャッシュはスキップ）
            logger.warning(f"Redis が利用不可のため、キャッシュをスキップ: {cache_key}")
            return etag

        try:
            # Redis に SETEX でキャッシュ保存（TTL: 300秒）
            await self.redis_client.setex(cache_key, self.CACHE_TTL, feed_xml)
            logger.info(f"Cache saved: {cache_key}, TTL={self.CACHE_TTL}s")
            return etag

        except Exception as e:
            # Redis エラー時は警告ログを記録し、処理を継続
            logger.warning(f"Redis へのキャッシュ保存に失敗しました: {e}")
            return etag

    def _generate_cache_key(self, format: str, filter_params: dict) -> str:
        """
        キャッシュキーを生成

        Args:
            format: "rss" または "atom"
            filter_params: フィルタ条件

        Returns:
            キャッシュキー（例: feed:rss:abc123）
        """
        # フィルタ条件をソートして一貫性を保つ
        # None 値は除外
        filtered_params = {k: v for k, v in filter_params.items() if v is not None}
        param_str = json.dumps(filtered_params, sort_keys=True, ensure_ascii=False)

        # MD5 ハッシュを生成
        hash_value = hashlib.md5(param_str.encode()).hexdigest()

        return f"feed:{format}:{hash_value}"

    def _generate_etag(self, cache_key: str) -> str:
        """
        ETag を生成（キャッシュキーの MD5 ハッシュ）

        Args:
            cache_key: キャッシュキー

        Returns:
            ETag（例: "abc123"）
        """
        hash_value = hashlib.md5(cache_key.encode()).hexdigest()
        return f'"{hash_value}"'
