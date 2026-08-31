"""DouaiPrefTochigiPuppyAdapter (work/puppy, work/kitten) アダプターのテスト

栃木県動物愛護指導センターの子犬/子猫譲渡ページは、詳細ページを持たない
1 ページ完結型で、各動物は WordPress の Gutenberg テーブルブロック
(`table.has-fixed-layout`) の「列」として横並びに表現される
(行=項目、列=個体、という一般的な single-page-table とは転置した構造)。
T121 調査 (2026-08-31) で判明した実データ構造に基づく。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.douai_pref_tochigi_puppy import (
    DouaiPrefTochigiPuppyAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _puppy_site() -> SiteConfig:
    return SiteConfig(
        name="栃木県動物愛護指導センター（子犬譲渡）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://www.douai.pref.tochigi.lg.jp/work/puppy/",
        category="adoption",
        single_page=True,
    )


def _kitten_site() -> SiteConfig:
    return SiteConfig(
        name="栃木県動物愛護指導センター（子猫譲渡）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://www.douai.pref.tochigi.lg.jp/work/kitten/",
        category="adoption",
        single_page=True,
    )


class TestDouaiPrefTochigiPuppyListExtraction:
    def test_fetch_animal_list_counts_all_available_puppies(self, fixture_html):
        """譲渡会予定 5 頭 (番号未定) + 随時譲渡 9 頭 = 14 頭が全て取得される"""
        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        html = fixture_html("douai_pref_tochigi_puppy__puppy_page")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 14
        assert all(cat == "adoption" for _u, cat in result)

    def test_fetch_animal_list_virtual_urls_are_unique(self, fixture_html):
        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        html = fixture_html("douai_pref_tochigi_puppy__puppy_page")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))
        assert all(u.startswith(adapter.site_config.list_url + "#animal=") for u in urls)

    def test_fetch_animal_list_excludes_already_matched_kittens(self, fixture_html):
        """「飼い主さん決まりました」の個体は募集対象外のため除外される (3頭中1頭のみ)"""
        adapter = DouaiPrefTochigiPuppyAdapter(_kitten_site())
        html = fixture_html("douai_pref_tochigi_puppy__kitten_page")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert len(result) == 1

    def test_fetch_animal_list_zero_is_true_empty(self):
        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        empty_html = "<html><body><p>現在、譲渡対象の子犬はいません。</p></body></html>"
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


class TestDouaiPrefTochigiPuppyDetailExtraction:
    def test_extract_pending_number_puppy_has_blank_management_number(
        self, fixture_html, assert_raw_animal
    ):
        """９月譲渡会予定の子犬 (番号：希望表配布時に付番します) は management_number 空文字"""
        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        html = fixture_html("douai_pref_tochigi_puppy__puppy_page")
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(
                f"{adapter.site_config.list_url}#animal=0", category="adoption"
            )
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            management_number="",
            category="adoption",
        )
        assert raw.sex in ("オス", "メス")

    def test_extract_available_puppy_has_real_management_number(self, fixture_html):
        """随時譲渡の子犬 (番号：24 等) は実際の管理番号を保持する"""
        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        html = fixture_html("douai_pref_tochigi_puppy__puppy_page")
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            records = [
                adapter.extract_animal_details(f"{adapter.site_config.list_url}#animal={i}")
                for i in range(5, 14)
            ]
        management_numbers = {r.management_number for r in records}
        assert management_numbers == {
            "24",
            "27",
            "30",
            "31",
            "33",
            "34",
            "37",
            "38",
            "39",
        }

    def test_extract_kitten_available_individual(self, fixture_html):
        adapter = DouaiPrefTochigiPuppyAdapter(_kitten_site())
        html = fixture_html("douai_pref_tochigi_puppy__kitten_page")
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(
                f"{adapter.site_config.list_url}#animal=0", category="adoption"
            )
        assert raw.species == "猫"
        assert raw.management_number == "３"
        assert raw.sex == "オス"
        assert len(raw.image_urls) == 1

    def test_extract_out_of_range_index_raises(self, fixture_html):
        from data_collector.adapters.municipality_adapter import ParsingError

        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        html = fixture_html("douai_pref_tochigi_puppy__puppy_page")
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(f"{adapter.site_config.list_url}#animal=999")


class TestDouaiPrefTochigiPuppyNormalize:
    def test_normalize_returns_animal_data(self, fixture_html):
        adapter = DouaiPrefTochigiPuppyAdapter(_puppy_site())
        html = fixture_html("douai_pref_tochigi_puppy__puppy_page")
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#animal=5")
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert normalized.species == "犬"
        assert normalized.prefecture == "栃木県"


class TestDouaiPrefTochigiPuppyRegistry:
    EXPECTED_SITE_NAMES = (
        "栃木県動物愛護指導センター（子犬譲渡）",
        "栃木県動物愛護指導センター（子猫譲渡）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_adapter(self, site_name):
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is DouaiPrefTochigiPuppyAdapter, (
            f"{site_name} が DouaiPrefTochigiPuppyAdapter に紐付いていません: {cls}"
        )
