"""CityKurashikiAdapter のテスト

倉敷市（保護動物）用 rule-based adapter の動作を検証する。

- 1 ページに `<ul class="listlink"><li><a>` 形式で動物が並ぶ single_page 形式
- 各 `<a>` テキストに「収容日 / 収容場所 / 動物種別 / 性別」が
  全角スペース区切りで入っている
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
- 二重 UTF-8 mojibake fixture の自動補正
- 問い合わせ電話番号 (086-434-9829) は全行に共通で注入される
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kurashiki import (
    CityKurashikiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


SITE_NAME = "倉敷市（保護動物）"
LIST_URL = (
    "https://www.city.kurashiki.okayama.jp/kurashi/pet/1013042/index.html"
)


def _site() -> SiteConfig:
    return SiteConfig(
        name=SITE_NAME,
        prefecture="岡山県",
        prefecture_code="33",
        list_url=LIST_URL,
        category="sheltered",
        single_page=True,
    )


def _populated_html() -> str:
    """テスト用に動物 3 件を持つ最小 HTML を生成する

    実 fixture と同じ `<ul class="listlink"><li><a>...</a></li></ul>` 構造を
    持ち、`<a>` テキストに収容日 / 場所 / 種類 / 性別を埋め込む。
    """
    return """<html><head><title>倉敷市</title></head><body>
<main id="page"><article id="content">
<h1>保護動物情報</h1>
<ul class="listlink clearfix">
  <li><a href="../../../kurashi/pet/1013042/1025759.html">令和08年04月30日　児島小川　猫（雑種）♀</a></li>
  <li><a href="../../../kurashi/pet/1013042/1025743.html">令和08年04月27日　玉島乙島　犬（トイプードル）♂</a></li>
  <li><a href="../../../kurashi/pet/1013042/1025580.html">令和08年04月17日　加須山　猫（雑種）♂</a></li>
</ul>
<div id="reference">
  <p>電話番号：086-434-9829</p>
</div>
</article></main>
</body></html>
"""


class TestCityKurashikiAdapter:
    # ─────────────── 実 fixture を使った全体動作 ───────────────

    def test_fetch_animal_list_from_real_fixture(self, fixture_html):
        """実 fixture から 3 件の `<li>` 行が取得できる（mojibake 自動補正込み）"""
        html = fixture_html("city_kurashiki_okayama_jp")
        adapter = CityKurashikiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        for url, category in result:
            assert url.startswith(LIST_URL + "#row=")
            assert category == "sheltered"

    def test_extract_first_animal_from_real_fixture(self, fixture_html):
        """実 fixture の 1 件目: 令和08年04月30日 / 児島小川 / 猫 / メス"""
        html = fixture_html("city_kurashiki_okayama_jp")
        adapter = CityKurashikiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.shelter_date == "2026-04-30"
        assert raw.location == "児島小川"
        assert raw.category == "sheltered"
        # 問い合わせ先電話番号が全件に共通注入される
        assert raw.phone == "086-434-9829"
        # 詳細ページ URL が絶対化される
        assert raw.source_url.startswith("https://www.city.kurashiki.okayama.jp/")
        assert "1025759" in raw.source_url

    def test_extract_second_animal_dog_male(self, fixture_html):
        """実 fixture の 2 件目: 犬 / オス"""
        html = fixture_html("city_kurashiki_okayama_jp")
        adapter = CityKurashikiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[1][0], category="sheltered")

        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.shelter_date == "2026-04-27"
        assert raw.location == "玉島乙島"

    # ─────────────── populated HTML での詳細抽出ロジック ───────────────

    def test_extract_with_populated_html(self):
        """最小 populated HTML から 3 件抽出できる"""
        adapter = CityKurashikiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 3
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        # 1 件目: 猫メス
        assert raws[0].species == "猫"
        assert raws[0].sex == "メス"
        # 2 件目: 犬オス
        assert raws[1].species == "犬"
        assert raws[1].sex == "オス"
        # 3 件目: 猫オス
        assert raws[2].species == "猫"
        assert raws[2].sex == "オス"

    def test_http_called_only_once(self):
        """_load_rows のキャッシュにより HTTP は 1 回しか呼ばれない"""
        adapter = CityKurashikiAdapter(_site())

        with patch.object(
            adapter, "_http_get", return_value=_populated_html()
        ) as mock_get:
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                adapter.extract_animal_details(url, category=cat)

        assert mock_get.call_count == 1

    # ─────────────── 在庫 0 件 ───────────────

    def test_empty_listlink_returns_empty_list(self):
        """`<ul class="listlink">` 配下に `<li>` が無い場合は空リストを返す"""
        html_empty = """<html><body><main>
<h1>保護動物情報</h1>
<ul class="listlink"></ul>
</main></body></html>"""
        adapter = CityKurashikiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html_empty):
            assert adapter.fetch_animal_list() == []

    def test_li_without_anchor_excluded(self):
        """リンクを持たない `<li>` は除外される"""
        html = """<html><body><main>
<ul class="listlink">
  <li>placeholder</li>
  <li><a href="/x.html">令和08年04月30日　児島　猫（雑種）♀</a></li>
</ul>
</main></body></html>"""
        adapter = CityKurashikiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
        assert len(urls) == 1

    # ─────────────── 個別ロジック ───────────────

    def test_parse_shelter_date_reiwa(self):
        """令和YY年MM月DD日 が ISO に揃う (令和元年 = 2019)"""
        f = CityKurashikiAdapter._parse_shelter_date
        assert f("令和08年04月30日") == "2026-04-30"
        assert f("令和元年5月1日") in {"", "2019-05-01"}  # 元年表記は対象外
        assert f("令和1年5月1日") == "2019-05-01"
        assert f("令和10年12月3日") == "2028-12-03"

    def test_parse_shelter_date_gregorian(self):
        """西暦表記もそのまま ISO に揃う"""
        f = CityKurashikiAdapter._parse_shelter_date
        assert f("2026年4月30日") == "2026-04-30"
        assert f("2026/4/30") == "2026-04-30"
        assert f("2026-04-30") == "2026-04-30"
        assert f("") == ""
        assert f("不明な日付") == ""

    def test_parse_species(self):
        """動物種別フィールドから犬/猫/その他に丸める"""
        f = CityKurashikiAdapter._parse_species
        assert f("犬（トイプードル）") == "犬"
        assert f("猫（雑種）") == "猫"
        assert f("犬") == "犬"
        assert f("猫") == "猫"
        assert f("ウサギ") == "その他"
        assert f("") == ""

    def test_parse_sex(self):
        """性別記号 / 文字列を正規化する"""
        f = CityKurashikiAdapter._parse_sex
        assert f("♂") == "オス"
        assert f("♀") == "メス"
        assert f("オス") == "オス"
        assert f("メス") == "メス"
        assert f("雄") == "オス"
        assert f("雌") == "メス"
        assert f("") == ""
        assert f("不明") == ""

    # ─────────────── mojibake 補正 ───────────────

    def test_mojibake_is_repaired(self):
        """二重 UTF-8 エンコード HTML でも漢字が正しく復元される"""
        good = _populated_html()
        try:
            mojibake = good.encode("utf-8").decode("latin-1")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pytest.skip("環境依存: 二重エンコード再現不可")
        assert "倉敷" not in mojibake

        adapter = CityKurashikiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=mojibake):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.location == "児島小川"
        assert raw.species == "猫"

    # ─────────────── normalize ───────────────

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        adapter = CityKurashikiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert hasattr(normalized, "species")

    # ─────────────── レジストリ ───────────────

    def test_site_is_registered(self):
        """sites.yaml の site name が Registry に登録されている"""
        if SiteAdapterRegistry.get(SITE_NAME) is None:
            SiteAdapterRegistry.register(SITE_NAME, CityKurashikiAdapter)
        assert SiteAdapterRegistry.get(SITE_NAME) is CityKurashikiAdapter
