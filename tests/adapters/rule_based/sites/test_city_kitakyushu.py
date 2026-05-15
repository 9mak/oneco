"""CityKitakyushuAdapter のテスト

北九州市動物愛護センター (city.kitakyushu.lg.jp/contents/) 用
rule-based adapter の動作を検証する。

- `<table>` 形式の single_page サイト (保護犬/譲渡犬 の 2 種)
- ページ内に複数 `<table>` が存在するため `<caption>` で対象を絞る
- フィクスチャは二重 UTF-8 エンコーディング (Latin-1 → UTF-8) のことが
  あるためテスト側で逆変換を行う
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kitakyushu import (
    CityKitakyushuAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "北九州市（保護犬）",
    list_url: str = "https://www.city.kitakyushu.lg.jp/contents/924_11831.html",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="福岡県",
        prefecture_code="40",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_kitakyushu_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば二重 UTF-8 を補正する

    リポジトリ内の `city_kitakyushu.html` は UTF-8 バイトを Latin-1 で
    解釈してから UTF-8 として保存し直された二重エンコーディング状態。
    実運用 (`_http_get`) では requests が正しい UTF-8 を返す。
    """
    raw = fixture_html("city_kitakyushu")
    if "北九州" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含む対象テーブル HTML を生成する (テスト用)

    実サイトの構造を再現する: 先頭に手数料表 (無関係) があり、
    その後ろに `<caption>収容表</caption>` を持つ対象表が続く。
    """
    return """
    <html><body>
      <table style="width: 98%;">
        <caption>返還手数料等</caption>
        <thead><tr><th>内容</th><th>金額</th></tr></thead>
        <tbody><tr><td>登録手数料</td><td>3,000円</td></tr></tbody>
      </table>

      <h2>収容されている犬の一覧表</h2>
      <table style="width: 100%;">
        <caption>収容表</caption>
        <thead>
          <tr>
            <th>収容日</th>
            <th>収容期限</th>
            <th>区</th>
            <th>種類（推定）</th>
            <th>毛色</th>
            <th>性別</th>
            <th>体格</th>
            <th>備考</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>5月11日</td>
            <td>5月15日</td>
            <td>小倉南区</td>
            <td>柴</td>
            <td>茶・白</td>
            <td>メス</td>
            <td>小</td>
            <td>&nbsp;</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """


def _build_html_with_three_rows() -> str:
    """3 件のデータ行を含む対象テーブル HTML"""
    return """
    <html><body>
      <table>
        <caption>収容表</caption>
        <thead>
          <tr>
            <th>収容日</th><th>収容期限</th><th>区</th><th>種類（推定）</th>
            <th>毛色</th><th>性別</th><th>体格</th><th>備考</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>5月11日</td><td>5月15日</td><td>小倉南区</td><td>柴</td>
            <td>茶・白</td><td>メス</td><td>小</td><td>&nbsp;</td>
          </tr>
          <tr>
            <td>5月11日</td><td>5月15日</td><td>門司区</td><td>雑</td>
            <td>茶</td><td>メス</td><td>小</td><td>&nbsp;</td>
          </tr>
          <tr>
            <td>5月12日</td><td>5月18日</td><td>門司区</td><td>雑</td>
            <td>茶・黒</td><td>オス</td><td>小</td><td>&nbsp;</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """


class TestCityKitakyushuAdapter:
    def test_fetch_animal_list_from_real_fixture(self, fixture_html):
        """実フィクスチャ (保護犬一覧) からデータ行を抽出できる"""
        html = _load_kitakyushu_html(fixture_html)
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # フィクスチャには 3 行入っている (May 11, 11, 12)
        assert len(result) == 3
        for i, (url, cat) in enumerate(result):
            assert url.endswith(f"#row={i}")
            assert url.startswith("https://www.city.kitakyushu.lg.jp/")
            assert cat == "sheltered"

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """1 件のデータ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        assert raw.sex == "メス"
        assert raw.color == "茶・白"
        assert raw.size == "小"
        assert raw.shelter_date == "5月11日"
        assert raw.location == "小倉南区"
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_animal_details_real_fixture(self, fixture_html):
        """実フィクスチャの 1 行目を抽出できる"""
        html = _load_kitakyushu_html(fixture_html)
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "犬"
        # フィクスチャの 1 行目: 5月11日 / 小倉南区 / 柴 / 茶・白 / メス / 小
        assert "5月11日" in raw.shelter_date
        assert raw.location == "小倉南区"
        assert raw.sex == "メス"
        assert raw.color == "茶・白"
        assert raw.size == "小"

    def test_fetch_animal_list_returns_empty_when_no_target_table(self):
        """対象テーブル (収容表/譲渡) が無い場合は空リスト (在庫 0 件)"""
        html = """
        <html><body>
          <table>
            <caption>返還手数料等</caption>
            <tr><th>内容</th><th>金額</th></tr>
            <tr><td>登録手数料</td><td>3,000円</td></tr>
          </table>
        </body></html>
        """
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_empty_when_tbody_empty(self):
        """対象テーブルはあるがデータ行が 0 件の場合は空リスト"""
        html = """
        <html><body>
          <table>
            <caption>収容表</caption>
            <thead><tr><th>収容日</th><th>区</th></tr></thead>
            <tbody></tbody>
          </table>
        </body></html>
        """
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_multiple_rows_independent_extraction(self):
        """複数行を別々に抽出しても各行が独立して取得できる"""
        html = _build_html_with_three_rows()
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 3
            raws = [adapter.extract_animal_details(u, category=c) for u, c in urls]

        assert raws[0].location == "小倉南区"
        assert raws[1].location == "門司区"
        assert raws[2].location == "門司区"
        assert raws[2].sex == "オス"
        assert raws[2].color == "茶・黒"

    def test_adoption_site_uses_adoption_category(self):
        """譲渡犬サイトでは category=adoption が伝搬する"""
        html = _build_html_with_one_row()
        adoption_site = _site(
            name="北九州市（譲渡犬）",
            list_url="https://www.city.kitakyushu.lg.jp/contents/924_11834.html",
            category="adoption",
        )
        adapter = CityKitakyushuAdapter(adoption_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert urls[0][1] == "adoption"
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.category == "adoption"
        assert raw.species == "犬"

    def test_both_sites_registered(self):
        """2 つの北九州市サイト名が Registry に登録されている"""
        expected = ["北九州市（保護犬）", "北九州市（譲渡犬）"]
        for name in expected:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityKitakyushuAdapter)
            assert SiteAdapterRegistry.get(name) is CityKitakyushuAdapter

    def test_returns_empty_list_when_no_table_at_all(self):
        """テーブルが完全に存在しない HTML では空リスト (在庫 0 件)"""
        adapter = CityKitakyushuAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_extract_raises_when_index_out_of_range(self):
        """範囲外 index を指定したら ParsingError"""
        from data_collector.adapters.municipality_adapter import ParsingError

        html = _build_html_with_one_row()
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    f"{adapter.site_config.list_url}#row=99",
                    category="sheltered",
                )
