"""CitySaitamaAdapter のテスト

さいたま市動物愛護ふれあいセンター (city.saitama.lg.jp/008/004/003/004/) 用
rule-based adapter の動作を検証する。

- `div.wysiwyg_area > div` カード形式の single_page サイト (保護犬 / 保護猫・その他)
- フィクスチャは在庫 0 件状態 (空欄テンプレートのみ) なので、データ行を持つ
  テストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_saitama import (
    CitySaitamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "さいたま市（保護犬）",
    list_url: str = "https://www.city.saitama.lg.jp/008/004/003/004/p003138.html",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="埼玉県",
        prefecture_code="11",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_saitama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_saitama.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態になっているため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_saitama")
    if "さいたま" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_card() -> str:
    """1 件の動物カードを含む HTML を生成する (テスト用)

    実サイトの `div.wysiwyg_area > div` カード構造を再現する。
    """
    return """
    <html><body>
      <div class="content_in" id="b2111_detail">
        <div class="wysiwyg_area">
          <h2>迷子の犬を保護しています</h2>
          <p>飼い主関係者以外の方からのお問い合わせはご遠慮ください。</p>
          <div>
            <p>管理番号 R07-001</p>
            <p>
              <img alt="dog" src="./p003138_d/img/001_s.jpg" /><br />
              写真の無断転載はご遠慮ください。
            </p>
            <ul>
              <li><strong>収容日： </strong>令和8年5月10日</li>
              <li><strong>公示（掲載）期限： </strong>令和8年5月15日</li>
              <li><strong>収容場所： </strong>さいたま市浦和区常盤</li>
              <li><strong>種類： </strong>柴犬</li>
              <li><strong>毛色： </strong>茶</li>
              <li><strong>性別： </strong>オス</li>
              <li><strong>体格： </strong>中</li>
              <li><strong>推定年齢： </strong>3歳</li>
              <li><strong>首輪： </strong>あり</li>
              <li><strong>備考：</strong>人懐こい</li>
            </ul>
          </div>
          <h2>返還申請について</h2>
          <p>飼い主様は早急に連絡してください。</p>
        </div>
        <div class="wysiwyg_area">
          <h2>地図情報</h2>
          <ul><li><a href="#">地図リンク</a></li></ul>
        </div>
      </div>
    </body></html>
    """


def _build_html_with_two_cards() -> str:
    """2 件のカードを含む HTML (複数件抽出の検証用)"""
    return """
    <html><body>
      <div class="content_in" id="b2111_detail">
        <div class="wysiwyg_area">
          <h2>迷子の犬を保護しています</h2>
          <div>
            <p>管理番号 R07-001</p>
            <p><img src="./img/dog001.jpg" /></p>
            <ul>
              <li><strong>収容日： </strong>令和8年5月10日</li>
              <li><strong>収容場所： </strong>さいたま市浦和区</li>
              <li><strong>種類： </strong>柴犬</li>
              <li><strong>毛色： </strong>茶</li>
              <li><strong>性別： </strong>オス</li>
              <li><strong>体格： </strong>中</li>
            </ul>
          </div>
          <div>
            <p>管理番号 R07-002</p>
            <p><img src="./img/dog002.jpg" /></p>
            <ul>
              <li><strong>収容日： </strong>令和8年5月12日</li>
              <li><strong>収容場所： </strong>さいたま市大宮区</li>
              <li><strong>種類： </strong>雑種</li>
              <li><strong>毛色： </strong>白黒</li>
              <li><strong>性別： </strong>メス</li>
              <li><strong>体格： </strong>小</li>
            </ul>
          </div>
        </div>
      </div>
    </body></html>
    """


class TestCitySaitamaAdapter:
    def test_fetch_animal_list_returns_empty_when_template_only(
        self, fixture_html
    ):
        """空欄テンプレートのみの実フィクスチャでは空リストを返す"""
        html = _load_saitama_html(fixture_html)
        adapter = CitySaitamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # 全 li が空欄のテンプレートカードのみ → 在庫 0 件扱い
        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ入りのカードがあるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_card()
        adapter = CitySaitamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.saitama.lg.jp/")
        assert cat == "sheltered"

    def test_fetch_animal_list_returns_multiple_rows(self):
        """2 件のカードがあるときは 2 件抽出される"""
        html = _build_html_with_two_cards()
        adapter = CitySaitamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for i, (url, cat) in enumerate(result):
            assert url.endswith(f"#row={i}")
            assert cat == "sheltered"

    def test_extract_animal_details_first_card(self):
        """1 件目のカードから RawAnimalData を構築できる"""
        html = _build_html_with_one_card()
        adapter = CitySaitamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert raw.age == "3歳"
        assert "令和8年5月10日" in raw.shelter_date
        assert "浦和区" in raw.location
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.saitama.lg.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_species_inference_for_cat_other_site(self):
        """サイト名 "さいたま市（保護猫・その他）" のときは species が "猫" になる"""
        html = _build_html_with_one_card()
        cat_site = _site(
            name="さいたま市（保護猫・その他）",
            list_url=(
                "https://www.city.saitama.lg.jp/008/004/003/004/p019971.html"
            ),
        )
        adapter = CitySaitamaAdapter(cat_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        # サイト名に "猫" を含むので species は "猫"
        assert raw.species == "猫"

    def test_all_two_sites_registered(self):
        """2 つのさいたま市サイト名すべてが Registry に登録されている"""
        expected = [
            "さいたま市（保護犬）",
            "さいたま市（保護猫・その他）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CitySaitamaAdapter)
            assert SiteAdapterRegistry.get(name) is CitySaitamaAdapter

    def test_returns_empty_when_no_wysiwyg_area(self):
        """`div.wysiwyg_area` が存在しない HTML では空リストを返す"""
        adapter = CitySaitamaAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            result = adapter.fetch_animal_list()
        assert result == []
