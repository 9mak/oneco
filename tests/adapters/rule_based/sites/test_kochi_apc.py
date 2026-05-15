"""高知県 wrapper のテスト

既存 KochiAdapter にデリゲートしていることを確認。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.kochi_apc import KochiApcAdapter
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="高知県動物愛護センター",
        prefecture="高知県",
        prefecture_code="39",
        list_url="https://kochi-apc.com/center-data/",
        category="adoption",
    )


def test_site_registered():
    assert SiteAdapterRegistry.get("高知県動物愛護センター") is KochiApcAdapter


def test_fetch_delegates_to_kochi_adapter():
    adapter = KochiApcAdapter(_site())
    expected = [("https://kochi-apc.com/center-data/abc/", "adoption")]
    with patch.object(adapter._kochi, "fetch_animal_list", return_value=expected) as m:
        result = adapter.fetch_animal_list()
    m.assert_called_once()
    assert result == expected


def test_extract_delegates_to_kochi_adapter():
    adapter = KochiApcAdapter(_site())
    mock_raw = MagicMock()
    with patch.object(adapter._kochi, "extract_animal_details", return_value=mock_raw) as m:
        result = adapter.extract_animal_details(
            "https://kochi-apc.com/center-data/abc/", category="adoption"
        )
    m.assert_called_once_with("https://kochi-apc.com/center-data/abc/", "adoption")
    assert result is mock_raw
