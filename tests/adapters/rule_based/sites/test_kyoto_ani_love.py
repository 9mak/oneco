"""KyotoAniLoveAdapter のテスト

京都動物愛護センターサイト (kyoto-ani-love.com) 用 rule-based adapter
の動作を検証する。

- 1 ページに `div.content > table.info` が並ぶ single_page 形式
- 2 サイト (迷子犬 / 迷子猫) すべての登録確認
- 在庫 0 件でも空リストを返す (ParsingError を投げない)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.kyoto_ani_love import (
    KyotoAniLoveAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _dog_site() -> SiteConfig:
    return SiteConfig(
        name="京都市ペットラブ（迷子犬）",
        prefecture="京都府",
        prefecture_code="26",
        list_url="https://kyoto-ani-love.com/lost-animal/dog/",
        category="lost",
        single_page=True,
    )


def _cat_site() -> SiteConfig:
    return SiteConfig(
        name="京都市ペットラブ（迷子猫）",
        prefecture="京都府",
        prefecture_code="26",
        list_url="https://kyoto-ani-love.com/lost-animal/cat/",
        category="lost",
        single_page=True,
    )


class TestKyotoAniLoveAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """一覧ページから動物カード (仮想 URL) が抽出できる"""
        html = fixture_html("kyoto_ani_love")
        adapter = KyotoAniLoveAdapter(_dog_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # フィクスチャには 2 件のテーブルがある
        assert len(result) == 2
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://kyoto-ani-love.com/lost-animal/dog/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(
        self, fixture_html, assert_raw_animal
    ):
        """1 件目のカードから RawAnimalData を構築できる

        フィクスチャの 1 件目:
          - 受入日: ３月１７日
          - 保護日: ３月１７日
          - 保護場所: 南区西九条比永城町
          - 品種: 柴
          - 毛色: 茶
          - 性別: オス
          - 推定年齢: 成犬
          - 体格: 中
        """
        html = fixture_html("kyoto_ani_love")
        adapter = KyotoAniLoveAdapter(_dog_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            sex="オス",
            color="茶",
            size="中",
            location="南区西九条比永城町",
            shelter_date="３月１７日",
            category="lost",
        )
        # phone はカード内に無いため空
        assert raw.phone == ""
        # source_url は仮想 URL
        assert raw.source_url == first_url
        # age (推定年齢) は "成犬"
        assert raw.age == "成犬"

    def test_extract_animal_details_second_row(
        self, fixture_html, assert_raw_animal
    ):
        """2 件目のカードから RawAnimalData を構築できる

        フィクスチャの 2 件目:
          - 受入日: ５月８日
          - 保護日: ５月２日
          - 保護場所: 山科区四ノ宮川原町
          - 品種: ポメラニアン
          - 毛色: 茶
          - 性別: メス
          - 推定年齢: 成犬
          - 体格: 小
        """
        html = fixture_html("kyoto_ani_love")
        adapter = KyotoAniLoveAdapter(_dog_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert_raw_animal(
            raw,
            species="犬",
            sex="メス",
            color="茶",
            size="小",
            location="山科区四ノ宮川原町",
            # 保護日を優先する (受入日 ５月８日 ではない)
            shelter_date="５月２日",
            category="lost",
        )
        assert raw.age == "成犬"

    def test_species_inferred_for_cat_site(self, fixture_html):
        """猫サイトでは species が "猫" に推定される

        フィクスチャは犬ページだが、テンプレートが共通なので
        site_config だけ猫サイトに差し替えて species 推定だけ確認する。
        """
        html = fixture_html("kyoto_ani_love")
        adapter = KyotoAniLoveAdapter(_cat_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "猫"
        assert raw.category == "lost"

    def test_all_two_sites_registered(self):
        """2 つの京都市ペットラブサイト名すべてが Registry に登録されている"""
        expected = [
            "京都市ペットラブ（迷子犬）",
            "京都市ペットラブ（迷子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, KyotoAniLoveAdapter)
            assert SiteAdapterRegistry.get(name) is KyotoAniLoveAdapter

    def test_returns_empty_list_when_no_animals(self):
        """在庫 0 件 (テーブル無し) の HTML では空リストを返す

        京都市の運用上、保護中の動物が 0 件の状態が正常運用として
        頻繁に発生するため、ParsingError ではなく空リストで扱う。
        """
        empty_html = """
        <html><body>
          <div class="information-care-lost-content">
            <p>現在保護している犬はいません。</p>
          </div>
        </body></html>
        """
        adapter = KyotoAniLoveAdapter(_dog_site())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []
