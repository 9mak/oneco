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


def _site(requires_js: bool = True) -> SiteConfig:
    return SiteConfig(
        name="JSサイト",
        prefecture="熊本県",
        prefecture_code="43",
        list_url="https://example.com/list/",
        category="adoption",
        requires_js=requires_js,
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

    def test_http_get_applies_polite_wait_before_fetch(self):
        """_http_get が取得前に _polite_wait を呼び送信間隔を守ること(throttle バイパス防止)。

        旧実装は base._http_get の throttle を override で素通りし、JS サイトへ間隔保証
        なしでバースト送信していた（偽計業務妨害リスク）。
        """
        adapter = _SamplePlaywrightAdapter(_site())

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>ok</html>"

        with (
            patch(
                "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
                return_value=mock_fetcher,
            ),
            patch.object(adapter, "_polite_wait") as mock_wait,
        ):
            adapter._http_get("https://example.com/page")

        mock_wait.assert_called_once()

    def test_works_with_wordpress_list_adapter(self):
        """WordPressListAdapter と組み合わせて fetch_animal_list が動くこと"""
        adapter = _SamplePlaywrightAdapter(_site())
        list_html = '<html><body><a class="detail" href="/animals/1">a1</a></body></html>'
        with patch.object(adapter, "_http_get", return_value=list_html):
            result = adapter.fetch_animal_list()
        assert len(result) == 1
        assert result[0][0] == "https://example.com/animals/1"

    def test_http_get_delegates_to_static_fetch_when_requires_js_false(self):
        """requires_js=False のとき Playwright を使わず基底クラスの静的 HTTP に委譲すること

        T108: sites.yaml の requires_js フラグが静的 HTTP で取得できるサイトに
        誤って True 設定されている問題への対応。フラグ 1 つで切り替えられる
        ことを保証する。
        """
        adapter = _SamplePlaywrightAdapter(_site(requires_js=False))

        with (
            patch("data_collector.adapters.rule_based.playwright.PlaywrightFetcher") as mock_cls,
            patch(
                "data_collector.adapters.rule_based.base.RuleBasedAdapter._http_get",
                return_value="<html>static</html>",
            ) as mock_static,
        ):
            result = adapter._http_get("https://example.com/page")

        assert result == "<html>static</html>"
        mock_cls.assert_not_called()
        # unittest.mock.patch でクラス属性を差し替えると MagicMock は
        # ディスクリプタではないため self は自動束縛されない
        # (super()._http_get(...) の呼び出しに self は含まれない)。
        mock_static.assert_called_once_with(
            "https://example.com/page", timeout=30, extra_headers=None
        )

    def test_http_get_uses_playwright_when_requires_js_true(self):
        """requires_js=True (既定) のときは従来通り Playwright を使うこと (回帰防止)"""
        adapter = _SamplePlaywrightAdapter(_site(requires_js=True))

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>JS-rendered</html>"

        with patch(
            "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
            return_value=mock_fetcher,
        ):
            result = adapter._http_get("https://example.com/page")

        assert result == "<html>JS-rendered</html>"
        mock_fetcher.fetch.assert_called_once_with("https://example.com/page")
