"""PrefGunmaAdapter のテスト

群馬県動物愛護センターサイト (pref.gunma.jp) 用 rule-based adapter の
動作を検証する。

2026-07 のサイト構造変更で、一覧ページはインラインの動物テーブルから
「管理番号：NN-NNN（場所）」の詳細ページリンク並びに変わった。
本テストは新形式の実ページフィクスチャで検証する:

- 一覧ページ (`pref_gunma_list_tobu.html`): 詳細ページ URL の抽出
- 詳細ページ (`pref_gunma_detail.html`): ラベル/値テーブルからの全フィールド抽出
  + `normalize()` 戻り値 (AnimalData) での end-to-end 検証 (サイレントドロップ防止)
- 0 件告知ページ (`pref_gunma_empty_new.html`): 空リストを返す
- 同一テンプレート上の 3 サイト (本所 保護犬/猫、東部支所 保護犬) の登録確認
- リンクも empty state も無い無関係 HTML は ParsingError
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_gunma import (
    PrefGunmaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_LIST_URL_TOBU = "https://www.pref.gunma.jp/page/179441.html"
_DETAIL_URL = "https://www.pref.gunma.jp/page/766184.html"


def _site(
    name: str = "群馬県動物愛護センター東部支所（保護犬）",
    list_url: str = _LIST_URL_TOBU,
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="群馬県",
        prefecture_code="10",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _patch_http(adapter, fixture_html):
    """list_url / 詳細 URL に応じたフィクスチャを返す _http_get モック"""
    pages = {
        _LIST_URL_TOBU: fixture_html("pref_gunma_list_tobu"),
        _DETAIL_URL: fixture_html("pref_gunma_detail"),
    }

    def _get(url, *args, **kwargs):
        if url not in pages:
            raise AssertionError(f"unexpected URL fetched: {url}")
        return pages[url]

    return patch.object(adapter, "_http_get", side_effect=_get)


class TestFetchAnimalList:
    def test_returns_detail_page_urls(self, fixture_html):
        """一覧ページの「管理番号：…」リンクから詳細ページ URL を抽出できる"""
        adapter = PrefGunmaAdapter(_site())

        with _patch_http(adapter, fixture_html):
            result = adapter.fetch_animal_list()

        assert result == [(_DETAIL_URL, "sheltered")]

    def test_returns_empty_for_no_animals_page(self, fixture_html):
        """「現在、保管期間中の負傷猫はいません」告知ページでは空リストが返る"""
        adapter = PrefGunmaAdapter(
            _site(
                name="群馬県動物愛護センター（保護猫）",
                list_url="https://www.pref.gunma.jp/page/167523.html",
            )
        )

        with patch.object(adapter, "_http_get", return_value=fixture_html("pref_gunma_empty_new")):
            result = adapter.fetch_animal_list()

        assert result == [], f"empty state ページでは空配列が返るはず: got {result!r}"

    def test_returns_empty_for_old_format_no_animals_page(self, fixture_html):
        """旧形式の 0 件告知ページ (地域別「おりません」) でも空リストが返る"""
        adapter = PrefGunmaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=fixture_html("pref_gunma")):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_caches_list_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        adapter = PrefGunmaAdapter(_site())

        with patch.object(
            adapter, "_http_get", return_value=fixture_html("pref_gunma_list_tobu")
        ) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1

    def test_raises_parsing_error_for_unrelated_html(self):
        """リンクも empty state テキストも無い HTML では ParsingError"""
        adapter = PrefGunmaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><p>無関係なページ</p></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()


class TestExtractAnimalDetails:
    def test_extracts_all_fields_from_detail_page(self, fixture_html):
        """詳細ページのラベル/値テーブルから全フィールドを抽出できる

        フィクスチャ収録の個体 (管理番号 26-049):
        - 種類: 柴犬 (= breed)  性別: オス  推定年齢: 10才位
        - 毛色: 薄茶  体格: 中型  収容日: 2026年7月8日  収容場所: 館林市岡野町
        - 首輪: 赤色 (description に保持)  写真: 2 枚 (バナー広告は除外)
        """
        adapter = PrefGunmaAdapter(_site())

        with _patch_http(adapter, fixture_html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.breed == "柴犬"
        assert raw.management_number == "26-049"
        assert raw.sex == "オス"
        assert raw.age == "10才位"
        assert raw.color == "薄茶"
        assert raw.size == "中型"
        assert raw.shelter_date == "2026年7月8日"
        assert raw.location == "館林市岡野町"
        assert "首輪" in raw.description and "赤色" in raw.description
        # 東部出張所の Tel を抽出 (県庁代表 027-223-1111 を拾わない)
        assert raw.phone == "0276-55-0731"
        assert raw.source_url == _DETAIL_URL
        # 動物写真 2 枚のみ。/uploaded/banner/ 配下の広告は除外
        assert len(raw.image_urls) == 2
        assert all(
            u.startswith("https://www.pref.gunma.jp/uploaded/image/") for u in raw.image_urls
        )

    def test_full_scraping_flow_normalize(self, fixture_html):
        """end-to-end: normalize() 戻り値 AnimalData まで個体識別フィールドが届く

        adapter 単体で raw.breed を検証するだけでは normalize 側での
        サイレントドロップ (PR #171/#173/#176/#177/#180 の再発) を検出
        できないため、AnimalData でアサーションする。
        """
        adapter = PrefGunmaAdapter(_site())

        with _patch_http(adapter, fixture_html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])
            animal = adapter.normalize(raw)

        assert animal.species == "犬"
        assert animal.breed == "柴犬"
        assert animal.management_number == "26-049"
        assert animal.sex == "男の子"
        assert animal.age_months == 120  # 10才位 → 120ヶ月
        assert animal.color == "薄茶"
        assert animal.size == "中型"
        assert animal.prefecture == "群馬県"
        assert animal.location == "館林市岡野町"
        assert animal.description and "赤色" in animal.description
        assert str(animal.shelter_date) == "2026-07-08"
        assert len(animal.image_urls) == 2


class TestHelpers:
    def test_infer_species_from_site_name_dog(self):
        assert (
            PrefGunmaAdapter._infer_species_from_site_name("群馬県動物愛護センター（保護犬）")
            == "犬"
        )
        assert (
            PrefGunmaAdapter._infer_species_from_site_name(
                "群馬県動物愛護センター東部支所（保護犬）"
            )
            == "犬"
        )

    def test_infer_species_from_site_name_cat(self):
        assert (
            PrefGunmaAdapter._infer_species_from_site_name("群馬県動物愛護センター（保護猫）")
            == "猫"
        )

    def test_infer_species_from_site_name_unknown(self):
        assert (
            PrefGunmaAdapter._infer_species_from_site_name("群馬県動物愛護センター（その他）") == ""
        )

    def test_all_three_sites_registered(self):
        """3 つの群馬県サイト名すべてが Registry に登録されている"""
        expected = [
            "群馬県動物愛護センター（保護犬）",
            "群馬県動物愛護センター東部支所（保護犬）",
            "群馬県動物愛護センター（保護猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefGunmaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefGunmaAdapter
