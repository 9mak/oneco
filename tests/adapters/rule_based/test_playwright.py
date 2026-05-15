"""PlaywrightFetchMixin のテスト

JS 必須サイト用の取得を mixin で差し替える設計を検証。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.wordpress_list import (
    FieldSpec,
    WordPressListAdapter,
)
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="JSサイト",
        prefecture="熊本県",
        prefecture_code="43",
        list_url="https://example.com/list/",
        category="adoption",
        requires_js=True,
        wait_selector=".animals",
    )


class _SamplePlaywrightAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    LIST_LINK_SELECTOR = "a.detail"
    WAIT_SELECTOR = ".animals"
    FIELD_SELECTORS = {
        "species": FieldSpec(label="種別"),
    }


class TestPlaywrightFetchMixin:
    def test_http_get_uses_playwright_fetcher(self):
        """_http_get が PlaywrightFetcher.fetch を呼ぶこと"""
        adapter = _SamplePlaywrightAdapter(_site())

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>JS-rendered</html>"

        with patch(
            "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
            return_value=mock_fetcher,
        ) as mock_cls:
            result = adapter._http_get("https://example.com/page")

        assert result == "<html>JS-rendered</html>"
        mock_cls.assert_called_once()
        # WAIT_SELECTOR が PlaywrightFetcher に渡されること
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("wait_selector") == ".animals"
        mock_fetcher.fetch.assert_called_once_with("https://example.com/page")

    def test_works_with_wordpress_list_adapter(self):
        """WordPressListAdapter と組み合わせて fetch_animal_list が動くこと"""
        adapter = _SamplePlaywrightAdapter(_site())
        list_html = '<html><body><a class="detail" href="/animals/1">a1</a></body></html>'
        with patch.object(adapter, "_http_get", return_value=list_html):
            result = adapter.fetch_animal_list()
        assert len(result) == 1
        assert result[0][0] == "https://example.com/animals/1"
