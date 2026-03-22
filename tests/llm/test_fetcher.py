"""PageFetcher（StaticFetcher / PlaywrightFetcher）のユニットテスト"""

from unittest.mock import MagicMock, patch

import pytest

from src.data_collector.adapters.municipality_adapter import NetworkError
from src.data_collector.llm.adapter import LlmAdapter
from src.data_collector.llm.config import SiteConfig
from src.data_collector.llm.fetcher import PageFetcher, PlaywrightFetcher, StaticFetcher
from src.data_collector.llm.providers.base import ExtractionResult, LlmProvider


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------

class MockProvider(LlmProvider):
    """最小限のモックLlmProvider"""

    def extract_animal_data(self, html_content, source_url, category):
        return ExtractionResult(fields={}, input_tokens=0, output_tokens=0)

    def extract_detail_links(self, html_content, base_url):
        return []


def _make_site_config(**kwargs) -> SiteConfig:
    defaults = dict(
        name="テストサイト",
        prefecture="テスト県",
        prefecture_code="99",
        list_url="https://example.com/list",
        category="adoption",
        request_interval=1.0,
    )
    defaults.update(kwargs)
    return SiteConfig(**defaults)


# ---------------------------------------------------------------------------
# StaticFetcher
# ---------------------------------------------------------------------------

class TestStaticFetcher:
    def test_static_fetcher_uses_requests(self):
        """StaticFetcherがrequestsを使ってHTMLを返すこと"""
        mock_response = MagicMock()
        mock_response.text = "<html><body>テスト</body></html>"
        mock_response.apparent_encoding = "utf-8"

        with patch(
            "src.data_collector.llm.fetcher.requests.get",
            return_value=mock_response,
        ) as mock_get:
            fetcher = StaticFetcher()
            result = fetcher.fetch("https://example.com/page")

        mock_get.assert_called_once_with("https://example.com/page", timeout=30)
        assert result == "<html><body>テスト</body></html>"

    def test_static_fetcher_raises_network_error_on_failure(self):
        """requestsの例外がNetworkErrorに変換されること"""
        import requests as req

        with patch(
            "src.data_collector.llm.fetcher.requests.get",
            side_effect=req.RequestException("connection refused"),
        ):
            fetcher = StaticFetcher()
            with pytest.raises(NetworkError) as exc_info:
                fetcher.fetch("https://example.com/fail")

        assert "ページ取得失敗" in str(exc_info.value)

    def test_static_fetcher_is_page_fetcher(self):
        """StaticFetcherがPageFetcherのサブクラスであること"""
        assert issubclass(StaticFetcher, PageFetcher)


# ---------------------------------------------------------------------------
# PlaywrightFetcher
# ---------------------------------------------------------------------------

class TestPlaywrightFetcher:
    def test_playwright_fetcher_uses_playwright(self):
        """PlaywrightFetcherがsync_playwright APIを正しく呼ぶこと"""
        expected_html = "<html><body>JS描画済み</body></html>"

        # playwright.sync_api.sync_playwright のモック構築
        mock_page = MagicMock()
        mock_page.content.return_value = expected_html

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = MagicMock()
        mock_chromium.launch.return_value = mock_browser

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        mock_sync_playwright = MagicMock()
        mock_sync_playwright.return_value.__enter__ = MagicMock(
            return_value=mock_playwright_instance
        )
        mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.data_collector.llm.fetcher.sync_playwright",
            mock_sync_playwright,
        ):
            fetcher = PlaywrightFetcher()
            result = fetcher.fetch("https://example.com/js-page")

        # chromium.launch(headless=True) が呼ばれること
        mock_chromium.launch.assert_called_once_with(headless=True)
        # page.goto が正しい引数で呼ばれること
        mock_page.goto.assert_called_once_with(
            "https://example.com/js-page",
            wait_until="networkidle",
            timeout=30000,
        )
        # page.content() の結果が返ること
        assert result == expected_html
        # ブラウザが閉じられること
        mock_browser.close.assert_called_once()

    def test_playwright_fetcher_waits_for_selector_when_specified(self):
        """wait_selectorが指定された場合にwait_for_selectorが呼ばれること"""
        mock_page = MagicMock()
        mock_page.content.return_value = "<html></html>"

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = MagicMock()
        mock_chromium.launch.return_value = mock_browser

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        mock_sync_playwright = MagicMock()
        mock_sync_playwright.return_value.__enter__ = MagicMock(
            return_value=mock_playwright_instance
        )
        mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.data_collector.llm.fetcher.sync_playwright",
            mock_sync_playwright,
        ):
            fetcher = PlaywrightFetcher(wait_selector=".animal-list")
            fetcher.fetch("https://example.com/js-page")

        mock_page.wait_for_selector.assert_called_once_with(".animal-list", timeout=30000)

    def test_playwright_fetcher_skips_wait_for_selector_when_none(self):
        """wait_selectorがNoneの場合はwait_for_selectorが呼ばれないこと"""
        mock_page = MagicMock()
        mock_page.content.return_value = "<html></html>"

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = MagicMock()
        mock_chromium.launch.return_value = mock_browser

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        mock_sync_playwright = MagicMock()
        mock_sync_playwright.return_value.__enter__ = MagicMock(
            return_value=mock_playwright_instance
        )
        mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.data_collector.llm.fetcher.sync_playwright",
            mock_sync_playwright,
        ):
            fetcher = PlaywrightFetcher(wait_selector=None)
            fetcher.fetch("https://example.com/js-page")

        mock_page.wait_for_selector.assert_not_called()

    def test_playwright_fetcher_raises_network_error_on_failure(self):
        """Playwright例外がNetworkErrorに変換されること"""
        mock_sync_playwright = MagicMock()
        mock_sync_playwright.return_value.__enter__ = MagicMock(
            side_effect=Exception("browser launch failed")
        )
        mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.data_collector.llm.fetcher.sync_playwright",
            mock_sync_playwright,
        ):
            fetcher = PlaywrightFetcher()
            with pytest.raises(NetworkError) as exc_info:
                fetcher.fetch("https://example.com/fail")

        assert "Playwrightページ取得失敗" in str(exc_info.value)

    def test_playwright_fetcher_is_page_fetcher(self):
        """PlaywrightFetcherがPageFetcherのサブクラスであること"""
        assert issubclass(PlaywrightFetcher, PageFetcher)


# ---------------------------------------------------------------------------
# LlmAdapter のフェッチャー選択ロジック
# ---------------------------------------------------------------------------

class TestAdapterFetcherSelection:
    def test_adapter_uses_static_fetcher_by_default(self):
        """requires_js=False のサイトはStaticFetcherを使うこと"""
        site_config = _make_site_config(
            requires_js=False,
            list_link_pattern="a.link",
        )

        mock_static_fetch = MagicMock(return_value="<html><body><a class='link' href='/d/1'>x</a></body></html>")

        with patch(
            "src.data_collector.llm.fetcher.requests.get"
        ) as mock_get:
            mock_response = MagicMock()
            mock_response.text = "<html><body><a class='link' href='/d/1'>x</a></body></html>"
            mock_response.apparent_encoding = "utf-8"
            mock_get.return_value = mock_response

            with patch("src.data_collector.llm.adapter.time.sleep"):
                adapter = LlmAdapter(
                    site_config=site_config,
                    provider=MockProvider(),
                )
                adapter.fetch_animal_list()

        # requests.get が呼ばれていること（StaticFetcher経由）
        mock_get.assert_called()

    def test_adapter_uses_playwright_fetcher_when_requires_js(self):
        """requires_js=True のサイトはPlaywrightFetcherを使うこと"""
        site_config = _make_site_config(
            requires_js=True,
            wait_selector=".animal-list",
            list_link_pattern="a.link",
        )

        expected_html = "<html><body><a class='link' href='/d/1'>x</a></body></html>"

        mock_page = MagicMock()
        mock_page.content.return_value = expected_html

        mock_context = MagicMock()
        mock_context.new_page.return_value = mock_page

        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context

        mock_chromium = MagicMock()
        mock_chromium.launch.return_value = mock_browser

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium = mock_chromium

        mock_sync_playwright = MagicMock()
        mock_sync_playwright.return_value.__enter__ = MagicMock(
            return_value=mock_playwright_instance
        )
        mock_sync_playwright.return_value.__exit__ = MagicMock(return_value=False)

        with patch(
            "src.data_collector.llm.fetcher.sync_playwright",
            mock_sync_playwright,
        ):
            with patch("src.data_collector.llm.adapter.time.sleep"):
                adapter = LlmAdapter(
                    site_config=site_config,
                    provider=MockProvider(),
                )
                adapter.fetch_animal_list()

        # sync_playwright が呼ばれていること（PlaywrightFetcher経由）
        mock_sync_playwright.assert_called()
        # wait_selector が渡されていること
        mock_page.wait_for_selector.assert_called_with(".animal-list", timeout=30000)

    def test_adapter_injected_fetcher_is_used(self):
        """コンストラクタで注入したfetcherが優先して使われること"""
        site_config = _make_site_config(
            requires_js=False,
            list_link_pattern="a.link",
        )

        mock_fetcher = MagicMock(spec=PageFetcher)
        mock_fetcher.fetch.return_value = (
            "<html><body><a class='link' href='/d/1'>x</a></body></html>"
        )

        with patch("src.data_collector.llm.adapter.time.sleep"):
            adapter = LlmAdapter(
                site_config=site_config,
                provider=MockProvider(),
                fetcher=mock_fetcher,
            )
            adapter.fetch_animal_list()

        mock_fetcher.fetch.assert_called()
