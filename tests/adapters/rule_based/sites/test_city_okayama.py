"""CityOkayamaAdapter のテスト

岡山市保護動物情報サイト (city.okayama.jp/kurashi/category/1-15-1-...html) 用
rule-based adapter の動作を検証する。

- 一覧ページ fixture (`city_okayama_jp.html`) からの detail URL 抽出
  (`/kurashi/0000NNNNNN.html` 形式の記事リンク)
- detail ページ HTML を模した最小 HTML (`<th>/<td>` テーブルおよび
  `<td>/<td>` 2 列テーブル) からの RawAnimalData 構築
- 動物種別 (犬/猫) がページタイトルから推定されること
- サイト名が SiteAdapterRegistry に登録されていること
- 在庫 0 件 (詳細リンク 0 件) の HTML では空リストを返すこと

NOTE: fixture の HTML は実サイトから取得した際に二重 UTF-8 エンコード
(mojibake) になっているが、href 等の ASCII 部分は無傷のため、
ASCII ベースの CSS セレクタで detail link を抽出する本アダプタは
エンコードの影響を受けない。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_okayama import (
    CityOkayamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# detail ページを模した最小 HTML (`<th>/<td>` テーブル版)。
# 自治体 CMS で広く見られる「左 th: 項目名 / 右 td: 値」構造。
DETAIL_HTML_DOG = """
<html><head><title>1D2026023保護犬個別情報 | 岡山市</title></head><body>
<div class="container">
  <h1>1D2026023保護犬個別情報</h1>
  <table>
    <tbody>
      <tr><th>種類</th><td>雑種</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>年齢</th><td>成犬</td></tr>
      <tr><th>毛色</th><td>黒白</td></tr>
      <tr><th>大きさ</th><td>中型</td></tr>
      <tr><th>収容日</th><td>2026年5月14日</td></tr>
      <tr><th>収容場所</th><td>岡山市北区</td></tr>
      <tr><th>連絡先</th><td>086-803-1000</td></tr>
    </tbody>
  </table>
  <div class="photo">
    <img src="/uploaded/image/dog001.jpg" alt="保護犬1">
    <img src="/uploaded/image/dog002.jpg" alt="保護犬2">
  </div>
</div>
<footer>
  <img src="/css/img/2024_foot_logo.png" alt="ロゴ">
  <img src="/design_img/favicon.ico" alt="">
  <img src="/images/clearspacer.gif" alt="">
</footer>
</body></html>
"""

# detail ページを模した最小 HTML (`<td>/<td>` 2 列テーブル版)。
# `<th>` を持たないレイアウトでもラベルベースで値が取れること。
DETAIL_HTML_2COL = """
<html><head><title>保護猫個別情報 | 岡山市</title></head><body>
<table>
  <tr><td>種類</td><td>三毛</td></tr>
  <tr><td>性別</td><td>メス</td></tr>
  <tr><td>毛色</td><td>三毛</td></tr>
  <tr><td>収容日</td><td>2026年5月10日</td></tr>
  <tr><td>収容場所</td><td>岡山市南区</td></tr>
</table>
<img src="/uploaded/image/cat001.jpg" alt="保護猫1">
</body></html>
"""

# 詳細リンクが 1 件も含まれない一覧ページ (在庫 0 件状態) を模した HTML。
EMPTY_LIST_HTML = """
<html><body>
<div class="container">
  <h1>保護動物情報</h1>
  <ul class="category_end">
  </ul>
</div>
<aside class="page_right">
  <ul>
    <li><a href="https://www.city.okayama.jp/kurashi/category/1-15-9-0-0-0-0-0-0-0.html">同じ階層</a></li>
  </ul>
</aside>
</body></html>
"""


def _site() -> SiteConfig:
    """岡山市（保護動物情報） sites.yaml と一致する SiteConfig"""
    return SiteConfig(
        name="岡山市（保護動物情報）",
        prefecture="岡山県",
        prefecture_code="33",
        list_url=("https://www.city.okayama.jp/kurashi/category/1-15-1-0-0-0-0-0-0-0.html"),
        list_link_pattern="a[href*='/kurashi/']",
        category="sheltered",
    )


class TestCityOkayamaAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(self, fixture_html):
        """一覧 fixture から `/kurashi/0000NNNNNN.html` の記事 URL が抽出できる"""
        html = fixture_html("city_okayama_jp")
        adapter = CityOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        urls = [u for u, _cat in result]
        # フィクスチャに含まれる既知の detail URL (`./../0000067714.html` →
        # 絶対 URL `https://www.city.okayama.jp/kurashi/0000067714.html`)
        assert any("/kurashi/0000067714.html" in u for u in urls)
        # 全 URL が 10 桁数字 + .html 形式の記事リンク (category/index.html ではない)
        for u in urls:
            assert "/kurashi/" in u
            assert "/category/" not in u
            assert not u.endswith("/index.html")
        # category は site_config.category 由来
        assert all(cat == "sheltered" for _u, cat in result)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)

    def test_fetch_animal_list_excludes_sidebar_links(self, fixture_html):
        """サイドメニュー (`aside.page_right` / `div.page_right_cat`) の
        `/kurashi/category/...` や「こんなときには」リンクは混入しない"""
        html = fixture_html("city_okayama_jp")
        adapter = CityOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        # サイドメニュー由来の category/... リンクは含まれない
        for u in urls:
            assert "/category/" not in u
        # サイドメニューの「こんなときには」セクションの URL
        # (例: 0000021839.html〜0000021779.html) は ul.category_end 配下では
        # ないため、本文の記事 URL とは別に並ぶ。本文セレクタ ul.category_end
        # で絞り込んでいるので混入しないはず。
        assert not any("/kurashi/0000021839.html" in u for u in urls)

    def test_fetch_animal_list_dedupes_urls(self, fixture_html):
        """同一 URL が重複して並んでいても 1 件に集約される"""
        html = fixture_html("city_okayama_jp")
        adapter = CityOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """記事リンクが 1 件も無い (在庫 0 件) HTML では空リストを返す"""
        adapter = CityOkayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=EMPTY_LIST_HTML):
            result = adapter.fetch_animal_list()
        assert result == []


class TestCityOkayamaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_dog(self, assert_raw_animal):
        """`<th>/<td>` テーブルの詳細ページから各フィールドが抽出できる"""
        adapter = CityOkayamaAdapter(_site())
        detail_url = "https://www.city.okayama.jp/kurashi/0000067714.html"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="成犬",
            color="黒白",
            size="中型",
            shelter_date="2026年5月14日",
            location="岡山市北区",
            phone="086-803-1000",
            category="sheltered",
        )
        # 動物写真は `/uploaded/image/` 配下の 2 枚を採用、
        # `/css/img/`, `/design_img/`, `/images/clearspacer` (テンプレート
        # ロゴ等) は除外される
        assert len(raw.image_urls) == 2
        assert all("/css/img/" not in u for u in raw.image_urls)
        assert all("/design_img/" not in u for u in raw.image_urls)
        assert all(not u.endswith(".ico") for u in raw.image_urls)
        assert all(not u.endswith(".gif") for u in raw.image_urls)
        assert all("/uploaded/image/" in u for u in raw.image_urls)

    def test_extract_animal_details_supports_two_column_table(self, assert_raw_animal):
        """`<th>` を持たない 2 列テーブルからも値を抽出できる"""
        adapter = CityOkayamaAdapter(_site())
        detail_url = "https://www.city.okayama.jp/kurashi/0000082050.html"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_2COL):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="三毛",
            sex="メス",
            color="三毛",
            shelter_date="2026年5月10日",
            location="岡山市南区",
            category="sheltered",
        )

    def test_extract_animal_details_infers_species_from_title_when_empty(
        self,
    ):
        """species ラベルが見つからないときページタイトルから「犬」が推定される"""
        # 「種類」ラベルを欠いた detail HTML (タイトルに「保護犬」を含む)
        detail_html = """
        <html><head><title>1D2026023保護犬個別情報 | 岡山市</title></head>
        <body>
        <h1>1D2026023保護犬個別情報</h1>
        <table>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>毛色</th><td>白</td></tr>
        </table>
        </body></html>
        """
        adapter = CityOkayamaAdapter(_site())
        detail_url = "https://www.city.okayama.jp/kurashi/0000067714.html"
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_cat_from_title(self):
        """ページタイトルに「保護猫」を含む場合「猫」が推定される"""
        detail_html = """
        <html><head><title>岡山市保護猫情報 | 岡山市</title></head>
        <body>
        <h1>岡山市保護猫情報</h1>
        <table>
          <tr><th>性別</th><td>メス</td></tr>
        </table>
        </body></html>
        """
        adapter = CityOkayamaAdapter(_site())
        detail_url = "https://www.city.okayama.jp/kurashi/0000016469.html"
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")
        assert raw.species == "猫"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では例外を出す"""
        adapter = CityOkayamaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.city.okayama.jp/kurashi/0000067714.html"
                )


class TestCityOkayamaAdapterSpeciesInference:
    """テキストからの動物種別推定"""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("1D2026023保護犬個別情報", "犬"),
            ("岡山市保護猫情報", "猫"),
            ("保護犬猫一覧", ""),  # 両方含む → 推定不能
            ("お問い合わせ", ""),  # どちらも含まない
            ("", ""),
        ],
    )
    def test_infer_species_from_text(self, text, expected):
        assert CityOkayamaAdapter._infer_species_from_text(text) == expected


class TestCityOkayamaAdapterRegistry:
    """registry にサイト名が登録されていること

    sites.yaml の `name` フィールドと完全一致するサイト名で登録される。
    """

    EXPECTED_SITE_NAMES = ("岡山市（保護動物情報）",)

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_city_okayama_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, CityOkayamaAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is CityOkayamaAdapter, (
            f"{site_name} が CityOkayamaAdapter に紐付いていません: {cls}"
        )
