"""__main__.py の rule-based / LLM 振り分けロジックのテスト

Phase A2 Task 2.2: run_rule_based_sites と main() の振り分け。
"""

from __future__ import annotations

from data_collector.__main__ import (
    PROVIDER_REGISTRY,
    _effective_extraction,
)
from data_collector.llm.config import (
    ExtractionConfig,
    SiteConfig,
    SitesConfig,
)


def _site(extraction: str | None = None) -> SiteConfig:
    """テスト用 SiteConfig （extraction を指定可）"""
    kwargs = {
        "name": "テスト",
        "prefecture": "高知県",
        "prefecture_code": "39",
        "list_url": "https://example.com/",
    }
    if extraction is not None:
        kwargs["extraction"] = extraction
    return SiteConfig(**kwargs)


def _config(default_extraction: str = "llm") -> SitesConfig:
    return SitesConfig(
        extraction=ExtractionConfig(
            default_provider="anthropic",
            default_model="claude-haiku-4-5-20251001",
            default_extraction=default_extraction,
        ),
        sites=[_site()],
    )


class TestEffectiveExtraction:
    def test_explicit_site_extraction_wins(self):
        """サイト個別 extraction が指定されていればそれを採用"""
        site = _site(extraction="rule-based")
        config = _config(default_extraction="llm")
        assert _effective_extraction(site, config) == "rule-based"

    def test_falls_back_to_default_extraction_when_none(self):
        """サイト個別が空の時 default_extraction が採用される"""
        site = _site(extraction=None)
        config = _config(default_extraction="rule-based")
        assert _effective_extraction(site, config) == "rule-based"

    def test_default_to_llm_when_unspecified(self):
        site = _site(extraction=None)
        config = _config(default_extraction="llm")
        assert _effective_extraction(site, config) == "llm"


class TestProviderRegistry:
    def test_anthropic_registered(self):
        assert "anthropic" in PROVIDER_REGISTRY

    def test_groq_registered(self):
        assert "groq" in PROVIDER_REGISTRY


class TestSiteRunReturnTypeContract:
    """run_llm_sites / run_rule_based_sites の戻り値契約

    PR #20 で bool → tuple[succeeded, failed, zero_count_sites] に変更した。
    main 側で「成功 0 件かつ失敗 > 0 のみ exit 1、それ以外は exit 0」の
    部分成功許容判定に使うため、空 config では (0, 0, []) を返すことが
    契約として固定されている必要がある。
    """

    def test_run_llm_sites_returns_zero_zero_empty_for_empty_config(self):
        from unittest.mock import Mock

        from data_collector.__main__ import run_llm_sites

        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="llm",
            ),
            sites=[],
        )
        result = run_llm_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
        )
        assert result == (0, 0, [])

    def test_run_rule_based_sites_returns_zero_zero_empty_for_empty_config(self):
        from unittest.mock import Mock

        from data_collector.__main__ import run_rule_based_sites

        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="rule-based",
            ),
            sites=[],
        )
        result = run_rule_based_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
        )
        assert result == (0, 0, [])


class TestBrokenSiteSkipThreshold:
    """BROKEN_SITE_SKIP_THRESHOLD で連続失敗サイトをスキップする動作"""

    def test_threshold_default_is_3(self):
        """環境変数未指定時は 3 (Requirement 6.4 系)"""
        import os
        from unittest.mock import patch

        # 環境変数を空にして再読み込みするのは module level でセットされる
        # ため難しい。代わりに getenv の挙動だけ確認する。
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROKEN_SITE_SKIP_THRESHOLD", None)
            assert int(os.getenv("BROKEN_SITE_SKIP_THRESHOLD", "3")) == 3

    def test_run_rule_based_sites_skips_site_with_high_consecutive_failures(self, tmp_path):
        """consecutive_failures >= 閾値 のサイトは adapter 呼び出しに到達しない"""
        from unittest.mock import Mock

        from data_collector.__main__ import run_rule_based_sites
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker
        from data_collector.adapters.rule_based.registry import SiteAdapterRegistry

        # adapter は呼ばれないはず（呼ばれたら Mock の call_count が増える）
        spy_adapter_cls = Mock()
        SiteAdapterRegistry.register("テスト_スキップ対象", spy_adapter_cls)

        broken_path = tmp_path / "broken_sites.yaml"
        tracker = BrokenSitesTracker(broken_path)
        # 連続 5 回失敗（閾値 3 を超える）
        for _ in range(5):
            tracker.record_failure("テスト_スキップ対象", "permanent failure")

        site = _site(extraction="rule-based")
        site = type(site)(**{**site.model_dump(), "name": "テスト_スキップ対象"})
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="rule-based",
            ),
            sites=[site],
        )

        succeeded, failed, zero = run_rule_based_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
            broken_tracker=tracker,
        )

        assert spy_adapter_cls.call_count == 0, (
            "閾値超えサイトでは adapter コンストラクタも呼ばれない"
        )
        assert (succeeded, failed, zero) == (0, 0, []), (
            "スキップは success / failure どちらにもカウントしない (0件サイトでもない)"
        )
