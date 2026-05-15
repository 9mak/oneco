"""__main__.py の rule-based / LLM 振り分けロジックのテスト

Phase A2 Task 2.2: run_rule_based_sites と main() の振り分け。
"""

from __future__ import annotations

import pytest

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
