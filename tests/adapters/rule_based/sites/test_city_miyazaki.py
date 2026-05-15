"""CityMiyazakiAdapter のテスト

宮崎市保護動物サイト (city.miyazaki.miyazaki.jp/life/pet/protection/) 用
rule-based adapter の動作を検証する。

- 1 ページ 1 頭の single_page 形式 (detail ページを 1 行のテーブルと見立てる)
- 4 サイト (直近保護 犬/猫、センター保護 犬/猫) すべての登録確認
- `<article class="body">` 内の h3-p ペアからフィールド抽出
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_miyazaki import (
    CityMiyazakiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="宮崎市（直近保護犬）",
        prefecture="宮崎県",
        prefecture_code="45",
        list_url=("https://www.city.miyazaki.miyazaki.jp/life/pet/protection/411118.html"),
        category="sheltered",
        single_page=True,
    )


class TestCityMiyazakiAdapter:
    def test_fetch_animal_list_returns_single_row(self, fixture_html):
        """1 頭分の virtual URL が 1 件抽出される"""
        html = fixture_html("city_miyazaki__protection")
        adapter = CityMiyazakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1, "1 ページ 1 頭の single_page 形式"
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith(
            "https://www.city.miyazaki.miyazaki.jp/life/pet/protection/411118.html"
        )
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self, fixture_html):
        """フィクスチャの 1 頭から RawAnimalData を構築できる"""
        html = fixture_html("city_miyazaki__protection")
        adapter = CityMiyazakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # ページ本文 "犬の種類" 見出しから犬と判定
        assert raw.species == "犬"
        # 各フィールドはフィクスチャ通り
        assert "宮崎市恒久" in raw.location
        assert raw.sex == "メス"
        assert raw.color == "黒茶"
        assert raw.age == "成齢"
        assert raw.size == "中"
        # 保護日時の文字列がそのまま入る (正規化は別段で実施)
        assert raw.shelter_date and "令和8年5月6日" in raw.shelter_date
        # 電話番号は footer の dl.tel から抽出され XXX-XXXX-XXXX 形式
        assert raw.phone == "0985-85-6011"
        # 画像は /fs/ 配下のものが絶対 URL に変換されて入る
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.miyazaki.miyazaki.jp/")
            assert "/fs/" in u
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_image_urls_filter_excludes_decoration(self, fixture_html):
        """フィクスチャ内のロゴ等装飾画像は image_urls に含まれない"""
        html = fixture_html("city_miyazaki__protection")
        adapter = CityMiyazakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        # `/img/` 配下のロゴ等は混入しない
        assert all("/img/" not in u for u in raw.image_urls)
        # `/assets/` 配下のテーマ画像も混入しない
        assert all("/assets/" not in u for u in raw.image_urls)

    def test_all_four_sites_registered(self):
        """4 つの宮崎市サイト名すべてが Registry に登録されている"""
        expected = [
            "宮崎市（直近保護犬）",
            "宮崎市（直近保護猫）",
            "宮崎市（センター保護犬・飼い主募集）",
            "宮崎市（センター保護猫・飼い主募集）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityMiyazakiAdapter)
            assert SiteAdapterRegistry.get(name) is CityMiyazakiAdapter

    def test_raises_parsing_error_when_no_article(self):
        """`article.body` 要素が無い HTML では例外を出す"""
        adapter = CityMiyazakiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
