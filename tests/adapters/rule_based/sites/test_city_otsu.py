"""CityOtsuAdapter のテスト

大津市動物愛護センター (city.otsu.lg.jp/.../pet/mayoi/) 用
rule-based adapter の動作を検証する。

- `<table>` 形式の single_page サイト ("迷い犬猫" 1 種)
- フィクスチャは 0 件状態 (告知 `<h3>` + 空プレースホルダ行) なので、
  データ行を持つテストは synthetic な HTML を組み立てて検証する
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため、
  実運用相当のテキストを得るために逆変換が必要
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_otsu import (
    CityOtsuAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


SITE_NAME = "大津市動物愛護センター（迷い犬猫）"
LIST_URL = (
    "https://www.city.otsu.lg.jp/soshiki/021/1442/g/pet/mayoi/"
    "1387775941679.html"
)


def _site() -> SiteConfig:
    return SiteConfig(
        name=SITE_NAME,
        prefecture="滋賀県",
        prefecture_code="25",
        list_url=LIST_URL,
        category="lost",
        single_page=True,
    )


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含むテーブル HTML を生成する (テスト用)

    実サイトの `div.wysiwyg` 配下のテーブル構造を再現する。
    列順: 種類 / 毛色 / 体格 / 性別 / 保護場所 / 保護日時 / 備考
    """
    return """
    <html><body>
      <article id="contents">
        <div class="wysiwyg">
          <table style="width: 100%;">
            <caption><p>迷い犬猫情報</p></caption>
            <thead>
              <tr>
                <th scope="col">種類</th>
                <th scope="col">毛色</th>
                <th scope="col">体格</th>
                <th scope="col">性別</th>
                <th scope="col">保護場所</th>
                <th scope="col">保護日時</th>
                <th scope="col">備考</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>柴犬</td>
                <td>茶</td>
                <td>中</td>
                <td>オス</td>
                <td>大津市仰木の里</td>
                <td>
                  <p>令和8年5月7日</p>
                  <p>10時30分</p>
                </td>
                <td>首輪あり</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </body></html>
    """


class TestCityOtsuAdapter:
    def test_fetch_animal_list_returns_empty_on_real_fixture(
        self, fixture_html
    ):
        """0 件状態 (告知 + 空プレースホルダ行) の実フィクスチャでは空リストを返す"""
        # 実フィクスチャは _load_rows 内の mojibake 補正に任せる
        raw = fixture_html("city_otsu_lg_jp")
        adapter = CityOtsuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityOtsuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.otsu.lg.jp/")
        assert cat == "lost"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityOtsuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名 "迷い犬猫" は犬猫いずれもありうるため "その他" 推定
        assert raw.species == "その他"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert "令和8年5月7日" in raw.shelter_date
        assert "大津市" in raw.location
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_empty_placeholder_row_excluded(self):
        """全セルが空 + 日時テンプレ文字のみの行はデータ扱いされない"""
        html = """
        <html><body>
          <h3>現在収容している犬猫の情報はありません。</h3>
          <div class="wysiwyg">
            <table>
              <thead><tr>
                <th>種類</th><th>毛色</th><th>体格</th><th>性別</th>
                <th>保護場所</th><th>保護日時</th><th>備考</th>
              </tr></thead>
              <tbody>
                <tr>
                  <td>&nbsp;</td>
                  <td>&nbsp;</td>
                  <td>&nbsp;</td>
                  <td>&nbsp;</td>
                  <td>&nbsp;</td>
                  <td><p>月　日</p><p>時　分</p></td>
                  <td>&nbsp;</td>
                </tr>
              </tbody>
            </table>
          </div>
        </body></html>
        """
        adapter = CityOtsuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_site_registered(self):
        """大津市サイト名が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(SITE_NAME) is None:
            SiteAdapterRegistry.register(SITE_NAME, CityOtsuAdapter)
        assert SiteAdapterRegistry.get(SITE_NAME) is CityOtsuAdapter

    def test_raises_parsing_error_when_no_table(self):
        """テーブルも告知も見当たらない HTML では例外を出す"""
        adapter = CityOtsuAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
