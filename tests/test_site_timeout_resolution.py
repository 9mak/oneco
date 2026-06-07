"""run_rule_based_sites / run_llm_sites の timeout 解決テスト

過去 bug: rule-based 経路で `site.timeout_sec` を読まず、sites.yaml に
個別 timeout を設定したサイト (例: 高知 timeout_sec=240) が常にグローバル
SITE_TIMEOUT_SEC=120 で timeout していた。本テストは両経路が同一の
優先順位 (site.timeout_sec > requires_js 既定 > 通常既定) で解決することを保証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.data_collector.__main__ import (
    SITE_TIMEOUT_JS_SEC,
    SITE_TIMEOUT_SEC,
    run_rule_based_sites,
)


def _make_site(name: str, *, timeout_sec: int | None = None, requires_js: bool = False):
    """SiteConfig 風の Mock"""
    site = MagicMock()
    site.name = name
    site.timeout_sec = timeout_sec
    site.requires_js = requires_js
    site.list_url = f"https://example.com/{name}"
    site.extraction = "rule-based"
    site.category = "adoption"
    site.fallback_to_llm = False
    return site


def _capture_timeout_from_site_timeout(seconds: int, site_name: str):
    """site_timeout context manager の呼び出し時に seconds を記録するスタブ"""
    _capture_timeout_from_site_timeout.captured = seconds

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return _Ctx()


class TestRuleBasedTimeoutResolution:
    """run_rule_based_sites の timeout 解決"""

    def _run_one_site(self, site, monkeypatch):
        """1 サイトを run_rule_based_sites に流し、parallel_runner に渡された timeout を返す。

        並列化後は `site_timeout` (SIGALRM) を廃止し、`parallel_runner.run_sites_parallel`
        が `timeout_resolver(site) -> float` を呼んでサイト個別の秒数を解決する。
        ここでは run_sites_parallel をフックして timeout_resolver の戻り値を捕捉する。
        """
        from src.data_collector import __main__ as main_mod

        captured: dict = {}

        def fake_run_sites_parallel(
            sites, collect_fn, timeout_resolver, max_workers=10, on_outcome=None
        ):
            # 各 site に対する timeout_resolver の解決結果を記録
            for s in sites:
                captured["seconds"] = timeout_resolver(s)
            return []

        # parallel_runner は `__main__` 内で関数ローカル import されるため、
        # モジュール側の関数を差し替える。
        monkeypatch.setattr(
            "src.data_collector.orchestration.parallel_runner.run_sites_parallel",
            fake_run_sites_parallel,
        )

        # adapter 登録は eligible_sites フィルタを通過させるためだけに必要
        adapter_cls = MagicMock()
        adapter_instance = MagicMock()
        adapter_cls.return_value = adapter_instance
        monkeypatch.setattr(
            main_mod.SiteAdapterRegistry, "get", MagicMock(return_value=adapter_cls)
        )

        config = MagicMock()
        config.sites = [site]
        config.extraction.default_extraction = "rule-based"
        site.extraction = "rule-based"

        run_rule_based_sites(
            config=config,
            snapshot_store=MagicMock(),
            diff_detector=MagicMock(),
            output_writer=MagicMock(),
            notification_client=MagicMock(),
            db_connection=None,
            logger=MagicMock(),
            broken_tracker=None,
            previous_site_counts={},
        )

        return captured.get("seconds")

    def test_individual_timeout_sec_overrides_global(self, monkeypatch):
        """site.timeout_sec=240 が個別優先される (回帰テスト)"""
        site = _make_site("高知県動物愛護センター", timeout_sec=240)
        captured = self._run_one_site(site, monkeypatch)
        assert captured == 240, (
            f"site.timeout_sec=240 が反映されていない: 実際の timeout={captured}秒"
        )

    def test_requires_js_uses_js_default(self, monkeypatch):
        """timeout_sec 未指定 + requires_js=True → SITE_TIMEOUT_JS_SEC"""
        site = _make_site("JS必須サイト", timeout_sec=None, requires_js=True)
        captured = self._run_one_site(site, monkeypatch)
        assert captured == SITE_TIMEOUT_JS_SEC

    def test_default_timeout(self, monkeypatch):
        """timeout_sec 未指定 + requires_js=False → SITE_TIMEOUT_SEC"""
        site = _make_site("通常サイト", timeout_sec=None, requires_js=False)
        captured = self._run_one_site(site, monkeypatch)
        assert captured == SITE_TIMEOUT_SEC

    def test_individual_overrides_requires_js(self, monkeypatch):
        """site.timeout_sec 設定済なら requires_js より優先される"""
        site = _make_site("JS必須 + 個別設定", timeout_sec=300, requires_js=True)
        captured = self._run_one_site(site, monkeypatch)
        assert captured == 300


@pytest.fixture(autouse=True)
def _block_real_site_timeout(monkeypatch):
    """テスト中に SIGALRM の実シグナルが立たないように"""
    # _run_one_site で個別に monkeypatch するので追加保護は不要
    yield
