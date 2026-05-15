"""豊橋市あいくる adapter テスト"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.toyohashi_aikuru import (
    ToyohashiAikuruAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(animal_type: str = "dog", category: str = "lost") -> SiteConfig:
    return SiteConfig(
        name=f"豊橋市あいくる（{'迷い犬' if animal_type == 'dog' else '迷い猫'}）",
        prefecture="愛知県",
        prefecture_code="23",
        list_url=f"https://toyohashi-aikuru.jp/animal_category/lost-found?animal_type={animal_type}",
        category=category,
    )


SAMPLE_LIST = """
<html><body>
  <article><a href="/animal/abc123" class="post-link">柴犬の保護</a></article>
  <article><a href="/animal/def456" class="post-link">秋田犬</a></article>
</body></html>
"""

SAMPLE_DETAIL = """
<html><body>
  <article>
    <dl>
      <dt>種別</dt><dd>犬</dd>
      <dt>性別</dt><dd>オス</dd>
      <dt>年齢</dt><dd>3歳</dd>
      <dt>毛色</dt><dd>茶</dd>
      <dt>体格</dt><dd>中型</dd>
      <dt>収容日</dt><dd>2026-04-01</dd>
      <dt>保護場所</dt><dd>豊橋市</dd>
    </dl>
    <img src="https://toyohashi-aikuru.jp/wp-content/uploads/dog1.jpg">
  </article>
</body></html>
"""


def test_fetch_extracts_detail_urls():
    adapter = ToyohashiAikuruAdapter(_site("dog"))
    with patch.object(adapter, "_http_get", return_value=SAMPLE_LIST):
        result = adapter.fetch_animal_list()
    assert len(result) == 2
    assert all(u.startswith("https://toyohashi-aikuru.jp/animal/") for u, _ in result)


def test_fetch_returns_empty_on_failure():
    """fetch 失敗時は空リスト返却 (在庫 0 件 fixture 対応)"""
    adapter = ToyohashiAikuruAdapter(_site("dog"))
    with patch.object(adapter, "_http_get", side_effect=Exception("network")):
        assert adapter.fetch_animal_list() == []


def test_extract_detail_returns_raw_data():
    adapter = ToyohashiAikuruAdapter(_site("dog"))
    with patch.object(adapter, "_http_get", return_value=SAMPLE_DETAIL):
        raw = adapter.extract_animal_details(
            "https://toyohashi-aikuru.jp/animal/abc123"
        )
    assert raw.species == "犬"
    assert raw.sex == "オス"
    assert raw.age == "3歳"
    assert raw.shelter_date == "2026-04-01"
    assert raw.location == "豊橋市"
    assert raw.image_urls == ["https://toyohashi-aikuru.jp/wp-content/uploads/dog1.jpg"]


def test_species_inferred_from_animal_type_query():
    """detail に種別が無い時、URL クエリから推定"""
    adapter = ToyohashiAikuruAdapter(_site("cat"))
    detail_no_species = SAMPLE_DETAIL.replace("<dt>種別</dt><dd>犬</dd>", "")
    with patch.object(adapter, "_http_get", return_value=detail_no_species):
        raw = adapter.extract_animal_details(
            "https://toyohashi-aikuru.jp/animal/x"
        )
    assert raw.species == "猫"


def test_two_sites_registered():
    assert SiteAdapterRegistry.get("豊橋市あいくる（迷い犬）") is ToyohashiAikuruAdapter
    assert SiteAdapterRegistry.get("豊橋市あいくる（迷い猫）") is ToyohashiAikuruAdapter
