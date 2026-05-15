"""ワンニャピアあきた adapter テスト

JS 必須サイトなので静的 HTML 取得時は常に空リスト返却することを検証。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.wannyapia_akita import (
    WannyapiaAkitaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(species: str = "犬") -> SiteConfig:
    return SiteConfig(
        name=f"ワンニャピアあきた（譲渡{species}）",
        prefecture="秋田県",
        prefecture_code="05",
        list_url=f"https://wannyapia.akita.jp/pages/protective-{'dogs' if species == '犬' else 'cats'}",
        category="adoption",
    )


def test_fetch_returns_empty_list_for_js_only_site():
    """静的 HTML 取得では JS が動かないので 0 件返却"""
    adapter = WannyapiaAkitaAdapter(_site("犬"))
    with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
        result = adapter.fetch_animal_list()
    assert result == []


def test_fetch_returns_empty_on_network_error():
    adapter = WannyapiaAkitaAdapter(_site("猫"))
    with patch.object(adapter, "_http_get", side_effect=Exception("network")):
        assert adapter.fetch_animal_list() == []


def test_extract_raises_parsing_error():
    adapter = WannyapiaAkitaAdapter(_site("犬"))
    with pytest.raises(ParsingError):
        adapter.extract_animal_details("https://wannyapia.akita.jp/animal/1")


def test_two_sites_registered():
    assert SiteAdapterRegistry.get("ワンニャピアあきた（譲渡犬）") is WannyapiaAkitaAdapter
    assert SiteAdapterRegistry.get("ワンニャピアあきた（譲渡猫）") is WannyapiaAkitaAdapter


def test_real_fixture_handles_gracefully(fixture_html):
    """実 fixture (JS 待ち状態の HTML) でも例外なし"""
    html = fixture_html("wannyapia_akita")
    adapter = WannyapiaAkitaAdapter(_site("犬"))
    with patch.object(adapter, "_http_get", return_value=html):
        result = adapter.fetch_animal_list()
    assert isinstance(result, list)
    assert len(result) == 0
