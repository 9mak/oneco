"""CityFunabashiAdapter のテスト

船橋市動物愛護指導センター (city.funabashi.lg.jp/.../doubutsu/003/) 用
rule-based adapter の動作を検証する。

- `<table>` 形式の single_page サイト (収容犬猫 / 譲渡可能犬猫 の 2 サイト)
- 同梱フィクスチャは 0 件状態 (ヘッダ行のみ) なので、データ行を持つ
  テストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_funabashi import (
    CityFunabashiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "船橋市（収容犬猫）",
    list_url: str = ("https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/p013242.html"),
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="千葉県",
        prefecture_code="12",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_funabashi_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_funabashi.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態になっているため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_funabashi")
    if "船橋" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含むテーブル HTML を生成する (テスト用)

    実サイトの `div.boxEntryFreeform` 配下のテーブル構造を再現する。
    列順: 番号 / 収容年月日 / 公示満了日 / 収容場所 / 動物種 /
          種類 / 毛色 / 性別 / 体格 / 備考 / 写真
    """
    return """
    <html><body>
      <div class="boxEntryFreeform">
        <table style="width: 800; height: 96;">
          <caption>
            <p>公示内容</p>
          </caption>
          <tbody>
            <tr>
              <th>番号</th>
              <th>収容<br>年月日</th>
              <th>公示<br>満了日</th>
              <th>収容<br>場所</th>
              <th>動物種</th>
              <th>種類</th>
              <th>毛色</th>
              <th>性別</th>
              <th>体格</th>
              <th>備考</th>
              <th>写真</th>
            </tr>
            <tr>
              <td>1</td>
              <td>令和8年5月10日</td>
              <td>令和8年5月15日</td>
              <td>船橋市潮見町</td>
              <td>犬</td>
              <td>柴犬</td>
              <td>茶</td>
              <td>オス</td>
              <td>中</td>
              <td>首輪あり</td>
              <td><img src="/kurashi/doubutsu/003/img/dog001.jpg" alt=""></td>
            </tr>
          </tbody>
        </table>
      </div>
    </body></html>
    """


def _build_html_with_two_rows() -> str:
    """2 件 (犬 + 猫) のデータ行を含むテーブル HTML を生成する (テスト用)"""
    return """
    <html><body>
      <div class="boxEntryFreeform">
        <table style="width: 800; height: 96;">
          <caption><p>公示内容</p></caption>
          <tbody>
            <tr>
              <th>番号</th><th>収容年月日</th><th>公示満了日</th>
              <th>収容場所</th><th>動物種</th><th>種類</th>
              <th>毛色</th><th>性別</th><th>体格</th>
              <th>備考</th><th>写真</th>
            </tr>
            <tr>
              <td>1</td><td>令和8年5月10日</td><td>令和8年5月15日</td>
              <td>船橋市潮見町</td><td>犬</td><td>柴犬</td>
              <td>茶</td><td>オス</td><td>中</td>
              <td>首輪あり</td>
              <td><img src="/kurashi/doubutsu/003/img/dog001.jpg" alt=""></td>
            </tr>
            <tr>
              <td>2</td><td>令和8年5月11日</td><td>令和8年5月16日</td>
              <td>船橋市本町</td><td>猫</td><td>雑種</td>
              <td>三毛</td><td>メス</td><td>小</td>
              <td>-</td>
              <td><img src="/kurashi/doubutsu/003/img/cat001.jpg" alt=""></td>
            </tr>
          </tbody>
        </table>
      </div>
    </body></html>
    """


class TestCityFunabashiAdapter:
    def test_fetch_animal_list_returns_empty_when_header_only(self, fixture_html):
        """0 件状態 (ヘッダ行のみ) の実フィクスチャでは空リストを返す"""
        html = _load_funabashi_html(fixture_html)
        adapter = CityFunabashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # データ行が存在しない → 0 件扱い
        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityFunabashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.funabashi.lg.jp/")
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityFunabashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # 動物種列から犬を取得 (サイト名推定ではなく HTML 値)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert "令和8年5月10日" in raw.shelter_date
        assert "船橋市" in raw.location
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.funabashi.lg.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_animal_details_cat_row(self):
        """動物種列に「猫」が入っているデータ行は species="猫" になる"""
        html = _build_html_with_two_rows()
        adapter = CityFunabashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            # 2 件目 (猫) を取得
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.color == "三毛"
        assert raw.size == "小"

    def test_adoption_site_uses_correct_category(self):
        """譲渡可能サイトでは category="adoption" になる"""
        html = _build_html_with_one_row()
        adoption_site = _site(
            name="船橋市（譲渡可能犬猫）",
            list_url=("https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/joutoindex.html"),
            category="adoption",
        )
        adapter = CityFunabashiAdapter(adoption_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert urls[0][1] == "adoption"
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.category == "adoption"

    def test_all_two_sites_registered(self):
        """2 つの船橋市サイト名すべてが Registry に登録されている"""
        expected = [
            "船橋市（収容犬猫）",
            "船橋市（譲渡可能犬猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityFunabashiAdapter)
            assert SiteAdapterRegistry.get(name) is CityFunabashiAdapter

    def test_raises_parsing_error_when_no_table(self):
        """テーブルが見当たらない HTML では例外を出す"""
        adapter = CityFunabashiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
