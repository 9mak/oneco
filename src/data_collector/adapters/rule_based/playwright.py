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
        # extra_headers は無視（PlaywrightFetcher が ONECO_USER_AGENT を設定する）。
        # base._http_get と同様にアクセス間隔を保証する。override でこの待機を
        # 飛ばすと JS サイトへ間隔なしでバースト送信してしまう（偽計業務妨害リスク）。
        self._polite_wait(getattr(self.site_config, "request_interval", None))
        try:
            fetcher = PlaywrightFetcher(
                wait_selector=self.WAIT_SELECTOR,
                timeout=self.PLAYWRIGHT_TIMEOUT_MS,
            )
            return fetcher.fetch(url)
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(f"Playwright fetch 失敗: {e}", url=url) from e
