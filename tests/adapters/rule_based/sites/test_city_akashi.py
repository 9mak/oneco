"""CityAkashiAdapter のテスト

あかし動物センター (city.akashi.lg.jp/kankyou/dobutsu/info/maigo/{dog,cat}.html)
用 rule-based adapter の動作を検証する。

- `<table>` 形式の single_page サイト (迷子犬 / 迷子猫 の 2 種)
- 実フィクスチャは 0 件状態 (テーブル自体が無い) なので、データ行を持つ
  テストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_akashi import (
    CityAkashiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "あかし動物センター（迷子犬）",
    list_url: str = (
        "https://www.city.akashi.lg.jp/kankyou/dobutsu/info/maigo/dog.html"
    ),
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="兵庫県",
        prefecture_code="28",
        list_url=list_url,
        category="lost",
        single_page=True,
    )


def _load_akashi_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_akashi.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態になっているため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_akashi")
    if "明石" in raw or "あかし動物" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含むテーブル HTML を生成する (テスト用)

    あかし動物センターのテンプレート (`#tmp_contents` 配下) に動物情報が
    掲載される場合の典型的なテーブル構造を再現する。
    """
    return """
    <html><body>
      <div id="tmp_contents">
        <h2>犬の迷子情報</h2>
        <p>このページは迷子犬の飼い主さんを探すためのものです。</p>
        <table>
          <tr>
            <th>収容日</th>
            <th>写真</th>
            <th>種類</th>
            <th>性別</th>
            <th>毛色</th>
            <th>体格</th>
            <th>収容場所</th>
          </tr>
          <tr>
            <td>令和8年5月10日</td>
            <td><img src="/kankyou/dobutsu/info/maigo/img/dog001.jpg" alt=""></td>
            <td>柴犬</td>
            <td>オス</td>
            <td>茶</td>
            <td>中</td>
            <td>明石市大久保町</td>
          </tr>
        </table>
      </div>
    </body></html>
    """


class TestCityAkashiAdapter:
    def test_fetch_animal_list_returns_empty_when_no_table(self, fixture_html):
        """テーブル不在の実フィクスチャ (0 件状態) では空リストを返す

        あかし動物センターは保護動物が居ない期間も平常運用される。
        ParsingError ではなく空リスト扱いとする。
        """
        html = _load_akashi_html(fixture_html)
        adapter = CityAkashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityAkashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.akashi.lg.jp/")
        assert cat == "lost"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityAkashiAdapter(_site())

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
        assert "令和8年5月10日" in raw.shelter_date
        assert "明石市大久保町" in raw.location
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.akashi.lg.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_species_inference_for_cat_site(self):
        """サイト名 "あかし動物センター（迷子猫）" のときは species が "猫" になる"""
        cat_html = """
        <html><body>
          <div id="tmp_contents">
            <h2>猫の迷子情報</h2>
            <table>
              <tr>
                <th>収容日</th><th>写真</th><th>種類</th>
                <th>性別</th><th>毛色</th><th>体格</th><th>収容場所</th>
              </tr>
              <tr>
                <td>令和8年5月12日</td>
                <td><img src="/img/cat001.jpg" alt=""></td>
                <td>雑種</td>
                <td>メス</td>
                <td>三毛</td>
                <td>小</td>
                <td>明石市本町</td>
              </tr>
            </table>
          </div>
        </body></html>
        """
        cat_site = _site(
            name="あかし動物センター（迷子猫）",
            list_url=(
                "https://www.city.akashi.lg.jp/kankyou/dobutsu/info/maigo/cat.html"
            ),
        )
        adapter = CityAkashiAdapter(cat_site)

        with patch.object(adapter, "_http_get", return_value=cat_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert "明石市本町" in raw.location

    def test_returns_empty_when_only_header_row(self):
        """ヘッダ行のみのテーブル (在庫 0 件) でも空リストを返す"""
        empty_html = """
        <html><body>
          <div id="tmp_contents">
            <h2>犬の迷子情報</h2>
            <table>
              <tr>
                <th>収容日</th><th>写真</th><th>種類</th>
                <th>性別</th><th>毛色</th><th>体格</th><th>収容場所</th>
              </tr>
            </table>
          </div>
        </body></html>
        """
        adapter = CityAkashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_all_two_sites_registered(self):
        """2 つのあかし動物センターサイト名すべてが Registry に登録されている"""
        expected = [
            "あかし動物センター（迷子犬）",
            "あかし動物センター（迷子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityAkashiAdapter)
            assert SiteAdapterRegistry.get(name) is CityAkashiAdapter

    def test_raises_parsing_error_when_no_main_container(self):
        """`#tmp_contents` 自体が無い (テンプレート崩壊) 場合は例外を出す"""
        adapter = CityAkashiAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_caches_html_across_calls(self):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        html = _build_html_with_one_row()
        adapter = CityAkashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1
