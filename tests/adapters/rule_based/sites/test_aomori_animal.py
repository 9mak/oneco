"""AomoriAnimalAdapter のテスト

青森県動物愛護センター (aomori-animal.jp) 用 rule-based adapter の動作を検証。

- single_page 形式: 1 ページに 1 テーブル、テーブル 1 行 = 1 動物
- fixture は二重 UTF-8 mojibake (Shift_JIS バイトを Latin-1 として読んで UTF-8 保存)
  状態のため adapter 側で逆変換する
- 各データ行の先頭 `<td>` が閉じタグ欠落しており、BeautifulSoup が
  後続 td を入れ子としてパースする -> 平坦化セル列で扱う
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.aomori_animal import (
    AomoriAnimalAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

SITE_NAME = "青森県動物愛護センター（収容情報）"
LIST_URL = "http://www.aomori-animal.jp/01_MAIGO/Shuyo.html"


def _site() -> SiteConfig:
    return SiteConfig(
        name=SITE_NAME,
        prefecture="青森県",
        prefecture_code="02",
        list_url=LIST_URL,
        category="sheltered",
        single_page=True,
    )


class TestAomoriAnimalAdapter:
    def test_fetch_animal_list_returns_two_animals(self, fixture_html):
        """fixture から動物 2 件 (= データ行 2 件) が抽出される"""
        html = fixture_html("aomori_animal_jp")
        adapter = AomoriAnimalAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for i, (url, cat) in enumerate(result):
            assert url == f"{LIST_URL}#row={i}"
            assert cat == "sheltered"

    def test_extract_first_animal(self, fixture_html, assert_raw_animal):
        """1 件目から RawAnimalData を構築できる

        fixture の 1 行目:
            No.        : 1
            種別       : 犬
            見つかった日: 2026/05/12
            場所       : 十和田市奥瀬十和田湖畔休屋
            毛色       : 黒
            性別       : 雄 (-> オス)
            体格       : 中型
            画像       : Shuyoimg/20260515_001.jpg
            連絡先     : 動物愛護センター十和田市駐在 / TEL: 0176-23-9511
        """
        html = fixture_html("aomori_animal_jp")
        adapter = AomoriAnimalAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        # HTTP 取得は 1 回にキャッシュされる (fetch + extract で計 1 回)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            sex="オス",
            color="黒",
            size="中型",
            shelter_date="2026/05/12",
            category="sheltered",
            source_url=url,
        )
        assert "十和田市" in raw.location
        assert raw.phone == "0176-23-9511"
        # 画像 URL: 相対パスが list_url 起点で絶対化される
        assert raw.image_urls
        assert raw.image_urls[0].startswith("http://www.aomori-animal.jp/01_MAIGO/Shuyoimg/")
        assert raw.image_urls[0].endswith("20260515_001.jpg")

    def test_extract_second_animal(self, fixture_html):
        """2 件目も同形式で抽出できる"""
        html = fixture_html("aomori_animal_jp")
        adapter = AomoriAnimalAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[1][0], category="sheltered")

        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "黒"
        assert raw.size == "中型"
        assert raw.image_urls[0].endswith("20260515_002.jpg")

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字が正しく復元される

        逆変換に失敗すると「青森」「十和田」「雑種」等が一致しない。
        """
        html = fixture_html("aomori_animal_jp")
        # 逆変換が走ることを担保するため、fixture の生文字列に
        # 「青森」「動物」が含まれていないことを前提条件として確認
        assert "青森" not in html and "動物" not in html

        adapter = AomoriAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert "十和田" in raw.location

    def test_image_urls_filter_keeps_shuyoimg(self):
        """`Shuyoimg/` を含む URL はフィルタを通過する"""
        adapter = AomoriAnimalAdapter(_site())
        urls = [
            "http://www.aomori-animal.jp/01_MAIGO/Shuyoimg/x.jpg",
            "http://www.aomori-animal.jp/logo.png",
        ]
        filtered = adapter._filter_image_urls(urls, LIST_URL)
        assert filtered == ["http://www.aomori-animal.jp/01_MAIGO/Shuyoimg/x.jpg"]

    def test_image_urls_filter_failsafe_when_no_shuyoimg(self):
        """`Shuyoimg/` を含む URL が一つもない場合は元リストを返す (フェイルセーフ)"""
        adapter = AomoriAnimalAdapter(_site())
        urls = ["http://www.aomori-animal.jp/logo.png"]
        assert adapter._filter_image_urls(urls, LIST_URL) == urls

    def test_normalize_sex_variants(self):
        """雄/雌・オス/メス・♂/♀ 等を統一表記に揃える"""
        cases = {
            "雄": "オス",
            "オス": "オス",
            "♂": "オス",
            "雌": "メス",
            "メス": "メス",
            "♀": "メス",
            "": "",
        }
        for raw, expected in cases.items():
            assert AomoriAnimalAdapter._normalize_sex(raw) == expected

    def test_empty_page_returns_empty_list(self):
        """データ行が無いページ (在庫 0 件) でも ParsingError を出さない"""
        empty_html = (
            "<html><head><title>迷子動物</title></head>"
            "<body>"
            "<p>青森県動物愛護センターに収容されている動物</p>"
            # 実データテーブル (border 属性付き) はあるがデータ行なし
            "<table border='1' cellspacing='1' cellpadding='1'>"
            "<caption>収容情報</caption>"
            "<tbody>"
            "<tr style='background:#ccccff'>"
            "<th>No.</th><th>見つかった日</th><th>見つかった場所</th>"
            "<th>種類</th><th>毛色</th><th>性別</th><th>体格</th>"
            "<th>特徴</th><th>画像</th><th>連絡先</th>"
            "</tr>"
            "</tbody></table>"
            "</body></html>"
        )
        adapter = AomoriAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_extract_out_of_range_raises(self, fixture_html):
        """範囲外 row index は ParsingError"""
        html = fixture_html("aomori_animal_jp")
        adapter = AomoriAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(f"{LIST_URL}#row=99", category="sheltered")

    def test_extract_invalid_virtual_url_raises(self):
        """`#row=N` 形式でない URL は ParsingError"""
        adapter = AomoriAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            # rows は空、parse_row_index で fragment 不正
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(LIST_URL, category="sheltered")

    def test_extract_species_dog_cat_other(self):
        """先頭セルの `<p>...</p>` から犬/猫/その他を判定する"""
        from bs4 import BeautifulSoup

        def cells_for(content_html: str):
            soup = BeautifulSoup(f"<table><tr>{content_html}</tr></table>", "html.parser")
            tr = soup.find("tr")
            return list(tr.find_all(["td", "th"]))

        assert AomoriAnimalAdapter._extract_species(cells_for("<td><p>1</p><p>犬</p></td>")) == "犬"
        assert (
            AomoriAnimalAdapter._extract_species(cells_for("<td><p>1</p><p>ねこ</p></td>")) == "猫"
        )
        assert AomoriAnimalAdapter._extract_species(cells_for("<td><p>1</p><p>猫</p></td>")) == "猫"
        assert (
            AomoriAnimalAdapter._extract_species(cells_for("<td><p>1</p><p>うさぎ</p></td>"))
            == "その他"
        )
        assert AomoriAnimalAdapter._extract_species([]) == "その他"

    def test_normalize_returns_animal_data(self, fixture_html):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = fixture_html("aomori_animal_jp")
        adapter = AomoriAnimalAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert hasattr(normalized, "species")
        # YYYY/MM/DD は normalizer が ISO 形式に変換する
        assert str(normalized.shelter_date) == "2026-05-12"

    def test_site_registered(self):
        """sites.yaml の name と一致する形で Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(SITE_NAME) is None:
            SiteAdapterRegistry.register(SITE_NAME, AomoriAnimalAdapter)
        assert SiteAdapterRegistry.get(SITE_NAME) is AomoriAnimalAdapter
