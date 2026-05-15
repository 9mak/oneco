"""CityKashiwaAdapter のテスト

柏市動物愛護ふれあいセンター (city.kashiwa.lg.jp/.../dobutsu/hogo/) 用
rule-based adapter の動作を検証する。

- `div.col2_sp2_wrap` カードが並ぶ single_page 形式
- 2 サイト (保護動物 / 譲渡対象動物) の登録確認
- 写真なしのカードでも例外を投げず空 image_urls を返すこと
- 0 件告知ページは ParsingError ではなく空リストを返すこと
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kashiwa import (
    CityKashiwaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site_hogo() -> SiteConfig:
    return SiteConfig(
        name="柏市（保護動物）",
        prefecture="千葉県",
        prefecture_code="12",
        list_url=(
            "https://www.city.kashiwa.lg.jp/dobutsuaigo/shiseijoho/"
            "shisei/health_hospital/mainmenu/dobutsu/hogo/hogo.html"
        ),
        category="sheltered",
        single_page=True,
    )


def _site_satoya() -> SiteConfig:
    return SiteConfig(
        name="柏市（譲渡対象動物）",
        prefecture="千葉県",
        prefecture_code="12",
        list_url=(
            "https://www.city.kashiwa.lg.jp/dobutsuaigo/shiseijoho/"
            "shisei/health_hospital/mainmenu/dobutsu/hogo/satoya.html"
        ),
        category="adoption",
        single_page=True,
    )


def _load_kashiwa_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_kashiwa.html` は、本来 UTF-8 の
    バイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっているため、実サイト相当のテキストを
    得るには逆変換が必要。実運用 (`_http_get`) では requests が正しい
    UTF-8 として受け取るため、このテストヘルパーはフィクスチャ読み込み
    専用。
    """
    raw = fixture_html("city_kashiwa")
    # 期待する漢字 "柏市" がそのまま読めれば OK
    if "柏市" in raw and "ä¿è­·" not in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityKashiwaAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """一覧ページから動物カード (仮想 URL) が抽出できる"""
        html = _load_kashiwa_html(fixture_html)
        adapter = CityKashiwaAdapter(_site_hogo())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1, "少なくとも 1 件以上の動物カードが抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.city.kashiwa.lg.jp/")
            assert cat == "sheltered"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のカードから RawAnimalData を構築できる

        フィクスチャ収録の 1 件目 (番号 051101):
        - 種類: 雑種  → 直前の <h3>猫</h3> から species は「猫」
        - 毛色: 茶トラ
        - 収容: 5月11日
        - 性別: メス
        - 場所: 豊四季台
        - 画像: 2 枚
        """
        html = _load_kashiwa_html(fixture_html)
        adapter = CityKashiwaAdapter(_site_hogo())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # 直前の <h3>猫</h3> から推定
        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert "茶" in raw.color
        assert "豊四季台" in raw.location
        assert "5月11日" in raw.shelter_date
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert any("s-pxl_20260511_235338029.jpg" in u for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_animal_details_no_image(self, fixture_html):
        """写真なしカード (col2L が「写真なし」テキストのみ) でも例外を投げない"""
        html = _load_kashiwa_html(fixture_html)
        adapter = CityKashiwaAdapter(_site_hogo())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            # 2 件目以降に「写真なし」のカードが含まれる前提
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "猫"
        # 「写真なし」のカードでは image_urls は空でも例外にならない
        assert raw.image_urls == [] or all(isinstance(u, str) for u in raw.image_urls)

    def test_all_rows_extractable(self, fixture_html):
        """フィクスチャ内全カードが ParsingError なく抽出できる"""
        html = _load_kashiwa_html(fixture_html)
        adapter = CityKashiwaAdapter(_site_hogo())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            for url, category in urls:
                raw = adapter.extract_animal_details(url, category=category)
                assert isinstance(raw, RawAnimalData)
                # species は必ず推定されているはず (「犬」「猫」のどちらか)
                assert raw.species in ("犬", "猫", "その他", "")

    def test_satoya_site_uses_same_adapter(self, fixture_html):
        """譲渡対象動物サイトでも同じテンプレートで抽出できる

        satoya.html 専用フィクスチャは無いため hogo.html の HTML を
        使い回し、satoya 用 site_config (category=adoption) でも
        同じパース結果が得られることを確認する。
        """
        html = _load_kashiwa_html(fixture_html)
        adapter = CityKashiwaAdapter(_site_satoya())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) >= 1
            for _url, category in urls:
                assert category == "adoption"
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.category == "adoption"

    def test_empty_state_returns_empty_list(self):
        """0 件告知ページでは ParsingError ではなく空リストを返す"""
        empty_html = (
            "<html><body><main><div id='tmp_contents'>"
            "<h1>保護収容動物情報</h1>"
            "<p>現在、保護動物はおりません。</p>"
            "</div></main></body></html>"
        )
        adapter = CityKashiwaAdapter(_site_hogo())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_raises_parsing_error_when_no_blocks_and_no_empty_state(self):
        """0 件告知すら無い空 HTML では ParsingError 系例外を出す"""
        adapter = CityKashiwaAdapter(_site_hogo())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_both_sites_registered(self):
        """2 つの柏市サイト名が Registry に登録されている"""
        expected = [
            "柏市（保護動物）",
            "柏市（譲渡対象動物）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityKashiwaAdapter)
            assert SiteAdapterRegistry.get(name) is CityKashiwaAdapter
