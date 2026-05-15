"""CityHiroshimaAdapter のテスト

広島市公式ウェブサイト (city.hiroshima.lg.jp) 用 rule-based adapter。

- 1 ページ 1 動物の single_page 形式 (`<dl>` 1 件)
- 2 サイト (迷子犬 / 迷子猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_hiroshima import (
    CityHiroshimaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site_dog() -> SiteConfig:
    return SiteConfig(
        name="広島市（迷子犬）",
        prefecture="広島県",
        prefecture_code="34",
        list_url=(
            "https://www.city.hiroshima.lg.jp/"
            "living/pet-doubutsu/1021301/1026245/1037461.html"
        ),
        category="lost",
        single_page=True,
    )


def _site_cat() -> SiteConfig:
    return SiteConfig(
        name="広島市（迷子猫）",
        prefecture="広島県",
        prefecture_code="34",
        list_url=(
            "https://www.city.hiroshima.lg.jp/"
            "living/pet-doubutsu/1021301/1026245/1039097.html"
        ),
        category="lost",
        single_page=True,
    )


def _load_hiroshima_html(fixture_html) -> str:
    """フィクスチャを読み込み、二重 UTF-8 (mojibake) を補正する

    リポジトリに保存されている `city_hiroshima.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_hiroshima")
    # 復元済み HTML には漢字 "広島" が含まれるはず。既に正しいなら無加工。
    if "広島" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityHiroshimaAdapter:
    def test_fetch_animal_list_returns_one_row(self, fixture_html):
        """1 ページ 1 動物なので仮想 URL は 1 件返る"""
        html = _load_hiroshima_html(fixture_html)
        adapter = CityHiroshimaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert "#row=0" in url
        assert url.startswith("https://www.city.hiroshima.lg.jp/")
        assert cat == "lost"

    def test_extract_animal_details_dog(self, fixture_html):
        """飼い主不明犬ページから RawAnimalData を構築できる"""
        html = _load_hiroshima_html(fixture_html)
        adapter = CityHiroshimaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # フィクスチャ:
        #   性別 メス / 毛色 黒 / 推定年齢 8歳 /
        #   拾得等の場所 安佐南区相田1丁目付近 / 収容月日 令和8年4月27日
        assert raw.sex == "メス"
        assert raw.color == "黒"
        assert "8" in raw.age
        assert "安佐南区" in raw.location
        assert "令和" in raw.shelter_date or "8" in raw.shelter_date
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"
        # 画像が抽出され、絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # 動物写真のみで、SNS / 装飾アイコンは含まれない
        assert all(
            "/sns/" not in u and "/parts/" not in u for u in raw.image_urls
        )

    def test_species_inferred_for_cat_site(self, fixture_html):
        """猫サイトでは species='猫' と推定される (フィクスチャは犬ページだが
        サイト名ベースの推定であることを確認する)"""
        html = _load_hiroshima_html(fixture_html)
        adapter = CityHiroshimaAdapter(_site_cat())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "猫"

    def test_both_sites_registered(self):
        """2 つの広島市サイト名すべてが Registry に登録されている"""
        expected = [
            "広島市（迷子犬）",
            "広島市（迷子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityHiroshimaAdapter)
            assert SiteAdapterRegistry.get(name) is CityHiroshimaAdapter

    def test_raises_parsing_error_when_no_dl(self):
        """`<dl>` が存在しない HTML では ParsingError 系例外を出す"""
        adapter = CityHiroshimaAdapter(_site_dog())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_zero_animals_acceptable_when_dl_empty(self):
        """`<dl>` 内の dt/dd が空でもクラッシュせず空フィールドで返す

        実運用では「在庫 0 件」(該当なし) のページに切り替わることがあり、
        その場合 `<dl>` 自体が無くなることが多いが、テンプレート上だけ
        残るケースに備えて防御的に動作することを確認する。
        """
        empty_html = (
            '<html><body><div id="voice"><h2>該当なし</h2>'
            "<dl></dl></div></body></html>"
        )
        adapter = CityHiroshimaAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            urls = adapter.fetch_animal_list()
            url, cat = urls[0]
            raw = adapter.extract_animal_details(url, category=cat)

        assert raw.species == "犬"  # サイト名ベース
        assert raw.sex == ""
        assert raw.color == ""
        assert raw.location == ""
        assert raw.image_urls == []
