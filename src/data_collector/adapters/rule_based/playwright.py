"""PlaywrightFetchMixin - JS 描画必須サイトの取得を Playwright に差し替える mixin

WordPressListAdapter / SinglePageTableAdapter と多重継承で組合せて使う。

例:
    class KumamotoAdapter(PlaywrightFetchMixin, WordPressListAdapter):
        WAIT_SELECTOR = ".animal-list"
        LIST_LINK_SELECTOR = ".animal-card a"
        FIELD_SELECTORS = {...}
"""

from __future__ import annotations

from typing import ClassVar

from ...llm.fetcher import PlaywrightFetcher
from ..municipality_adapter import NetworkError


class PlaywrightFetchMixin:
    """Playwright で HTML を取得する mixin

    `RuleBasedAdapter._http_get` を override して、
    JavaScript 実行後の HTML を返す。
    """

    WAIT_SELECTOR: ClassVar[str | None] = None
    PLAYWRIGHT_TIMEOUT_MS: ClassVar[int] = 30000

    def _http_get(
        self,
        url: str,
        *,
        timeout: int = 30,
        extra_headers: dict[str, str] | None = None,
    ) -> str:
        """Playwright で JavaScript 実行後の HTML を取得"""
        # extra_headers は無視（Playwright は default User-Agent を内部で設定）
        try:
            fetcher = PlaywrightFetcher(
                wait_selector=self.WAIT_SELECTOR,
                timeout=self.PLAYWRIGHT_TIMEOUT_MS,
            )
            return fetcher.fetch(url)
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Playwright fetch 失敗: {e}", url=url
            ) from e
