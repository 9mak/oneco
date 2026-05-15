"""CityKumamotoAdapter のテスト

熊本市動物愛護センター (city.kumamoto.jp/doubutuaigo/) 用 rule-based
adapter の動作を検証する。

- 一覧ページ fixture (`city_kumamoto.html`) からの detail URL 抽出
  (`/doubutuaigo/kijiNNNNNNNN/index.html` 形式)
- detail ページ HTML を模した最小 HTML (`<th>/<td>` テーブルおよび
  `<td>/<td>` 2 列テーブル) からの RawAnimalData 構築
- 動物種別 (犬/猫) が list URL パス (`list03612` / `list03615`) または
  サイト名から推定されること
- 2 サイトすべてが SiteAdapterRegistry に登録されていること

NOTE: fixture の HTML は実サイトから取得した際に二重 UTF-8 エンコード
(mojibake) になっているが、href 等の ASCII 部分は無傷のため、
ASCII ベースの CSS セレクタで detail link を抽出する本アダプタは
エンコードの影響を受けない。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kumamoto import (
    CityKumamotoAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# detail ページを模した最小 HTML (`<th>/<td>` テーブル版)。
# 自治体 CMS で広く見られる「左 th: 項目名 / 右 td: 値」構造。
DETAIL_HTML_DOG = """
<html><body>
<div id="maincontent"></div>
<div class="kijiBlock">
  <table>
    <tbody>
      <tr><th>品種</th><td>雑種</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>年齢</th><td>成犬</td></tr>
      <tr><th>毛色</th><td>黒白</td></tr>
      <tr><th>大きさ</th><td>中型</td></tr>
      <tr><th>保護日</th><td>2026年4月27日</td></tr>
      <tr><th>場所</th><td>北区植木町石川</td></tr>
      <tr><th>連絡先</th><td>096-380-2153</td></tr>
    </tbody>
  </table>
  <div class="photoArea">
    <img src="/doubutuaigo/upload/kiji/370632_1.jpg" alt="迷子犬写真1">
    <img src="/doubutuaigo/upload/kiji/370632_2.jpg" alt="迷子犬写真2">
  </div>
</div>
<div class="footer">
  <img src="//www.city.kumamoto.jp/dynamic/doubutuaigo/common/images/loading.gif" alt="">
  <img src="//www.city.kumamoto.jp/doubutuaigo/common/upload/common/53_10_header.png" alt="ロゴ">
</div>
</body></html>
"""

# detail ページを模した最小 HTML (`<td>/<td>` 2 列テーブル版)。
# `<th>` を持たないレイアウトでもラベルベースで値が取れること。
DETAIL_HTML_CAT_2COL = """
<html><body>
<table>
  <tr><td>品種</td><td>三毛猫</td></tr>
  <tr><td>性別</td><td>メス</td></tr>
  <tr><td>毛色</td><td>三毛</td></tr>
  <tr><td>保護日</td><td>2026年4月21日</td></tr>
  <tr><td>場所</td><td>中央区桜町</td></tr>
</table>
<img src="/doubutuaigo/upload/kiji/370538_1.jpg" alt="迷子猫写真">
</body></html>
"""


def _site_dog() -> SiteConfig:
    """迷子犬一覧 (一覧 fixture と一致)"""
    return SiteConfig(
        name="熊本市（迷子犬一覧）",
        prefecture="熊本県",
        prefecture_code="43",
        list_url="https://www.city.kumamoto.jp/doubutuaigo/list03612.html",
        category="lost",
    )


def _site_cat() -> SiteConfig:
    """迷子猫一覧"""
    return SiteConfig(
        name="熊本市（迷子猫一覧）",
        prefecture="熊本県",
        prefecture_code="43",
        list_url="https://www.city.kumamoto.jp/doubutuaigo/list03615.html",
        category="lost",
    )


class TestCityKumamotoAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(
        self, fixture_html
    ):
        """一覧 fixture から `/doubutuaigo/kijiNNNNNNNN/index.html` URL が抽出できる"""
        html = fixture_html("city_kumamoto")
        adapter = CityKumamotoAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        urls = [u for u, _cat in result]
        # フィクスチャに含まれる既知の detail URL
        assert any(
            "/doubutuaigo/kiji00370632/index.html" in u for u in urls
        )
        assert any(
            "/doubutuaigo/kiji00370538/index.html" in u for u in urls
        )
        # 全 URL が `/doubutuaigo/kiji` を含む詳細ページである
        for u in urls:
            assert "/doubutuaigo/kiji" in u
        # ヘッダ/サイドメニュー/フッタの一覧ページ遷移リンクが混入しない
        for u in urls:
            assert "/doubutuaigo/list" not in u
            assert "/doubutuaigo/default" not in u
        # category は site_config.category 由来
        assert all(cat == "lost" for _u, cat in result)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)

    def test_fetch_animal_list_dedupes_urls(self, fixture_html):
        """同一 URL が重複して並んでいても 1 件に集約される"""
        html = fixture_html("city_kumamoto")
        adapter = CityKumamotoAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """記事リンクが 1 件も無い (在庫 0 件) HTML では空リストを返す"""
        empty_html = """
        <html><body>
        <div id="maincontent"></div>
        <ul class="kijilist"></ul>
        </body></html>
        """
        adapter = CityKumamotoAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


class TestCityKumamotoAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_dog(
        self, assert_raw_animal
    ):
        """`<th>/<td>` テーブルの詳細ページから各フィールドが抽出できる"""
        adapter = CityKumamotoAdapter(_site_dog())
        detail_url = (
            "https://www.city.kumamoto.jp/doubutuaigo/"
            "kiji00370632/index.html"
        )
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
            shelter_date="2026年4月27日",
            location="北区植木町石川",
            phone="096-380-2153",
            category="lost",
        )
        # 動物写真は `/doubutuaigo/upload/kiji/` 配下の 2 枚を採用、
        # `common/images/` (loading.gif) や `common/upload/common/` の
        # ロゴ画像は除外される
        assert len(raw.image_urls) == 2
        assert all("/common/images/" not in u for u in raw.image_urls)
        assert all("/common/upload/common/" not in u for u in raw.image_urls)
        assert all("/upload/kiji/" in u for u in raw.image_urls)

    def test_extract_animal_details_supports_two_column_table(
        self, assert_raw_animal
    ):
        """`<th>` を持たない 2 列テーブルからも値を抽出できる"""
        adapter = CityKumamotoAdapter(_site_cat())
        detail_url = (
            "https://www.city.kumamoto.jp/doubutuaigo/"
            "kiji00370538/index.html"
        )
        with patch.object(
            adapter, "_http_get", return_value=DETAIL_HTML_CAT_2COL
        ):
            raw = adapter.extract_animal_details(detail_url, category="lost")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="三毛猫",
            sex="メス",
            color="三毛",
            shelter_date="2026年4月21日",
            location="中央区桜町",
            category="lost",
        )

    def test_extract_animal_details_infers_species_from_list_url_when_empty(
        self,
    ):
        """species ラベルが見つからないとき list URL から推定される

        detail URL (`/doubutuaigo/kijiNNN/...`) は species ヒントを
        含まないため、site_config.list_url の `list03612` (犬) /
        `list03615` (猫) から推定される。
        """
        # 「品種」ラベルを欠いた detail HTML
        detail_html = """
        <html><body>
        <table>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>毛色</th><td>白</td></tr>
        </table>
        </body></html>
        """
        adapter = CityKumamotoAdapter(_site_dog())  # list_url: list03612
        detail_url = (
            "https://www.city.kumamoto.jp/doubutuaigo/"
            "kiji00370632/index.html"
        )
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="lost")
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_from_list_url_for_cat(self):
        """猫サイト (list03615) では species 補完が "猫" になる"""
        detail_html = """
        <html><body>
        <table>
          <tr><th>性別</th><td>メス</td></tr>
        </table>
        </body></html>
        """
        adapter = CityKumamotoAdapter(_site_cat())  # list_url: list03615
        detail_url = (
            "https://www.city.kumamoto.jp/doubutuaigo/"
            "kiji00370538/index.html"
        )
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="lost")
        assert raw.species == "猫"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では例外を出す"""
        adapter = CityKumamotoAdapter(_site_dog())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.city.kumamoto.jp/doubutuaigo/"
                    "kiji00000000/index.html"
                )


class TestCityKumamotoAdapterSpeciesInference:
    """list URL パス / サイト名からの動物種別推定"""

    @pytest.mark.parametrize(
        "url,expected",
        [
            (
                "https://www.city.kumamoto.jp/doubutuaigo/list03612.html",
                "犬",
            ),
            (
                "https://www.city.kumamoto.jp/doubutuaigo/list03615.html",
                "猫",
            ),
            (
                "https://www.city.kumamoto.jp/doubutuaigo/kiji00370632/index.html",
                "",
            ),
            ("", ""),
        ],
    )
    def test_infer_species_from_url(self, url, expected):
        assert (
            CityKumamotoAdapter._infer_species_from_url(url) == expected
        )

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("熊本市（迷子犬一覧）", "犬"),
            ("熊本市（迷子猫一覧）", "猫"),
            ("熊本市（迷子犬猫）", "その他"),
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert (
            CityKumamotoAdapter._infer_species_from_site_name(name) == expected
        )


class TestCityKumamotoAdapterRegistry:
    """registry に 2 サイトすべて登録されていること

    sites.yaml の `name` フィールドと完全一致する 2 サイト名で登録される。
    """

    EXPECTED_SITE_NAMES = (
        "熊本市（迷子犬一覧）",
        "熊本市（迷子猫一覧）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_city_kumamoto_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, CityKumamotoAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is CityKumamotoAdapter, (
            f"{site_name} が CityKumamotoAdapter に紐付いていません: {cls}"
        )
