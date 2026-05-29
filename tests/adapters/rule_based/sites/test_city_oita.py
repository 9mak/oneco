"""CityOitaAdapter のテスト

大分市犬の保護収容情報サイト (city.oita.oita.jp/kurashi/pet/inunohogo/)
用 rule-based adapter の動作を検証する。

実構造: **single_page 形式**。1ページに複数動物がフリーテキストで並ぶ。
- 動物ブロック開始: 「令和N年M月D日飼い主さんを探しています」見出し
- 直後に「保護した場所/種類/推定年齢/毛色/性別/体格/その他」がコロン区切りで列挙
- 「お家がみつかりました」セクション以降は飼い主返却済み = sheltered 解消なので除外
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_oita import CityOitaAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# list_url (index.html) を模した合成 HTML
# 説明文 + detail 記事 1 つへのリンク (`/oNNN/kurashi/pet/NNNNNNNNNNNNN.html`)
LIST_HTML = """
<html><body>
<div id="tmp_contents">
  <h1>犬の保護収容情報（大分市内）についてお知らせします</h1>
  <p>大分市内で保護収容された犬の情報を掲載しています。</p>
  <ul>
    <li><a href="/o245/kurashi/pet/1338766046231.html">最新の保護犬情報 (令和8年4月27日 登録)</a></li>
  </ul>
</div>
</body></html>
"""

# detail 記事ページを模した合成 HTML
# 「探しています」2 件 + 「お家がみつかりました」1 件
DETAIL_HTML = """
<html><body>
<div id="tmp_contents">
  <h1>最新の保護犬情報</h1>
  <p>探しています</p>
  <p>令和8年4月27日飼い主さんを探しています</p>
  <p>保護した場所：荏隈</p>
  <p>種類：雑種</p>
  <p>推定年齢:5～7歳</p>
  <p>毛色：茶、白、黒</p>
  <p>性別：オス</p>
  <p>体格：中型</p>
  <p>その他：首輪（青色・革製）あり、リードなし</p>
  <p>令和8年3月4日飼い主さんを探しています</p>
  <p>保護した場所：種具</p>
  <p>種類：雑種</p>
  <p>推定年齢:4～6歳</p>
  <p>毛色：茶</p>
  <p>性別：メス</p>
  <p>体格：小型</p>
  <p>その他：首輪（緑・革製）あり、リードなし</p>
  <p>※保護収容犬の種類・年齢等は推定で記載しています。</p>
  <p>愛護動物の遺棄は犯罪です。</p>
  <p>問合せ先 大分市動物愛護センター</p>
  <p>お家がみつかりました</p>
  <p>令和8年5月26日飼い主さんからのお迎えがありました</p>
  <p>保護した場所：片島</p>
  <p>種類：シーズー</p>
  <p>推定年齢:6歳</p>
  <p>毛色：茶白</p>
  <p>性別：オス</p>
  <p>体格：小型</p>
</div>
</body></html>
"""

# detail link が無い list HTML (在庫 0 件状態)
EMPTY_LIST_HTML = """
<html><body>
<div id="tmp_contents">
  <h1>犬の保護収容情報</h1>
  <p>現在、保護収容中の犬はいません。</p>
</div>
</body></html>
"""


def _site(name: str = "大分市（保護犬）") -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="大分県",
        prefecture_code="44",
        list_url="https://www.city.oita.oita.jp/kurashi/pet/inunohogo/index.html",
        category="sheltered",
        single_page=True,
    )


class TestCityOitaAdapterFetchList:
    """list → detail を辿り、detail 内の「探しています」配下の動物ブロックを抽出"""

    def test_returns_only_active_blocks(self):
        """『探しています』配下の動物だけを抽出 (『お家がみつかりました』除外)"""
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", side_effect=[LIST_HTML, DETAIL_HTML]):
            urls = adapter.fetch_animal_list()
        assert len(urls) == 2, f"探しています配下の2匹のみ期待 (got {len(urls)})"
        for u, cat in urls:
            assert "#row=" in u
            assert u.startswith("https://www.city.oita.oita.jp/")
            assert cat == "sheltered"

    def test_empty_when_no_detail_link(self):
        """index.html に detail link が無ければ空リスト"""
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=EMPTY_LIST_HTML):
            urls = adapter.fetch_animal_list()
        assert urls == []

    def test_caches_html_for_two_fetches(self):
        """fetch_animal_list + 複数 extract_animal_details で HTTP は 2 回 (list+detail) だけ"""
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", side_effect=[LIST_HTML, DETAIL_HTML]) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, c)
        assert mock_get.call_count == 2


class TestCityOitaAdapterExtract:
    """各ブロックから RawAnimalData を構築"""

    def test_first_block_fields(self):
        """1匹目: 荏隈/雑種/5～7歳/茶、白、黒/オス/中型/2026-04-27"""
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", side_effect=[LIST_HTML, DETAIL_HTML]):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], "sheltered")
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"  # サイト名 (保護犬) から推定
        assert raw.sex == "オス"
        assert raw.age == "5～7歳"
        assert "茶" in raw.color
        assert raw.size == "中型"
        assert raw.location == "荏隈"
        # 令和8年4月27日 = 2026-04-27
        assert raw.shelter_date == "2026-04-27"
        assert raw.category == "sheltered"

    def test_second_block_fields(self):
        """2匹目: 種具/雑種/4～6歳/茶/メス/小型/2026-03-04"""
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", side_effect=[LIST_HTML, DETAIL_HTML]):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[1][0], "sheltered")
        assert raw.sex == "メス"
        assert raw.age == "4～6歳"
        assert raw.color == "茶"
        assert raw.size == "小型"
        assert raw.location == "種具"
        assert raw.shelter_date == "2026-03-04"

    def test_row_index_out_of_range_raises(self):
        adapter = CityOitaAdapter(_site())
        with patch.object(adapter, "_http_get", side_effect=[LIST_HTML, DETAIL_HTML]):
            adapter.fetch_animal_list()
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.city.oita.oita.jp/o245/kurashi/pet/1338766046231.html#row=99",
                    "sheltered",
                )


class TestCityOitaAdapterSpeciesInference:
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
        assert CityOitaAdapter._infer_species_from_site_name(name) == expected


class TestCityOitaAdapterRegistry:
    EXPECTED_SITE_NAMES = ("大分市（保護犬）",)

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered(self, site_name):
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, CityOitaAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is CityOitaAdapter
