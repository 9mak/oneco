"""CityOitaAdapter のテスト

大分市犬の保護収容情報サイト (city.oita.oita.jp/kurashi/pet/inunohogo/)
用 rule-based adapter の動作を検証する。

- 一覧ページ fixture (`city_oita_oita_jp.html`) からの detail URL 抽出
  (`/oNNN/kurashi/pet/NNNNNNNNNNNNN.html` 形式)
- detail ページ HTML を模した最小 HTML (`<th>/<td>` テーブルおよび
  `<td>/<td>` 2 列テーブル) からの RawAnimalData 構築
- 動物種別 (犬) がサイト名から推定されること
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
from data_collector.adapters.rule_based.sites.city_oita import (
    CityOitaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# detail ページを模した最小 HTML (`<th>/<td>` テーブル版)。
# 自治体 CMS で広く見られる「左 th: 項目名 / 右 td: 値」構造。
DETAIL_HTML_DOG = """
<html><body>
<div id="tmp_contents">
  <h1>犬の保護収容情報</h1>
  <table>
    <tbody>
      <tr><th>品種</th><td>雑種</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>年齢</th><td>成犬</td></tr>
      <tr><th>毛色</th><td>黒白</td></tr>
      <tr><th>大きさ</th><td>中型</td></tr>
      <tr><th>保護日</th><td>2026年5月7日</td></tr>
      <tr><th>場所</th><td>大分市内</td></tr>
      <tr><th>連絡先</th><td>097-588-1122</td></tr>
    </tbody>
  </table>
  <div class="photo">
    <img src="/o245/kurashi/pet/upload/dog001.jpg" alt="保護犬1">
    <img src="/o245/kurashi/pet/upload/dog002.jpg" alt="保護犬2">
  </div>
</div>
<div class="footer">
  <img src="/shared/images/footer/flogo.png" alt="ロゴ">
  <img src="/shared/images/favicon/favicon.ico" alt="">
</div>
</body></html>
"""

# detail ページを模した最小 HTML (`<td>/<td>` 2 列テーブル版)。
# `<th>` を持たないレイアウトでもラベルベースで値が取れること。
DETAIL_HTML_2COL = """
<html><body>
<table>
  <tr><td>品種</td><td>柴系雑種</td></tr>
  <tr><td>性別</td><td>メス</td></tr>
  <tr><td>毛色</td><td>茶</td></tr>
  <tr><td>保護日</td><td>2026年5月1日</td></tr>
  <tr><td>場所</td><td>大分市鶴崎</td></tr>
</table>
<img src="/o245/kurashi/pet/upload/dog003.jpg" alt="保護犬3">
</body></html>
"""

# 詳細リンクが 1 件も含まれない一覧ページ (在庫 0 件状態) を模した HTML。
EMPTY_LIST_HTML = """
<html><body>
<div id="tmp_contents">
  <h1>犬の保護収容情報</h1>
  <p>現在、保護収容中の犬はいません。</p>
</div>
<div id="tmp_lnavi">
  <ul>
    <li><a href="/kurashi/pet/inunohogo/index.html">犬の保護収容情報</a></li>
  </ul>
</div>
</body></html>
"""


def _site() -> SiteConfig:
    """大分市（保護犬） sites.yaml と一致する SiteConfig"""
    return SiteConfig(
        name="大分市（保護犬）",
        prefecture="大分県",
        prefecture_code="44",
        list_url=(
            "https://www.city.oita.oita.jp/kurashi/pet/inunohogo/index.html"
        ),
        category="sheltered",
        single_page=True,
    )


class TestCityOitaAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(
        self, fixture_html
    ):
        """一覧 fixture から `/oNNN/kurashi/pet/...` の記事 URL が抽出できる"""
        html = fixture_html("city_oita_oita_jp")
        adapter = CityOitaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1
        urls = [u for u, _cat in result]
        # フィクスチャに含まれる既知の detail URL
        assert any(
            "/o245/kurashi/pet/1338766046231.html" in u for u in urls
        )
        # 全 URL が `/oNNN/kurashi/pet/NNNNNNNNNNNNN.html` 形式の記事リンク
        for u in urls:
            assert "/kurashi/pet/" in u
            # `/kurashi/pet/{slug}/index.html` のカテゴリトップは含まれない
            assert not u.endswith("/index.html")
        # category は site_config.category 由来
        assert all(cat == "sheltered" for _u, cat in result)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)

    def test_fetch_animal_list_excludes_sidebar_links(self, fixture_html):
        """サイドメニュー (`#tmp_lnavi`) の `/kurashi/pet/{slug}/index.html`
        は detail URL に混入しない"""
        html = fixture_html("city_oita_oita_jp")
        adapter = CityOitaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        # サイドメニュー由来の URL (chiikineko / inunohogo 等) が含まれない
        for u in urls:
            assert "/chiikineko/" not in u
            assert "/inunohogo/" not in u
            assert "/dobutsu/" not in u

    def test_fetch_animal_list_dedupes_urls(self, fixture_html):
        """同一 URL が重複して並んでいても 1 件に集約される"""
        html = fixture_html("city_oita_oita_jp")
        adapter = CityOitaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """記事リンクが 1 件も無い (在庫 0 件) HTML では空リストを返す"""
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=EMPTY_LIST_HTML):
            result = adapter.fetch_animal_list()
        assert result == []


class TestCityOitaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_dog(
        self, assert_raw_animal
    ):
        """`<th>/<td>` テーブルの詳細ページから各フィールドが抽出できる"""
        adapter = CityOitaAdapter(_site())
        detail_url = (
            "https://www.city.oita.oita.jp/o245/kurashi/pet/"
            "1338766046231.html"
        )
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="成犬",
            color="黒白",
            size="中型",
            shelter_date="2026年5月7日",
            location="大分市内",
            phone="097-588-1122",
            category="sheltered",
        )
        # 動物写真は `/o245/kurashi/pet/upload/` 配下の 2 枚を採用、
        # `/shared/images/` (テンプレートロゴ等) は除外される
        assert len(raw.image_urls) == 2
        assert all("/shared/images/" not in u for u in raw.image_urls)
        assert all(not u.endswith(".ico") for u in raw.image_urls)
        assert all("/o245/kurashi/pet/upload/" in u for u in raw.image_urls)

    def test_extract_animal_details_supports_two_column_table(
        self, assert_raw_animal
    ):
        """`<th>` を持たない 2 列テーブルからも値を抽出できる"""
        adapter = CityOitaAdapter(_site())
        detail_url = (
            "https://www.city.oita.oita.jp/o245/kurashi/pet/"
            "1338766046231.html"
        )
        with patch.object(
            adapter, "_http_get", return_value=DETAIL_HTML_2COL
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="柴系雑種",
            sex="メス",
            color="茶",
            shelter_date="2026年5月1日",
            location="大分市鶴崎",
            category="sheltered",
        )

    def test_extract_animal_details_infers_species_from_site_name_when_empty(
        self,
    ):
        """species ラベルが見つからないときサイト名から「犬」が推定される"""
        # 「品種」ラベルを欠いた detail HTML
        detail_html = """
        <html><body>
        <table>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>毛色</th><td>白</td></tr>
        </table>
        </body></html>
        """
        adapter = CityOitaAdapter(_site())  # name: "大分市（保護犬）"
        detail_url = (
            "https://www.city.oita.oita.jp/o245/kurashi/pet/"
            "1338766046231.html"
        )
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )
        assert raw.species == "犬"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では例外を出す"""
        adapter = CityOitaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.city.oita.oita.jp/o245/kurashi/pet/"
                    "1338766046231.html"
                )


class TestCityOitaAdapterSpeciesInference:
    """サイト名からの動物種別推定"""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("大分市（保護犬）", "犬"),
            ("大分市（保護猫）", "猫"),
            ("大分市（保護犬猫）", "その他"),
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert (
            CityOitaAdapter._infer_species_from_site_name(name) == expected
        )


class TestCityOitaAdapterRegistry:
    """registry にサイト名が登録されていること

    sites.yaml の `name` フィールドと完全一致するサイト名で登録される。
    """

    EXPECTED_SITE_NAMES = ("大分市（保護犬）",)

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_city_oita_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, CityOitaAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is CityOitaAdapter, (
            f"{site_name} が CityOitaAdapter に紐付いていません: {cls}"
        )
