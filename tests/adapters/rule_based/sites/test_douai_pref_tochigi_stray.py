"""DouaiPrefTochigiStrayAdapter (douai.sakura.ne.jp) アダプターのテスト

栃木県動物愛護指導センターの「迷子動物収容情報」実データは、本体ドメイン
(douai.pref.tochigi.lg.jp) とは別の静的 HTML サイト (douai.sakura.ne.jp) に
あり、一覧 (`stray/{dog,cat}/list.html`) + 詳細 (`<管理番号>.html`) の
古典的な list+detail 構成を持つ (T121 調査で判明)。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.douai_pref_tochigi_stray import (
    DouaiPrefTochigiStrayAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _dog_site() -> SiteConfig:
    return SiteConfig(
        name="栃木県動物愛護指導センター（迷子動物・犬）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/list.html",
        category="lost",
        list_link_pattern="a[href$='.html']",
    )


def _cat_site() -> SiteConfig:
    return SiteConfig(
        name="栃木県動物愛護指導センター（迷子動物・猫）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://douai.sakura.ne.jp/wp/maigo/html/stray/cat/list.html",
        category="lost",
        list_link_pattern="a[href$='.html']",
    )


class TestDouaiPrefTochigiStrayListExtraction:
    def test_fetch_animal_list_extracts_detail_urls(self, fixture_html):
        adapter = DouaiPrefTochigiStrayAdapter(_dog_site())
        html = fixture_html("douai_pref_tochigi_stray__dog_list")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert "https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/2026-08-0022.html" in urls
        assert "https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/2026-08-0026.html" in urls
        assert "https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/2026-08-0027.html" in urls
        assert len(urls) == 3
        assert all(cat == "lost" for _u, cat in result)

    def test_fetch_animal_list_dedupes(self, fixture_html):
        adapter = DouaiPrefTochigiStrayAdapter(_dog_site())
        html = fixture_html("douai_pref_tochigi_stray__dog_list")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))

    def test_fetch_animal_list_cat_variant(self, fixture_html):
        adapter = DouaiPrefTochigiStrayAdapter(_cat_site())
        html = fixture_html("douai_pref_tochigi_stray__cat_list")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == 3
        assert all(cat == "lost" for _u, cat in result)

    def test_fetch_animal_list_zero_is_true_empty(self):
        """一覧テーブルに行が無い (在庫 0 件) は真の 0 件として扱う"""
        adapter = DouaiPrefTochigiStrayAdapter(_dog_site())
        empty_html = (
            "<html><body><h1>迷子動物収容情報一覧（犬）</h1>"
            "<table><tr><th>管理番号</th></tr></table></body></html>"
        )
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


class TestDouaiPrefTochigiStrayDetailExtraction:
    def test_extract_animal_details_returns_raw_data(self, fixture_html, assert_raw_animal):
        adapter = DouaiPrefTochigiStrayAdapter(_dog_site())
        html = fixture_html("douai_pref_tochigi_stray__dog_detail")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/2026-08-0022.html",
                category="lost",
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            management_number="2026-08-0022",
            shelter_date="2026/08/21",
            location="那須町　高久丙",
            species="犬",
            breed="雑種",
            sex="雌",
            age="子",
            color="黒、茶",
            size="小",
            category="lost",
        )

    def test_extract_filters_broken_image_and_keeps_valid_photos(self, fixture_html):
        """`../../image/` (ファイル名無し = 写真未登録) は除外し、実写真だけ残す"""
        adapter = DouaiPrefTochigiStrayAdapter(_dog_site())
        html = fixture_html("douai_pref_tochigi_stray__dog_detail")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/2026-08-0022.html"
            )
        assert len(raw.image_urls) == 2
        assert all(u.endswith(".JPG") for u in raw.image_urls)
        assert "https://douai.sakura.ne.jp/wp/maigo/html/image/20260821k1-1.JPG" in raw.image_urls


class TestDouaiPrefTochigiStrayNormalize:
    def test_normalize_returns_animal_data(self, fixture_html):
        adapter = DouaiPrefTochigiStrayAdapter(_dog_site())
        html = fixture_html("douai_pref_tochigi_stray__dog_detail")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(
                "https://douai.sakura.ne.jp/wp/maigo/html/stray/dog/2026-08-0022.html",
                category="lost",
            )
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert normalized.species == "犬"
        assert normalized.prefecture == "栃木県"


class TestDouaiPrefTochigiStrayRegistry:
    EXPECTED_SITE_NAMES = (
        "栃木県動物愛護指導センター（迷子動物・犬）",
        "栃木県動物愛護指導センター（迷子動物・猫）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_adapter(self, site_name):
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is DouaiPrefTochigiStrayAdapter, (
            f"{site_name} が DouaiPrefTochigiStrayAdapter に紐付いていません: {cls}"
        )
