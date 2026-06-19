"""CityKoshigayaKojinAdapter のテスト

越谷市 個人保護犬猫 (hogo_kojin.html) 専用 adapter の検証。

検証観点:
- セクション h2 「犬の情報」「猫の情報」配下の h3 を 1 動物として扱う
- 0 件正常終了（セクション h2 はあるが h3 が無い）
- adapter 破損検出（tmp_honbun も SPECIES_SECTIONS も無い HTML で ParsingError）
- p 「ラベル：値」形式から RawAnimalData を構築
- species は h2 から確定（li 値ではなく h2 スコープ）
- Registry に「越谷市（個人保護犬猫）」が登録されている
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_koshigaya_kojin import (
    CityKoshigayaKojinAdapter,
)
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="越谷市（個人保護犬猫）",
        prefecture="埼玉県",
        prefecture_code="11",
        list_url=(
            "https://www.city.koshigaya.saitama.jp/"
            "kurashi_shisei/fukushi/hokenjo/pet/hogo/hogo_kojin.html"
        ),
        category="sheltered",
        single_page=True,
    )


class TestCityKoshigayaKojinAdapter:
    def test_one_cat_with_p_label_value_fields(self):
        """猫セクションに R8-001 が 1 頭、p 「ラベル：値」から抽出"""
        html = """
        <html><body>
        <div id="tmp_honbun">
          <h2>犬の情報</h2>
            <p>現在、情報はありません。</p>
          <h2>猫の情報</h2>
            <h3>R8-001</h3>
              <p>発見場所：越谷市大沢４丁目付近</p>
              <p>発見時期：おおよそ２０２５年８月ごろ</p>
              <p>種類：スコティッシュフォールド</p>
              <p>毛色：キジトラ</p>
              <p>特徴：ピンク色の首輪あり</p>
        </div>
        </body></html>
        """
        adapter = CityKoshigayaKojinAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        assert mock_get.call_count == 1, "HTML はキャッシュされる"
        assert len(urls) == 1
        assert raw.species == "猫"
        # 「種類」は species(h2セクションで猫確定)ではなく猫種=breed として保持(回帰防止)
        assert raw.breed == "スコティッシュフォールド"
        assert adapter.normalize(raw).breed == "スコティッシュフォールド"
        assert "越谷市大沢" in raw.location
        assert "2025" in raw.shelter_date or "２０２５" in raw.shelter_date
        assert "キジトラ" in raw.color
        assert raw.category == "sheltered"
        assert raw.source_url == urls[0][0]

    def test_both_sections_empty_returns_empty_list(self):
        """犬・猫セクションどちらも h3 が無い → 0 件正常終了"""
        html = """
        <html><body>
        <div id="tmp_honbun">
          <h2>犬の情報</h2>
            <p>現在、情報はありません。</p>
          <h2>猫の情報</h2>
            <p>現在、情報はありません。</p>
        </div>
        </body></html>
        """
        adapter = CityKoshigayaKojinAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
        assert urls == []

    def test_dog_section_with_h3(self):
        """犬セクションに h3 があれば species=犬 で抽出される"""
        html = """
        <html><body>
        <div id="tmp_honbun">
          <h2>犬の情報</h2>
            <h3>R8-D001</h3>
              <p>発見場所：越谷市東町</p>
              <p>毛色：茶</p>
              <p>性別：オス</p>
          <h2>猫の情報</h2>
            <p>現在、情報はありません。</p>
        </div>
        </body></html>
        """
        adapter = CityKoshigayaKojinAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert "越谷市東町" in raw.location

    def test_no_species_sections_raises_parsing_error(self):
        """「犬の情報」「猫の情報」 h2 がどちらも無い → ParsingError"""
        html = """
        <html><body>
        <div id="tmp_honbun">
          <h2>注意事項</h2>
            <p>本ページは...</p>
          <h2>お問い合わせ</h2>
            <p>...</p>
        </div>
        </body></html>
        """
        adapter = CityKoshigayaKojinAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_no_tmp_honbun_raises_parsing_error(self):
        """`div#tmp_honbun` 自体が無い HTML は ParsingError"""
        adapter = CityKoshigayaKojinAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><div>x</div></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_h3_outside_species_sections_is_ignored(self):
        """「犬の情報」「猫の情報」以外のセクションの h3 は動物として拾わない

        例: 「注意事項」「マイクロチップについて」セクションには
        「参考：越谷警察署」「環境省ホームページ」等の h3 があるが、
        これらは動物情報ではないので拾わない。
        """
        html = """
        <html><body>
        <div id="tmp_honbun">
          <h2>注意事項</h2>
            <h3>参考：越谷警察署</h3>
              <p>電話：048-964-0110</p>
          <h2>犬の情報</h2>
            <p>現在、情報はありません。</p>
          <h2>猫の情報</h2>
            <h3>R8-001</h3>
              <p>発見場所：越谷市大沢４丁目</p>
              <p>毛色：キジトラ</p>
          <h2>参考：マイクロチップについて</h2>
            <h3>環境省ホームページ</h3>
              <p>マイクロチップとは...</p>
        </div>
        </body></html>
        """
        adapter = CityKoshigayaKojinAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
        # 注意事項/マイクロチップ配下の h3 はカウントしない、猫 1 件のみ
        assert len(urls) == 1


class TestCityKoshigayaKojinRegistry:
    def test_site_registered(self):
        assert SiteAdapterRegistry.get("越谷市（個人保護犬猫）") is CityKoshigayaKojinAdapter, (
            "「越谷市（個人保護犬猫）」が CityKoshigayaKojinAdapter にマップされている"
        )

    def test_existing_koshigaya_dog_cat_still_use_table_adapter(self):
        """保護犬/保護猫は引き続き CityKoshigayaAdapter (table 形式) を使う"""
        from data_collector.adapters.rule_based.sites.city_koshigaya import (
            CityKoshigayaAdapter,
        )

        for name in ("越谷市（保護犬）", "越谷市（保護猫）"):
            assert SiteAdapterRegistry.get(name) is CityKoshigayaAdapter, (
                f"{name} は CityKoshigayaAdapter にマップされている"
            )
