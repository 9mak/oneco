"""
CacheManager ユニットテスト

TDD アプローチ:
- キャッシュキー生成の一意性
- ETag 生成の一貫性
- If-None-Match 一致時の 304 判定
- Redis 障害時の graceful degradation
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from src.syndication_service.services.cache_manager import CacheManager


@pytest.fixture
def cache_manager():
    """テスト用 CacheManager インスタンス"""
    return CacheManager(redis_url="redis://localhost:6379/0")


@pytest.fixture
def filter_params_1():
    """フィルタ条件1"""
    return {"species": "犬", "location": "高知"}


@pytest.fixture
def filter_params_2():
    """フィルタ条件2（異なる条件）"""
    return {"species": "猫", "location": "高知市"}


class TestCacheKeyGeneration:
    """Task 3.1: キャッシュキー生成テスト"""

    def test_generate_cache_key_uniqueness(self, cache_manager, filter_params_1, filter_params_2):
        """異なるフィルタ条件で異なるキャッシュキーが生成されること"""
        key1 = cache_manager._generate_cache_key("rss", filter_params_1)
        key2 = cache_manager._generate_cache_key("rss", filter_params_2)

        assert key1 != key2
        assert key1.startswith("feed:rss:")
        assert key2.startswith("feed:rss:")

    def test_generate_cache_key_consistency(self, cache_manager, filter_params_1):
        """同じフィルタ条件で同じキャッシュキーが生成されること"""
        key1 = cache_manager._generate_cache_key("rss", filter_params_1)
        key2 = cache_manager._generate_cache_key("rss", filter_params_1)

        assert key1 == key2

    def test_generate_cache_key_format_differs_by_format(self, cache_manager, filter_params_1):
        """RSS と Atom で異なるキャッシュキーが生成されること"""
        rss_key = cache_manager._generate_cache_key("rss", filter_params_1)
        atom_key = cache_manager._generate_cache_key("atom", filter_params_1)

        assert rss_key != atom_key
        assert rss_key.startswith("feed:rss:")
        assert atom_key.startswith("feed:atom:")


class TestETagGeneration:
    """Task 3.1: ETag 生成テスト"""

    def test_generate_etag_consistency(self, cache_manager):
        """同じキャッシュキーで同じ ETag が生成されること"""
        cache_key = "feed:rss:abc123"
        etag1 = cache_manager._generate_etag(cache_key)
        etag2 = cache_manager._generate_etag(cache_key)

        assert etag1 == etag2
        assert etag1.startswith('"')  # ETag は " で囲まれる
        assert etag1.endswith('"')

    def test_generate_etag_format(self, cache_manager):
        """ETag が正しい形式（MD5 ハッシュ）であること"""
        cache_key = "feed:rss:test123"
        etag = cache_manager._generate_etag(cache_key)

        # ETag は "ハッシュ値" の形式
        assert len(etag) == 34  # " + 32文字のMD5ハッシュ + "
        assert etag.startswith('"')
        assert etag.endswith('"')


@pytest.mark.asyncio
class TestCacheRetrival:
    """Task 3.2: キャッシュ取得テスト"""

    async def test_get_cached_feed_cache_miss(self, cache_manager, filter_params_1):
        """キャッシュミス時に (None, None, False) を返すこと"""
        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            mock_redis.get.return_value = None  # キャッシュミス

            feed_xml, etag, is_304 = await cache_manager.get_cached_feed("rss", filter_params_1)

            assert feed_xml is None
            assert etag is None
            assert is_304 is False

    async def test_get_cached_feed_cache_hit(self, cache_manager, filter_params_1):
        """キャッシュヒット時にフィード XML と ETag を返すこと"""
        cached_xml = '<?xml version="1.0"?><rss>...</rss>'

        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            mock_redis.get.return_value = cached_xml

            feed_xml, etag, is_304 = await cache_manager.get_cached_feed("rss", filter_params_1)

            assert feed_xml == cached_xml
            assert etag is not None
            assert etag.startswith('"')
            assert is_304 is False

    async def test_get_cached_feed_if_none_match_matches(self, cache_manager, filter_params_1):
        """If-None-Match ヘッダーが一致した場合、is_304=True を返すこと"""
        cached_xml = '<?xml version="1.0"?><rss>...</rss>'

        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            mock_redis.get.return_value = cached_xml

            # 最初にキャッシュを取得して ETag を取得
            _, etag, _ = await cache_manager.get_cached_feed("rss", filter_params_1)

            # 同じ ETag で再度リクエスト
            feed_xml, etag2, is_304 = await cache_manager.get_cached_feed(
                "rss", filter_params_1, if_none_match=etag
            )

            assert feed_xml is None  # 304 の場合、ボディは返さない
            assert etag2 == etag
            assert is_304 is True


@pytest.mark.asyncio
class TestCacheSaving:
    """Task 3.3: キャッシュ保存テスト"""

    async def test_save_cached_feed(self, cache_manager, filter_params_1):
        """キャッシュ保存が成功し、ETag を返すこと"""
        feed_xml = '<?xml version="1.0"?><rss>...</rss>'

        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            mock_redis.setex.return_value = True

            etag = await cache_manager.save_cached_feed("rss", filter_params_1, feed_xml)

            assert etag is not None
            assert etag.startswith('"')
            # setex が呼ばれたことを確認
            mock_redis.setex.assert_called_once()
            # TTL が 300秒（5分）であることを確認
            args = mock_redis.setex.call_args
            assert args[0][1] == 300  # TTL

    async def test_save_cached_feed_ttl_is_300(self, cache_manager, filter_params_1):
        """キャッシュの TTL が 300秒であることを確認"""
        feed_xml = '<?xml version="1.0"?><rss>...</rss>'

        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            await cache_manager.save_cached_feed("rss", filter_params_1, feed_xml)

            # setex の第2引数が TTL
            call_args = mock_redis.setex.call_args
            assert call_args[0][1] == 300


@pytest.mark.asyncio
class TestGracefulDegradation:
    """Task 3.4: Redis 障害時の graceful degradation テスト"""

    async def test_get_cached_feed_redis_failure_returns_miss(self, cache_manager, filter_params_1):
        """Redis 接続失敗時にキャッシュミスとして扱うこと"""
        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            mock_redis.get.side_effect = Exception("Redis connection error")

            feed_xml, etag, is_304 = await cache_manager.get_cached_feed("rss", filter_params_1)

            # 例外をキャッチし、キャッシュミスとして扱う
            assert feed_xml is None
            assert etag is None
            assert is_304 is False

    async def test_save_cached_feed_redis_failure_continues(self, cache_manager, filter_params_1):
        """Redis 接続失敗時にも処理を継続すること（例外を発生させない）"""
        feed_xml = '<?xml version="1.0"?><rss>...</rss>'

        with patch.object(cache_manager, 'redis_client', new_callable=AsyncMock) as mock_redis:
            mock_redis.setex.side_effect = Exception("Redis connection error")

            # 例外が発生せず、None または空文字列の ETag を返す
            etag = await cache_manager.save_cached_feed("rss", filter_params_1, feed_xml)

            # 処理が継続される（例外が発生しない）
            assert etag is not None or etag == ""
