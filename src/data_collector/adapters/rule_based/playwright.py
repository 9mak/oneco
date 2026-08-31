"""PlaywrightFetchMixin - JS 描画必須サイトの取得を Playwright に差し替える mixin

WordPressListAdapter / SinglePageTableAdapter と多重継承で組合せて使う。

例:
    class KumamotoAdapter(PlaywrightFetchMixin, WordPressListAdapter):
        WAIT_SELECTOR = ".animal-list"
        LIST_LINK_SELECTOR = ".animal-card a"
        FIELD_SELECTORS = {...}

T108 (2026-08-31) までは `_http_get` を無条件に Playwright 実装へ差し替えて
おり、`sites.yaml` の `requires_js` フラグは (timeout 既定値の切替を除いて)
rule-based 経路では一切参照されない死んだ設定値だった。そのため
「静的 HTTP GET で取得できるのに `requires_js: true` のまま」という誤フラグ
が 25 件中 22 件で発生していた (徳島/香川さぬき/沖縄/熊本/東京/福岡保護中)。
本 mixin は `site_config.requires_js` を実行時に見て、False なら基底クラス
(`RuleBasedAdapter._http_get` 相当) の静的 HTTP 実装に委譲するよう変更した。
これにより sites.yaml のフラグ 1 つで Playwright / 静的 HTTP を切り替えられ、
将来サイトが再び JS 化した場合もアダプタ本体を書き換えず `requires_js: true`
に戻すだけで復旧できる (同一クラスで requires_js が site ごとに異なる
福岡市わんにゃん adapter のようなケースにも対応できる)。
"""

from __future__ import annotations

from typing import ClassVar

from ...llm.fetcher import PlaywrightFetcher
from ..municipality_adapter import NetworkError


class PlaywrightFetchMixin:
    """Playwright で HTML を取得する mixin

    `site_config.requires_js` が True のときだけ `RuleBasedAdapter._http_get`
    を override して JavaScript 実行後の HTML を返す。False のときは
    `super()._http_get(...)` (MRO 上の次のクラス、通常は静的 HTTP 実装) に
    そのまま委譲する。
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
        """`requires_js` に応じて Playwright / 静的 HTTP を切り替えて HTML を取得"""
        if not getattr(self.site_config, "requires_js", True):
            # 静的 HTTP で取得可能と判明したサイト向けの経路。
            # 型チェッカーは Mixin 単体で super() の型を解決できないため無視する。
            return super()._http_get(  # type: ignore[misc]
                url, timeout=timeout, extra_headers=extra_headers
            )

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
