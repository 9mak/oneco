"""RobotsChecker のテスト"""

from unittest.mock import patch

import pytest

from src.data_collector.llm.robots_checker import RobotsChecker


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class TestRobotsChecker:
    """ベストエフォートの robots.txt 遵守チェッカー"""

    def test_returns_true_when_disallow_does_not_match(self):
        """allow なパス → True"""
        robots = "User-agent: *\nDisallow: /private/\n"
        with patch(
            "src.data_collector.llm.robots_checker.requests.get",
            return_value=_FakeResponse(200, robots),
        ):
            checker = RobotsChecker(user_agent="oneco-collector/1.0")
            assert checker.is_allowed("https://example.com/public/list") is True

    def test_returns_false_when_disallow_matches(self):
        """disallow なパス → False"""
        robots = "User-agent: *\nDisallow: /private/\n"
        with patch(
            "src.data_collector.llm.robots_checker.requests.get",
            return_value=_FakeResponse(200, robots),
        ):
            checker = RobotsChecker(user_agent="oneco-collector/1.0")
            assert checker.is_allowed("https://example.com/private/secret") is False

    def test_returns_true_when_robots_missing(self):
        """robots.txt が 404 → ベストエフォートで True"""
        with patch(
            "src.data_collector.llm.robots_checker.requests.get",
            return_value=_FakeResponse(404),
        ):
            checker = RobotsChecker()
            assert checker.is_allowed("https://example.com/anything") is True

    def test_returns_true_when_fetch_raises(self):
        """fetch 失敗 → ベストエフォートで True"""
        with patch(
            "src.data_collector.llm.robots_checker.requests.get",
            side_effect=ConnectionError("boom"),
        ):
            checker = RobotsChecker()
            assert checker.is_allowed("https://example.com/anything") is True

    def test_caches_per_domain(self):
        """同一ドメインの 2 回目呼び出しは fetch しない（キャッシュ）"""
        robots = "User-agent: *\nDisallow: /private/\n"
        with patch(
            "src.data_collector.llm.robots_checker.requests.get",
            return_value=_FakeResponse(200, robots),
        ) as mock_get:
            checker = RobotsChecker()
            checker.is_allowed("https://example.com/a")
            checker.is_allowed("https://example.com/b")
            assert mock_get.call_count == 1

    def test_separate_cache_per_domain(self):
        """別ドメインは別 fetch"""
        robots = "User-agent: *\nDisallow:\n"
        with patch(
            "src.data_collector.llm.robots_checker.requests.get",
            return_value=_FakeResponse(200, robots),
        ) as mock_get:
            checker = RobotsChecker()
            checker.is_allowed("https://a.example/x")
            checker.is_allowed("https://b.example/x")
            assert mock_get.call_count == 2

    @pytest.mark.parametrize(
        "url",
        ["", "not-a-url", "ftp://example.com/x"],
    )
    def test_invalid_or_non_http_url_returns_true(self, url: str):
        """非 http(s) URL は判定しない（ベストエフォートで True）"""
        checker = RobotsChecker()
        assert checker.is_allowed(url) is True
