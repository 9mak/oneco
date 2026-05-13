"""
robots.txt 遵守チェッカーのテスト

ロジック部分はオフラインでテスト可能。
"""

import pytest

from src.data_collector.utils.robots_check import (
    DEFAULT_USER_AGENT,
    is_allowed_by_robots,
    summarize,
)


def test_empty_robots_txt_is_permissive():
    """robots.txt が空 or 未取得なら許可とみなす（RFC 9309）"""
    result = is_allowed_by_robots("https://example.com/path", "")
    assert result.allowed is True
    assert "permissive" in result.reason


def test_robots_disallow_blocks_target():
    """User-agent: * Disallow: / は全URLをブロック"""
    robots = "User-agent: *\nDisallow: /\n"
    result = is_allowed_by_robots("https://example.com/animals", robots)
    assert result.allowed is False
    assert "disallowed" in result.reason


def test_robots_allow_specific_path():
    """allow パターンが効く"""
    robots = "User-agent: *\nDisallow: /private\nAllow: /public\n"
    public = is_allowed_by_robots("https://example.com/public/page", robots)
    private = is_allowed_by_robots("https://example.com/private/page", robots)
    assert public.allowed is True
    assert private.allowed is False


def test_specific_user_agent_overrides_wildcard():
    """専用 user-agent ルールが * を上書き"""
    robots = "User-agent: *\nDisallow: /\n\nUser-agent: OnecoCollector\nAllow: /\n"
    result = is_allowed_by_robots(
        "https://example.com/animals", robots, user_agent=DEFAULT_USER_AGENT
    )
    assert result.allowed is True


def test_invalid_url_returns_disallowed():
    """netloc のない URL は invalid として禁止"""
    result = is_allowed_by_robots("not-a-url", "User-agent: *\nAllow: /\n")
    assert result.allowed is False
    assert "invalid" in result.reason


def test_robots_url_is_derived_from_target():
    """robots_url が target の scheme + host から組み立てられる"""
    result = is_allowed_by_robots("https://example.com/path/x", "")
    assert result.robots_url == "https://example.com/robots.txt"


@pytest.mark.parametrize(
    "results, expected",
    [
        ([], {"total": 0, "allowed": 0, "disallowed": 0}),
    ],
)
def test_summarize_empty(results, expected):
    assert summarize(results) == expected


def test_summarize_counts():
    """summarize が件数を正しく集計する"""
    results = [
        is_allowed_by_robots("https://a.example.com/", ""),  # allowed
        is_allowed_by_robots("https://b.example.com/", "User-agent: *\nDisallow: /\n"),
    ]
    s = summarize(results)
    assert s == {"total": 2, "allowed": 1, "disallowed": 1}
