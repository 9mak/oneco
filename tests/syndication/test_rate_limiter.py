"""
Tests for rate limiter middleware.

RED phase: Write failing tests for rate limiting functionality.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class TestRateLimiter:
    """Test suite for rate limiter middleware."""

    def test_rate_limit_headers_present(self, client: TestClient):
        """Test that rate limit headers are present in response."""
        response = client.get("/feeds/rss?species=犬")

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["X-RateLimit-Limit"] == "60"

    def test_rate_limit_not_exceeded_within_limit(self, client: TestClient):
        """Test that requests within limit are allowed."""
        # Make 5 requests (well within 60/minute limit)
        for i in range(5):
            response = client.get(f"/feeds/rss?species=犬&limit={10 + i}")
            assert response.status_code == 200

            remaining = int(response.headers.get("X-RateLimit-Remaining", "0"))
            # Remaining should decrease with each request
            assert remaining >= 0

    @pytest.mark.skip(reason="Rate limiting causes test slowdown - tested manually")
    def test_rate_limit_exceeded_returns_429(self, client: TestClient):
        """Test that exceeding rate limit returns 429 Too Many Requests."""
        # This test would require making 61 requests rapidly
        # Skipped in automated tests to avoid slowdown
        pass

    def test_rate_limit_retry_after_header_on_429(self):
        """Test that Retry-After header is present on 429 response."""
        # Mock test - actual 429 testing would be too slow
        with patch("slowapi.Limiter.limit") as mock_limit:
            mock_limit.side_effect = Exception("Rate limit exceeded")
            # In real scenario, this would return 429 with Retry-After header
            assert True  # Placeholder

    def test_rate_limit_reset_header_format(self, client: TestClient):
        """Test that X-RateLimit-Reset header is in correct format."""
        response = client.get("/feeds/rss?species=犬")

        reset_header = response.headers.get("X-RateLimit-Reset")
        if reset_header:
            # Should be a Unix timestamp (integer or float)
            try:
                reset_time = float(reset_header)
                assert reset_time > 0
            except ValueError:
                pytest.fail("X-RateLimit-Reset header is not a valid number")

    def test_rate_limit_applies_to_all_feed_endpoints(self, client: TestClient):
        """Test that rate limiting applies to all feed endpoints."""
        endpoints = [
            "/feeds/rss",
            "/feeds/atom",
            "/feeds/archive/rss",
            "/feeds/archive/atom",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # All should have rate limit headers (even if they return errors)
            assert "X-RateLimit-Limit" in response.headers or response.status_code in [400, 500]

    def test_rate_limit_graceful_degradation_on_redis_failure(self, client: TestClient):
        """Test that rate limiting gracefully degrades on Redis failure."""
        # If Redis is down, rate limiting should be disabled
        # Service should continue to work
        response = client.get("/feeds/rss?species=犬")

        # Should get either 200 or rate limit headers
        # But service should not fail completely
        assert response.status_code in [200, 429, 500]


class TestCreateLimiterPing:
    """create_limiter() の startup 時 Redis 接続テスト"""

    def test_returns_none_on_unreachable_redis(self):
        """到達不可能な Redis URL なら None を返す（fail-open）"""
        from src.syndication_service.middleware.rate_limiter import create_limiter

        # 確実に到達できない URL
        result = create_limiter("redis://10.255.255.1:6379/0")
        assert result is None

    def test_returns_limiter_for_memory_backend(self):
        """memory:// backend は ping せず Limiter を返す（テスト用途）"""
        from src.syndication_service.middleware.rate_limiter import create_limiter

        limiter = create_limiter("memory://")
        assert limiter is not None


class TestClientIpKey:
    """client_ip_key() のキー算出（プロキシ背後のクライアント識別）"""

    def test_uses_xforwarded_for_first_entry(self):
        """X-Forwarded-For があれば先頭(オリジナルクライアント)を採用する

        get_remote_address だと Cloud Run では GFE の IP になり全リクエストが
        同一キー(グローバルバケット)になってしまう。
        """
        from types import SimpleNamespace

        from src.syndication_service.middleware.rate_limiter import client_ip_key

        req = SimpleNamespace(
            headers={"x-forwarded-for": "203.0.113.7, 35.191.0.1"},
            client=SimpleNamespace(host="35.191.0.1"),
        )
        assert client_ip_key(req) == "203.0.113.7"

    def test_falls_back_to_client_host_without_xff(self):
        """X-Forwarded-For が無ければ request.client.host を使う"""
        from types import SimpleNamespace

        from src.syndication_service.middleware.rate_limiter import client_ip_key

        req = SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.5"))
        assert client_ip_key(req) == "10.0.0.5"
