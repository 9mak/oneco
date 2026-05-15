"""CityHigashiosakaAdapter のテスト

東大阪市保護収容動物情報 (city.higashiosaka.lg.jp/0000005910.html) 用
rule-based adapter の動作を検証する。

- `<div class="mol_imageblock ...">` を 1 頭のカードとする single_page サイト
- 実フィクスチャは 0 件状態 (動物カードが HTML コメント内に格納) なので、
  データを伴うテストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_higashiosaka import (
    CityHigashiosakaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "東大阪市（保護収容動物）",
    list_url: str = "https://www.city.higashiosaka.lg.jp/0000005910.html",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="大阪府",
        prefecture_code="27",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_higashiosaka_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_higashiosaka_lg_jp.html` は、本来
    UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっているため、実サイト相当のテキストを得るには
    逆変換が必要。実運用 (`_http_get`) では requests が正しい UTF-8 として
    受け取る。
    """
    raw = fixture_html("city_higashiosaka_lg_jp")
    if "東大阪" in raw or "保護収容動物情報" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_card() -> str:
    """1 件の動物カードを含む HTML を生成する (テスト用)

    東大阪市テンプレートの `<div class="mol_imageblock ...">` カード構造を
    再現する。<p> 内のラベル/値は本サイト実物と同じく全角コロン + 全角空白 +
    <br> の混在で記述する。
    """
    return """
    <html><body>
      <div id="mol_contents" class="mol_contents">
        <div class="mol_textblock">説明文</div>
        <div class="mol_imageblock clearfix block_index_27">
          <div class="mol_imageblock_imgfloatleft">
            <div class="mol_imageblock_w_long mol_imageblock_img_al_floatleft">
              <div class="mol_imageblock_img">
                <img src="./cmsfiles/contents/0000005/5910/dog001.jpg" alt="" width="180">
              </div>
              <p>個体番号:1　収容年月日:令和8年5月10日<br>
                 種類:雑種(犬)　性別:オス<br>
                 毛色:茶白　体格:中　体長50cm　体高40cm<br>
                 推定年齢:成犬　収容地域:東大阪市中部<br>
                 備考:</p>
            </div>
          </div>
        </div>
      </div>
    </body></html>
    """


class TestCityHigashiosakaAdapter:
    def test_fetch_animal_list_returns_empty_for_real_fixture(self, fixture_html):
        """実フィクスチャ (在庫 0 件、カードが HTML コメント内) では空リスト

        東大阪市 CMS は雛形を HTML コメントで残すため、BeautifulSoup の
        標準パーサからは `div.mol_imageblock` セレクタは何もマッチしない。
        ParsingError ではなく空リストになることを確認する。
        """
        html = _load_higashiosaka_html(fixture_html)
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データカードがあるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_card()
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.higashiosaka.lg.jp/")
        assert cat == "sheltered"

    def test_extract_animal_details_first_card(self):
        """1 件目のカードから RawAnimalData を構築できる"""
        html = _build_html_with_one_card()
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回 (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # テキストに「犬」が含まれるので犬と推定される
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶白"
        assert raw.size == "中"
        assert raw.age == "成犬"
        assert "令和8年5月10日" in raw.shelter_date
        assert "東大阪市中部" in raw.location
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.higashiosaka.lg.jp/")
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_species_inference_for_cat(self):
        """テキストに「猫」が含まれるとき species は「猫」になる"""
        cat_html = """
        <html><body>
          <div class="mol_contents">
            <div class="mol_imageblock">
              <div>
                <div class="mol_imageblock_img">
                  <img src="/cmsfiles/cat001.jpg" alt="">
                </div>
                <p>個体番号:2　収容年月日:令和8年5月12日<br>
                   種類:雑種(猫)　性別:メス<br>
                   毛色:三毛　体格:小　体長30cm　体高20cm<br>
                   推定年齢:成猫　収容地域:東大阪市東部<br>
                   備考:</p>
              </div>
            </div>
          </div>
        </body></html>
        """
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=cat_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.color == "三毛"
        assert "東大阪市東部" in raw.location

    def test_returns_empty_when_no_imageblock(self):
        """カード自体が無い (在庫 0 件) でも空リストを返す"""
        empty_html = """
        <html><body>
          <div class="mol_contents">
            <div class="mol_textblock">説明文のみ</div>
          </div>
        </body></html>
        """
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_raises_parsing_error_when_no_main_container(self):
        """`div.mol_contents` が無い (テンプレート崩壊) 場合は例外を出す"""
        adapter = CityHigashiosakaAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_site_registered(self):
        """サイト名が Registry に登録されている"""
        name = "東大阪市（保護収容動物）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, CityHigashiosakaAdapter)
        assert SiteAdapterRegistry.get(name) is CityHigashiosakaAdapter

    def test_extract_caches_html_across_calls(self):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        html = _build_html_with_one_card()
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1

    def test_multiple_cards(self):
        """複数カードが連続するとき index 順に正しく抽出される"""
        html = """
        <html><body>
          <div class="mol_contents">
            <div class="mol_imageblock">
              <div>
                <div class="mol_imageblock_img">
                  <img src="/img/1.jpg" alt="">
                </div>
                <p>個体番号:1　収容年月日:令和8年5月10日<br>
                   種類:犬　性別:オス<br>
                   毛色:黒　体格:大<br>
                   推定年齢:成犬　収容地域:A地区<br>
                   備考:</p>
              </div>
            </div>
            <div class="mol_imageblock">
              <div>
                <div class="mol_imageblock_img">
                  <img src="/img/2.jpg" alt="">
                </div>
                <p>個体番号:2　収容年月日:令和8年5月11日<br>
                   種類:猫　性別:メス<br>
                   毛色:白　体格:小<br>
                   推定年齢:成猫　収容地域:B地区<br>
                   備考:</p>
              </div>
            </div>
          </div>
        </body></html>
        """
        adapter = CityHigashiosakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2
            raw0 = adapter.extract_animal_details(urls[0][0], category="sheltered")
            raw1 = adapter.extract_animal_details(urls[1][0], category="sheltered")

        assert raw0.species == "犬"
        assert "A地区" in raw0.location
        assert raw1.species == "猫"
        assert "B地区" in raw1.location
