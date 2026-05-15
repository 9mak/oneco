"""SiteAdapterRegistry のテスト

サイト名 → rule-based adapter class マッピングを検証。
"""

from __future__ import annotations

import pytest

from data_collector.adapters.rule_based.base import RuleBasedAdapter
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.wordpress_list import (
    FieldSpec,
    WordPressListAdapter,
)
from data_collector.domain.models import AnimalData, RawAnimalData


class _DummyAdapter(WordPressListAdapter):
    LIST_LINK_SELECTOR = "a"
    FIELD_SELECTORS = {"species": FieldSpec(label="種別")}


class _AnotherAdapter(WordPressListAdapter):
    LIST_LINK_SELECTOR = "a.b"
    FIELD_SELECTORS = {"species": FieldSpec(label="種別")}


@pytest.fixture(autouse=True)
def _clean_registry():
    """各テスト前後に Registry をクリーンアップ"""
    SiteAdapterRegistry._registry.clear()
    yield
    SiteAdapterRegistry._registry.clear()


class TestSiteAdapterRegistry:
    def test_register_and_get(self):
        SiteAdapterRegistry.register("テストサイト", _DummyAdapter)
        assert SiteAdapterRegistry.get("テストサイト") is _DummyAdapter

    def test_get_returns_none_for_unregistered(self):
        assert SiteAdapterRegistry.get("存在しないサイト") is None

    def test_register_duplicate_raises(self):
        SiteAdapterRegistry.register("サイト1", _DummyAdapter)
        with pytest.raises(ValueError):
            SiteAdapterRegistry.register("サイト1", _AnotherAdapter)

    def test_all_registered_lists_names(self):
        SiteAdapterRegistry.register("A", _DummyAdapter)
        SiteAdapterRegistry.register("B", _AnotherAdapter)
        names = SiteAdapterRegistry.all_registered()
        assert set(names) == {"A", "B"}

    def test_coverage_stats(self):
        SiteAdapterRegistry.register("A", _DummyAdapter)
        SiteAdapterRegistry.register("B", _AnotherAdapter)
        stats = SiteAdapterRegistry.coverage_stats(["A", "B", "C", "D"])
        assert stats["total"] == 4
        assert stats["rule_based"] == 2
        assert stats["llm_only"] == 2
