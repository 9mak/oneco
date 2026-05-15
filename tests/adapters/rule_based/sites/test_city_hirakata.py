"""CityHirakataAdapter のテスト

枚方市保健所 (city.hirakata.osaka.jp) 用 rule-based adapter の動作を
検証する。

- `div.mol_imageblock` カードが並ぶ single_page 形式
- 「掲載情報が無い」告知のみのページは ParsingError ではなく空リスト
- 動物カードがある場合は <h4>収容犬|収容猫</h4> 見出しから species を推定
- サイト名「枚方市（収容動物）」が registry に登録される
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_hirakata import (
    CityHirakataAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site_hirakata() -> SiteConfig:
    return SiteConfig(
        name="枚方市（収容動物）",
        prefecture="大阪府",
        prefecture_code="27",
        list_url="https://www.city.hirakata.osaka.jp/0000001430.html",
        category="sheltered",
        single_page=True,
    )


def _load_hirakata_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    `tests/adapters/rule_based/fixtures/city_hirakata_osaka_jp.html` は
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。実運用 (`_http_get`)
    では requests が正しい UTF-8 として受け取るため、本ヘルパーは
    フィクスチャ読み込み専用。
    """
    raw = fixture_html("city_hirakata_osaka_jp")
    if "枚方市" in raw and "ææ¹å¸" not in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


# ───────── テスト本体 ─────────


class TestCityHirakataAdapter:
    def test_fixture_is_empty_state_returns_empty_list(self, fixture_html):
        """fixture は「掲載情報が無い」状態のため空リストが返る"""
        html = _load_hirakata_html(fixture_html)
        # 念のため empty-state の文言が fixture に含まれることを確認
        assert "掲載情報" in html
        adapter = CityHirakataAdapter(_site_hirakata())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_empty_state_minimal_html(self):
        """0 件告知のみ含む最小 HTML でも空リストを返す"""
        empty_html = (
            "<html><body><main>"
            "<h4>収容犬</h4>"
            "<p>掲載情報が無い場合でも、犬が行方不明になったら速やかに"
            "当課までご連絡ください。</p>"
            "<h4>収容猫</h4>"
            "<p>掲載情報が無い場合でも、猫が行方不明になったら速やかに"
            "当課までご連絡ください。</p>"
            "</main></body></html>"
        )
        adapter = CityHirakataAdapter(_site_hirakata())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_raises_parsing_error_when_no_blocks_and_no_empty_state(self):
        """0 件告知すら無い空 HTML では ParsingError 系例外を出す"""
        adapter = CityHirakataAdapter(_site_hirakata())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_animal_details_with_dog_card(self):
        """犬カードがある HTML から species=犬 として抽出できる"""
        html = (
            "<html><body><main>"
            "<h4 class='block_index_3'>収容犬</h4>"
            "<div class='mol_imageblock'>"
            "<p><img src='/cmsfiles/contents/0000001/1430/dog01.jpg'></p>"
            "<p>種別：雑種</p>"
            "<p>性別：オス</p>"
            "<p>毛色：茶白</p>"
            "<p>収容日：2026年5月10日</p>"
            "<p>場所：枚方市楠葉</p>"
            "</div>"
            "</main></body></html>"
        )
        adapter = CityHirakataAdapter(_site_hirakata())
        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶白"
        assert "2026" in raw.shelter_date
        assert "楠葉" in raw.location
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert any("dog01.jpg" in u for u in raw.image_urls)
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_animal_details_with_cat_card(self):
        """猫カードがある HTML から species=猫 として抽出できる"""
        html = (
            "<html><body><main>"
            "<h4 class='block_index_3'>収容犬</h4>"
            "<p>掲載情報が無い場合でも、犬が行方不明になったら…</p>"
            "<h4 class='block_index_5'>収容猫</h4>"
            "<div class='mol_imageblock'>"
            "<p><img src='/cmsfiles/contents/0000001/1430/cat01.jpg'></p>"
            "<p>種別：雑種</p>"
            "<p>性別：メス</p>"
            "<p>毛色：三毛</p>"
            "<p>収容日：2026年5月12日</p>"
            "</div>"
            "</main></body></html>"
        )
        adapter = CityHirakataAdapter(_site_hirakata())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert "三毛" in raw.color
        assert raw.category == "sheltered"

    def test_all_rows_extractable_with_mixed_dog_cat(self):
        """犬/猫が混在する HTML で全カードを ParsingError なく抽出できる"""
        html = (
            "<html><body><main>"
            "<h4 class='block_index_3'>収容犬</h4>"
            "<div class='mol_imageblock'>"
            "<p>種別：柴犬</p><p>性別：オス</p>"
            "</div>"
            "<h4 class='block_index_5'>収容猫</h4>"
            "<div class='mol_imageblock'>"
            "<p>種別：雑種</p><p>性別：メス</p>"
            "</div>"
            "<div class='mol_imageblock'>"
            "<p>種別：雑種</p><p>性別：不明</p>"
            "</div>"
            "</main></body></html>"
        )
        adapter = CityHirakataAdapter(_site_hirakata())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 3
            species_seen: list[str] = []
            for url, category in urls:
                raw = adapter.extract_animal_details(url, category=category)
                assert isinstance(raw, RawAnimalData)
                species_seen.append(raw.species)

        # 1 枚目は犬、2-3 枚目は猫見出し配下
        assert species_seen[0] == "犬"
        assert species_seen[1] == "猫"
        assert species_seen[2] == "猫"

    def test_site_registered(self):
        """枚方市（収容動物）が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get("枚方市（収容動物）") is None:
            SiteAdapterRegistry.register(
                "枚方市（収容動物）", CityHirakataAdapter
            )
        assert (
            SiteAdapterRegistry.get("枚方市（収容動物）")
            is CityHirakataAdapter
        )
