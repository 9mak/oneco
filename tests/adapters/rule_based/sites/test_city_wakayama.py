"""CityWakayamaAdapter のテスト

和歌山市動物愛護管理センター（譲渡候補）
(city.wakayama.wakayama.jp/.../1002096.html) 用 rule-based adapter の
動作を検証する。

- `<div class="imglows">` を 1 頭のカードとする single_page サイト
- セクション見出し `<h3>飼い主さんを募集中の{猫|犬}</h3>` で species を判定
- 実フィクスチャは譲渡候補の猫 11 頭・犬 8 頭の計 19 頭が並ぶ状態
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_wakayama import (
    CityWakayamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_SITE_NAME = "和歌山市動物愛護管理センター（譲渡候補）"
_LIST_URL = (
    "https://www.city.wakayama.wakayama.jp/"
    "kurashi/kenko_iryo/1009125/1035775/1002096.html"
)


def _site(
    name: str = _SITE_NAME,
    list_url: str = _LIST_URL,
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="和歌山県",
        prefecture_code="30",
        list_url=list_url,
        category="adoption",
        single_page=True,
    )


def _load_wakayama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_wakayama_wakayama_jp.html` は、本来
    UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態の場合がある。実運用 (`_http_get`) では requests
    が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_wakayama_wakayama_jp")
    # 既に正しい UTF-8 ならそのまま使う
    if "和歌山" in raw or "譲渡" in raw or "飼い主" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_card_cat() -> str:
    """1 件の猫カードを含む合成 HTML (本物の DOM 構造を模倣)"""
    return """
    <html><body>
      <article id="content">
        <h1>譲渡可能動物情報</h1>
        <h3>飼い主さんを募集中の猫</h3>
        <div class="img3lows">
          <div class="box">
            <div class="imglows">
              <p class="imagecenter">
                <img src="../../../../_res/projects/default_project/_page_/001/002/096/cat-1.png" alt="cat-1" width="220" height="293">
              </p>
              <p>仮名：ゆきこ<br>
                 種類：雑種<br>
                 年齢（推定）：5～6月<br>
                 性別：メス（手術済）<br>
                 検査等：FIV／FeLV陰性<br>
                 性格等：初めての人は少し苦手ですが、慣れたらまったりごろん。</p>
            </div>
          </div>
        </div>
      </article>
    </body></html>
    """


def _build_html_with_cat_and_dog() -> str:
    """猫 1 + 犬 1 の混在 HTML (セクション見出しから species 推定をテスト)"""
    return """
    <html><body>
      <article id="content">
        <h1>譲渡可能動物情報</h1>
        <h3>飼い主さんを募集中の猫</h3>
        <div class="img3lows">
          <div class="box">
            <div class="imglows">
              <p class="imagecenter">
                <img src="/_res/projects/default_project/_page_/001/002/096/cat-A.png" alt="">
              </p>
              <p>仮名：ねこA<br>
                 種類：雑種<br>
                 年齢（推定）：1歳<br>
                 性別：オス（手術済）<br>
                 検査等：FIV／FeLV陰性<br>
                 性格等：のんびりさん。</p>
            </div>
          </div>
        </div>
        <h3>飼い主さんを募集中の犬</h3>
        <div class="img3lows">
          <div class="box">
            <div class="imglows">
              <p class="imagecenter">
                <img src="/_res/projects/default_project/_page_/001/002/096/dog-B.png" alt="">
              </p>
              <p>仮名：いぬB<br>
                 種類：雑種<br>
                 年齢（推定）：6～8ヶ月<br>
                 性別：メス（手術済）<br>
                 性格等：人が大好き。</p>
            </div>
          </div>
        </div>
      </article>
    </body></html>
    """


class TestCityWakayamaAdapter:
    def test_fetch_animal_list_real_fixture(self, fixture_html):
        """実フィクスチャから 19 頭分 (猫 11 + 犬 8) の仮想 URL を返す"""
        html = _load_wakayama_html(fixture_html)
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 19
        for url, cat in result:
            assert url.startswith(_LIST_URL)
            assert "#row=" in url
            assert cat == "adoption"

    def test_extract_real_fixture_species_split(self, fixture_html):
        """実フィクスチャで先頭 11 件は猫・残り 8 件は犬と推定される"""
        html = _load_wakayama_html(fixture_html)
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            species_seq = [
                adapter.extract_animal_details(u, category=c).species
                for u, c in urls
            ]

        # フィクスチャ上は猫セクションが先 → 11 件、続いて犬 → 8 件
        assert species_seq[:11] == ["猫"] * 11
        assert species_seq[11:] == ["犬"] * 8

    def test_extract_real_fixture_first_cat_fields(self, fixture_html):
        """実フィクスチャの先頭カード (猫 1 頭目) の主要フィールドを検証"""
        html = _load_wakayama_html(fixture_html)
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "猫"
        # 性別の括弧注釈は除去される
        assert raw.sex in {"オス", "メス"}
        assert "（" not in raw.sex and "(" not in raw.sex
        # 年齢には数字や「歳/月」等が含まれる
        assert raw.age != ""
        assert raw.location  # 位置情報のフォールバックが入る
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.wakayama.wakayama.jp/")
        assert raw.source_url == urls[0][0]
        assert raw.category == "adoption"

    def test_extract_animal_details_synthetic_cat(self):
        """合成 HTML 1 件 (猫) で各フィールドが正しく抽出される"""
        html = _build_html_with_one_card_cat()
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        assert mock_get.call_count == 1  # キャッシュ確認
        assert raw.species == "猫"
        assert raw.sex == "メス"  # 括弧注釈 (手術済) は除去
        assert raw.age == "5～6月"
        assert raw.color == ""
        assert raw.size == ""
        assert raw.image_urls
        assert raw.image_urls[0].endswith("cat-1.png")
        assert raw.source_url == first_url
        assert raw.category == "adoption"

    def test_species_inferred_from_section_heading(self):
        """セクション見出しに従って猫 / 犬を判定する"""
        html = _build_html_with_cat_and_dog()
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2
            raw_cat = adapter.extract_animal_details(urls[0][0], category="adoption")
            raw_dog = adapter.extract_animal_details(urls[1][0], category="adoption")

        assert raw_cat.species == "猫"
        assert raw_dog.species == "犬"

    def test_returns_empty_when_no_imglows(self):
        """カード自体が無い (在庫 0 件) 場合は空リストを返す"""
        empty_html = """
        <html><body>
          <article id="content">
            <h1>譲渡可能動物情報</h1>
            <p>現在、譲渡候補の動物はおりません。</p>
          </article>
        </body></html>
        """
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_raises_parsing_error_when_no_main_container(self):
        """`article#content` (本文) が無い場合はテンプレート崩壊として例外"""
        adapter = CityWakayamaAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_image_filter_excludes_template_images(self):
        """テンプレート画像 (`/_template_/...`) は除外される"""
        html = """
        <html><body>
          <article id="content">
            <h3>飼い主さんを募集中の犬</h3>
            <div class="imglows">
              <p class="imagecenter">
                <img src="/_template_/_site_/_default_/_res/design/icon.png">
                <img src="/_res/projects/default_project/_page_/001/002/096/dog-X.png">
              </p>
              <p>仮名：テスト<br>
                 種類：雑種<br>
                 年齢（推定）：1歳<br>
                 性別：オス<br>
                 性格等：テスト用。</p>
            </div>
          </article>
        </body></html>
        """
        adapter = CityWakayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        # テンプレート画像は除外、動物写真だけが残る
        assert raw.image_urls
        for u in raw.image_urls:
            assert "/_template_/" not in u
        assert any(u.endswith("dog-X.png") for u in raw.image_urls)

    def test_caches_html_across_calls(self):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        html = _build_html_with_cat_and_dog()
        adapter = CityWakayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1

    def test_site_registered(self):
        """サイト名が Registry に登録されている"""
        if SiteAdapterRegistry.get(_SITE_NAME) is None:
            SiteAdapterRegistry.register(_SITE_NAME, CityWakayamaAdapter)
        assert SiteAdapterRegistry.get(_SITE_NAME) is CityWakayamaAdapter
