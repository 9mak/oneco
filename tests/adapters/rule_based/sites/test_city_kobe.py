"""CityKobeAdapter のテスト

神戸市動物管理センター (city.kobe.lg.jp/.../animal/zmenu/) 用
rule-based adapter の動作を検証する。

- `<table>` 形式の single_page サイト ("収容動物" 1 種)
- 1 ページ内に「収容犬一覧」「収容猫一覧」の 2 セクションが並び、
  各セクションに対応する動物テーブルが配置される (ことを想定)
- フィクスチャは 0 件状態 (告知文のみ / テーブル不在) なので、データ行
  を持つテストは synthetic な HTML を組み立てて検証する
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため、
  実運用相当のテキストを得るために逆変換が必要
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kobe import (
    CityKobeAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


SITE_NAME = "神戸市動物管理センター（収容動物）"
LIST_URL = (
    "https://www.city.kobe.lg.jp/a84140/kenko/health/hygiene/animal/zmenu/"
    "index.html"
)


def _site() -> SiteConfig:
    return SiteConfig(
        name=SITE_NAME,
        prefecture="兵庫県",
        prefecture_code="28",
        list_url=LIST_URL,
        category="sheltered",
        single_page=True,
    )


def _build_html_with_dog_and_cat() -> str:
    """1 件の収容犬 + 1 件の収容猫を含むテーブル HTML を生成する (テスト用)

    実サイトに動物が居る場合の典型的な構造を再現する:
      <h2>収容犬一覧</h2>
      <table>...</table>
      <h2>収容猫一覧</h2>
      <table>...</table>
    """
    return """
    <html><body>
      <div id="tmp_contents">
        <p>動物管理センターに収容した犬猫の情報を公開しています。</p>
        <h2>収容犬一覧</h2>
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
            <td><img src="/a84140/img/dog001.jpg" alt=""></td>
            <td>柴犬</td>
            <td>オス</td>
            <td>茶</td>
            <td>中</td>
            <td>神戸市中央区</td>
          </tr>
        </table>
        <h2>収容猫一覧</h2>
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
            <td>令和8年5月12日</td>
            <td><img src="/a84140/img/cat001.jpg" alt=""></td>
            <td>雑種</td>
            <td>メス</td>
            <td>三毛</td>
            <td>小</td>
            <td>神戸市東灘区</td>
          </tr>
        </table>
      </div>
    </body></html>
    """


class TestCityKobeAdapter:
    def test_fetch_animal_list_returns_empty_on_real_fixture(
        self, fixture_html
    ):
        """0 件状態 (告知文のみ / テーブル不在) の実フィクスチャでは空リストを返す"""
        # 実フィクスチャは _load_rows 内の mojibake 補正に任せる
        raw = fixture_html("city_kobe_lg_jp")
        adapter = CityKobeAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるときは仮想 URL のリストを返す (犬 1 + 猫 1 = 2 件)"""
        html = _build_html_with_dog_and_cat()
        adapter = CityKobeAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for i, (url, cat) in enumerate(result):
            assert url.endswith(f"#row={i}")
            assert url.startswith("https://www.city.kobe.lg.jp/")
            assert cat == "sheltered"

    def test_extract_animal_details_dog_row(self):
        """1 件目 (収容犬一覧 配下) のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_dog_and_cat()
        adapter = CityKobeAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # セクション見出し「収容犬一覧」配下なので "犬" と推定される
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert "令和8年5月10日" in raw.shelter_date
        assert "神戸市中央区" in raw.location
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.kobe.lg.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_animal_details_cat_row(self):
        """2 件目 (収容猫一覧 配下) のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_dog_and_cat()
        adapter = CityKobeAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        # セクション見出し「収容猫一覧」配下なので "猫" と推定される
        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.color == "三毛"
        assert raw.size == "小"
        assert "令和8年5月12日" in raw.shelter_date
        assert "神戸市東灘区" in raw.location
        assert raw.category == "sheltered"

    def test_returns_empty_when_only_header_rows(self):
        """ヘッダ行のみのテーブル (在庫 0 件) でも空リストを返す"""
        empty_html = """
        <html><body>
          <div id="tmp_contents">
            <h2>収容犬一覧</h2>
            <p>現在、収容した犬はいません。</p>
            <h2>収容猫一覧</h2>
            <p>現在、収容した猫はいません。</p>
          </div>
        </body></html>
        """
        adapter = CityKobeAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_site_registered(self):
        """神戸市サイト名が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(SITE_NAME) is None:
            SiteAdapterRegistry.register(SITE_NAME, CityKobeAdapter)
        assert SiteAdapterRegistry.get(SITE_NAME) is CityKobeAdapter

    def test_raises_parsing_error_when_no_main_container(self):
        """`#tmp_contents` 自体が無い (テンプレート崩壊) 場合は例外を出す"""
        adapter = CityKobeAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_caches_html_across_calls(self):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        html = _build_html_with_dog_and_cat()
        adapter = CityKobeAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1
