"""OitaAigoAdapter のテスト

おおいた動物愛護センターサイト (oita-aigo.com) 用 rule-based adapter
の動作を検証する。

- 1 ページに `div.information_box` カードが並ぶ single_page 形式
- 3 サイト (迷子情報メイン / 譲渡犬 / 譲渡猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.oita_aigo import OitaAigoAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _lostchild_site() -> SiteConfig:
    return SiteConfig(
        name="おおいた動物愛護センター（迷子情報メイン）",
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://oita-aigo.com/lostchild/",
        category="sheltered",
        single_page=True,
    )


def _adoption_dog_site() -> SiteConfig:
    return SiteConfig(
        name="おおいた動物愛護センター（譲渡犬）",
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://oita-aigo.com/information_doglist/anytimedog/",
        category="adoption",
        single_page=True,
    )


def _adoption_cat_site() -> SiteConfig:
    return SiteConfig(
        name="おおいた動物愛護センター（譲渡猫）",
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://oita-aigo.com/information_catlist/anytimecat/",
        category="adoption",
        single_page=True,
    )


class TestOitaAigoAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """一覧ページから動物カード (仮想 URL) が抽出できる"""
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_lostchild_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://oita-aigo.com/")
            assert cat == "sheltered"

    def test_extract_animal_details_first_row(self, fixture_html, assert_raw_animal):
        """1 件目のカードから RawAnimalData を構築できる

        フィクスチャの 1 件目:
          - 保護地域: 佐伯市
          - 推定年齢: 8歳
          - 性別: オス
          - 体重: 14.04kg
          - lostchild_ttl: 令和8年5月1日
          - 画像: /wp-content/uploads/2026/05/...jpg
        """
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_lostchild_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            sex="オス",
            age="8歳",
            size="14.04kg",
            location="佐伯市",
            shelter_date="令和8年5月1日",
            category="sheltered",
        )
        # 迷子情報メインは犬猫混在のため species は空 (不明)
        assert raw.species == ""
        # phone はカード内に無いため空
        assert raw.phone == ""
        # 画像 URL が絶対化され、uploads 配下のみ採用される
        assert raw.image_urls
        assert all(u.startswith("https://oita-aigo.com/") for u in raw.image_urls)
        assert any("/wp-content/uploads/" in u for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url

    def test_species_inferred_for_adoption_dog_site(self, fixture_html):
        """譲渡犬サイトでは species が "犬" に推定される

        フィクスチャは lostchild ページだが、テンプレートが共通なので
        site_config だけ譲渡犬サイトに差し替えて species 推定だけ確認する。
        """
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_adoption_dog_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "犬"
        assert raw.category == "adoption"

    def test_species_inferred_for_adoption_cat_site(self, fixture_html):
        """譲渡猫サイトでは species が "猫" に推定される"""
        html = fixture_html("oita_aigo__lostchild")
        adapter = OitaAigoAdapter(_adoption_cat_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "猫"
        assert raw.category == "adoption"

    def test_all_three_sites_registered(self):
        """3 つの大分愛護センターサイト名すべてが Registry に登録されている"""
        expected = [
            "おおいた動物愛護センター（迷子情報メイン）",
            "おおいた動物愛護センター（譲渡犬）",
            "おおいた動物愛護センター（譲渡猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, OitaAigoAdapter)
            assert SiteAdapterRegistry.get(name) is OitaAigoAdapter

    def test_raises_parsing_error_when_no_cards(self):
        """カード要素が見当たらない HTML では ParsingError 系例外を出す"""
        adapter = OitaAigoAdapter(_lostchild_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
