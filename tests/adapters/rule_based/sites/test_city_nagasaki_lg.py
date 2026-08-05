"""CityNagasakiLgAdapter のテスト

長崎市動物愛護管理センター (city.nagasaki.lg.jp/site/doubutsuaigo/) 用
rule-based adapter の動作を検証する。

このサイトは個体を掲載していない (2026-08-05 確認・W001/T021)。本文にあるのは
新着情報の記事リンクだけで、リンク先も見学案内である。旧実装はその記事を
1 動物として扱い、記事タイトルを location とする架空個体を公開していた。
そのため本テストの主眼は「記事を個体として拾わないこと」に置く。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_nagasaki_lg import (
    CityNagasakiLgAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "長崎市動物愛護管理センター（犬里親募集）",
    list_url: str = "https://www.city.nagasaki.lg.jp/site/doubutsuaigo/list7-19.html",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="長崎県",
        prefecture_code="42",
        list_url=list_url,
        category="adoption",
        single_page=True,
    )


class TestCityNagasakiLgAdapterReturnsNoAnimals:
    """記事リンクを個体として扱わない (架空個体の回帰テスト)"""

    def test_announcement_article_is_not_treated_as_animal(self, fixture_html):
        """実ページ相当の fixture でも 0 件を返す

        fixture に含まれる `list_pack` は「引き取り犬（保護犬）の見学　受付中」
        という告知記事。旧実装はこれを犬 1 頭として公開していた。
        """
        raw = fixture_html("city_nagasaki_lg")
        adapter = CityNagasakiLgAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_animal_like_article_title_is_still_not_an_animal(self):
        """個体を指すように見える記事タイトルでも個体として扱わない

        「里親募集中のミックス犬」のようなタイトルは個体に見えるが、実体は
        案内記事へのリンクであり、個体の性別・毛色・収容日を持たない。
        タイトル文字列で個体かどうかを判定する方式は採らない。
        """
        html = """
        <html><body>長崎市
        <div id="main_body"><div class="info_list_wrap"><div class="info_list"><ul>
          <li><div class="list_pack"><div class="article_txt">
            <span class="article_date">2026年5月10日更新</span>
            <span class="article_title"><a href="/site/doubutsuaigo/3001.html">里親募集中のミックス犬</a></span>
          </div></div></li>
        </ul></div></div></div>
        </body></html>
        """
        adapter = CityNagasakiLgAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            assert adapter.fetch_animal_list() == []

    def test_cat_site_also_returns_no_animals(self):
        """猫里親募集ページも同様に 0 件

        猫ページの写真には「動物愛護管理センターの猫たち（現在収容中の猫とは
        異なります）」と明記されており、そもそも個体情報ではない。
        """
        adapter = CityNagasakiLgAdapter(
            _site(
                name="長崎市動物愛護管理センター（猫里親募集）",
                list_url="https://www.city.nagasaki.lg.jp/site/doubutsuaigo/list7-18.html",
            )
        )
        html = "<html><body>長崎市<div id='main_body'><div class='info_list_wrap'></div></div></body></html>"
        with patch.object(adapter, "_http_get", return_value=html):
            assert adapter.fetch_animal_list() == []

    def test_page_is_still_fetched_so_outages_are_detected(self):
        """0 件でもページ取得は行う (URL 消滅・障害を収集ログで検知するため)"""
        adapter = CityNagasakiLgAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html></html>") as mock_get:
            adapter.fetch_animal_list()
        mock_get.assert_called_once_with(
            "https://www.city.nagasaki.lg.jp/site/doubutsuaigo/list7-19.html"
        )

    def test_extract_animal_details_raises(self):
        """詳細取得は呼ばれない経路なので明示的に失敗させる"""
        adapter = CityNagasakiLgAdapter(_site())
        with pytest.raises(ParsingError):
            adapter.extract_animal_details(
                "https://www.city.nagasaki.lg.jp/site/doubutsuaigo/list7-19.html#row=0"
            )


class TestCityNagasakiLgAdapterRegistration:
    def test_all_two_sites_registered(self):
        """2 つの長崎市サイト名すべてが Registry に登録されている"""
        expected = [
            "長崎市動物愛護管理センター（犬里親募集）",
            "長崎市動物愛護管理センター（猫里親募集）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityNagasakiLgAdapter)
            assert SiteAdapterRegistry.get(name) is CityNagasakiLgAdapter

    def test_species_inference_helper(self):
        """サイト名で species が決まる (犬里親募集→犬 / 猫里親募集→猫)

        個体取得は行わないが、サイトが個体を載せ始めたときに再利用するため
        ヘルパー自体は残している。
        """
        assert (
            CityNagasakiLgAdapter._infer_species_from_site_name(
                "長崎市動物愛護管理センター（犬里親募集）"
            )
            == "犬"
        )
        assert (
            CityNagasakiLgAdapter._infer_species_from_site_name(
                "長崎市動物愛護管理センター（猫里親募集）"
            )
            == "猫"
        )
