"""CityTakamatsuKagawaAdapter のテスト

高松市 わんにゃん高松 (city.takamatsu.kagawa.jp/udanimo/) 用 rule-based
adapter の動作を検証する。

- 一覧ページ fixture (`city_takamatsu_kagawa.html`) は在庫 0 件状態の
  HTML である (実サイトでは JS でテーブル行が動的追加されるため、
  静的 HTML 単体では `<tr class="ttr">` の見出し行のみ)。
  この状態で `fetch_animal_list` が空リストを返すことを検証する。
- detail ページ HTML を模した最小 HTML から `RawAnimalData` が
  正しく構築されることを検証する。
- 動物種別 (犬/猫) が URL クエリ `animaltype=1|2` から推定されることを検証する。
- 2 サイトすべてが SiteAdapterRegistry に登録されていることを検証する。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_takamatsu_kagawa import (
    CityTakamatsuKagawaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# detail ページを模した最小 HTML。
# 実サイトの詳細ページ HTML は入手できていないため、一覧表のカラム
# (収容日 / 収容場所 / 品種 / 毛色 / 性別) に対応するラベル付きの
# `<th>/<td>` テーブルを想定する。これは高松市 CMS の他ページで
# よく見られる構造。
DETAIL_HTML_DOG = """
<html><body>
<div id="container">
  <div id="contents">
    <div id="right">
      <table border="0" cellspacing="1" class="detail-table">
        <tbody>
          <tr><th>収容日</th><td>令和8年5月10日</td></tr>
          <tr><th>収容場所</th><td>高松市保健所</td></tr>
          <tr><th>品種</th><td>雑種</td></tr>
          <tr><th>毛色</th><td>黒白</td></tr>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>大きさ</th><td>中型</td></tr>
          <tr><th>年齢</th><td>成犬</td></tr>
        </tbody>
      </table>
      <div class="photo">
        <img src="/udanimo/images/animal/12345_1.jpg" alt="収容犬写真">
        <img src="/udanimo/images/animal/12345_2.jpg" alt="収容犬写真2">
      </div>
    </div>
  </div>
</div>
<div class="footer">
  <div class="footer-img">
    <img src="common/image/footer_pet.png" width="84" height="79" alt="わんにゃん高松"/>
  </div>
  <div class="adress">
    電話：<span id="katelno">０８７－８３９－２８６５</span>
  </div>
</div>
</body></html>
"""

# detail ページを模した最小 HTML (2 列テーブル版)
# `<th>` を使わず、左セルにラベル・右セルに値を並べる構造でも
# 抽出できることを検証する。
DETAIL_HTML_2COL = """
<html><body>
<table>
  <tr><td>品種</td><td>三毛猫</td></tr>
  <tr><td>性別</td><td>メス</td></tr>
  <tr><td>毛色</td><td>三毛</td></tr>
  <tr><td>収容日</td><td>令和8年5月12日</td></tr>
  <tr><td>収容場所</td><td>高松市保健所</td></tr>
</table>
<img src="/udanimo/images/animal/56789_1.jpg" alt="収容猫写真">
</body></html>
"""


def _site_dog() -> SiteConfig:
    """収容中犬 (一覧 fixture と一致)"""
    return SiteConfig(
        name="高松市 わんにゃん高松（収容中犬）",
        prefecture="香川県",
        prefecture_code="37",
        list_url=(
            "https://www.city.takamatsu.kagawa.jp/udanimo/"
            "ani_infolist1.html?infotype=1&animaltype=1"
        ),
        category="lost",
    )


def _site_cat() -> SiteConfig:
    """収容中猫"""
    return SiteConfig(
        name="高松市 わんにゃん高松（収容中猫）",
        prefecture="香川県",
        prefecture_code="37",
        list_url=(
            "https://www.city.takamatsu.kagawa.jp/udanimo/"
            "ani_infolist1.html?infotype=1&animaltype=2"
        ),
        category="lost",
    )


class TestCityTakamatsuKagawaAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_returns_empty_for_zero_stock_fixture(self, fixture_html):
        """在庫 0 件の fixture (テーブルが見出し行のみ) では空リストを返す

        高松市の一覧 HTML は JS でデータ行を動的に追加する仕組みのため、
        静的 HTML 単体では `<tr class="ttr">` の見出し行のみとなる。
        この状態を 0 件正常系として扱い、ParsingError を投げない。
        """
        html = fixture_html("city_takamatsu_kagawa")
        adapter = CityTakamatsuKagawaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_extracts_detail_urls_when_rows_present(self):
        """データ行 (詳細リンク) があれば detail URL を抽出する"""
        # JS が動いた後の DOM を想定して `<a href="ani_infodetail1.html?infoid=XXXX">`
        # を含むテーブル行を持つ HTML を組み立てる。
        list_html = """
        <html><body>
        <div class="list-area">
          <table id="hoken_tbl">
            <tbody>
              <tr class="ttr"><td>収容日</td><td>No.</td></tr>
              <tr>
                <td>令和8年5月10日</td>
                <td>1234</td>
                <td><a href="ani_infodetail1.html?infoid=1234">詳細</a></td>
              </tr>
              <tr>
                <td>令和8年5月11日</td>
                <td>1235</td>
                <td><a href="ani_infodetail1.html?infoid=1235">詳細</a></td>
              </tr>
            </tbody>
          </table>
          <table id="ippan_tbl">
            <tbody>
              <tr class="ttr"><td>収容日</td><td>No.</td></tr>
              <tr>
                <td>令和8年5月12日</td>
                <td>2001</td>
                <td><a href="ani_infodetail1.html?infoid=2001">詳細</a></td>
              </tr>
            </tbody>
          </table>
        </div>
        </body></html>
        """
        adapter = CityTakamatsuKagawaAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value=list_html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        urls = [u for u, _cat in result]
        # 詳細 URL は絶対 URL に変換されている
        for u in urls:
            assert u.startswith("http")
            assert "ani_infodetail1.html?infoid=" in u
        # 既知の infoid が含まれている
        assert any("infoid=1234" in u for u in urls)
        assert any("infoid=1235" in u for u in urls)
        assert any("infoid=2001" in u for u in urls)
        # category は site_config 由来
        assert all(cat == "lost" for _u, cat in result)

    def test_fetch_animal_list_dedupes_urls(self):
        """同一 detail URL が複数並んでも 1 件に集約される"""
        list_html = """
        <html><body>
        <a href="ani_infodetail1.html?infoid=999">詳細</a>
        <a href="ani_infodetail1.html?infoid=999">写真</a>
        <a href="ani_infodetail1.html?infoid=1000">詳細</a>
        </body></html>
        """
        adapter = CityTakamatsuKagawaAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value=list_html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == 2
        assert len(urls) == len(set(urls))


class TestCityTakamatsuKagawaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_dog(self, assert_raw_animal):
        """`<th>/<td>` テーブルの詳細ページから各フィールドが抽出できる"""
        adapter = CityTakamatsuKagawaAdapter(_site_dog())
        detail_url = "https://www.city.takamatsu.kagawa.jp/udanimo/ani_infodetail1.html?infoid=1234"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(detail_url, category="lost")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="成犬",
            color="黒白",
            size="中型",
            shelter_date="令和8年5月10日",
            location="高松市保健所",
            category="lost",
        )
        # フッタの全角電話番号が `XXX-XXX-XXXX` に正規化される
        assert raw.phone == "087-839-2865"
        # 動物写真は `/udanimo/images/animal/` 配下の 2 枚を採用、
        # `common/image/` 配下のロゴは除外される
        assert len(raw.image_urls) == 2
        assert all("/common/image/" not in u for u in raw.image_urls)
        assert all("/animal/" in u for u in raw.image_urls)

    def test_extract_animal_details_supports_two_column_table(self, assert_raw_animal):
        """`<th>` を持たない 2 列テーブルからも値を抽出できる"""
        adapter = CityTakamatsuKagawaAdapter(_site_cat())
        detail_url = "https://www.city.takamatsu.kagawa.jp/udanimo/ani_infodetail1.html?infoid=5678"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_2COL):
            raw = adapter.extract_animal_details(detail_url, category="lost")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="三毛猫",
            sex="メス",
            color="三毛",
            shelter_date="令和8年5月12日",
            location="高松市保健所",
            category="lost",
        )

    def test_extract_animal_details_infers_species_from_url_query_when_empty(
        self,
    ):
        """species ラベルが見つからないとき URL クエリ animaltype から推定される"""
        # 「品種」ラベルを欠いた detail HTML
        detail_html = """
        <html><body>
        <table>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>毛色</th><td>白</td></tr>
        </table>
        </body></html>
        """
        adapter = CityTakamatsuKagawaAdapter(_site_dog())
        # animaltype=1 (犬) を含む detail URL
        detail_url = (
            "https://www.city.takamatsu.kagawa.jp/udanimo/"
            "ani_infodetail1.html?infoid=1&animaltype=1"
        )
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="lost")
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_from_site_list_url(self):
        """detail URL に animaltype が無くても site_config.list_url から推定される"""
        detail_html = """
        <html><body>
        <table>
          <tr><th>性別</th><td>メス</td></tr>
        </table>
        </body></html>
        """
        # site_config の list_url は animaltype=2 (猫)
        adapter = CityTakamatsuKagawaAdapter(_site_cat())
        detail_url = "https://www.city.takamatsu.kagawa.jp/udanimo/ani_infodetail1.html?infoid=999"
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="lost")
        assert raw.species == "猫"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では例外を出す"""
        adapter = CityTakamatsuKagawaAdapter(_site_dog())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.city.takamatsu.kagawa.jp/udanimo/ani_infodetail1.html?infoid=99999"
                )


class TestCityTakamatsuKagawaAdapterSpeciesInference:
    """URL クエリ / サイト名からの動物種別推定"""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://example.com/x?animaltype=1", "犬"),
            ("https://example.com/x?animaltype=2", "猫"),
            ("https://example.com/x?animaltype=3", "その他"),
            ("https://example.com/x?animaltype=9", ""),
            ("https://example.com/x", ""),
            ("", ""),
        ],
    )
    def test_infer_species_from_url(self, url, expected):
        assert CityTakamatsuKagawaAdapter._infer_species_from_url(url) == expected

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("高松市 わんにゃん高松（収容中犬）", "犬"),
            ("高松市 わんにゃん高松（収容中猫）", "猫"),
            ("高松市 わんにゃん高松（犬猫）", "その他"),
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert CityTakamatsuKagawaAdapter._infer_species_from_site_name(name) == expected


class TestCityTakamatsuKagawaAdapterRegistry:
    """registry に 2 サイトすべて登録されていること"""

    EXPECTED_SITE_NAMES = (
        "高松市 わんにゃん高松（収容中犬）",
        "高松市 わんにゃん高松（収容中猫）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_takamatsu_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, CityTakamatsuKagawaAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is CityTakamatsuKagawaAdapter, (
            f"{site_name} が CityTakamatsuKagawaAdapter に紐付いていません: {cls}"
        )
