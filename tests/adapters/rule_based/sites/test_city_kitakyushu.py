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
        # phone は北九州市保健福祉局生活衛生課の代表電話を全件共通利用 (2026-05 観測)
        assert raw.phone == "093-581-1800"

    def test_extract_animal_details_real_fixture(self, fixture_html):
        """実フィクスチャの 1 行目を抽出できる"""
        html = _load_kitakyushu_html(fixture_html)
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "犬"
        # フィクスチャの 1 行目: 5月11日 / 小倉南区 / 柴 / 茶・白 / メス / 小
        # 「種類」列 (柴) は species ではなく品種(breed)として保存される
        assert raw.breed == "柴"
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


def _build_adoption_html_with_one_row() -> str:
    """譲渡犬テーブル (caption=「譲渡対象の成犬の一覧」) を含む HTML

    実サイト (924_11834.html) の構造を再現:
    列: 番号(愛称) / 種類 / 性別 / 毛色 / 推定生年 / フィラリア検査 / 備考 / 写真
    写真列は <a href="/files/xxx.jpg">写真N</a> 形式 (img タグではなくリンク)。
    """
    return """
    <html><body>
      <table>
        <caption>譲渡対象の成犬の一覧</caption>
        <thead>
          <tr>
            <th>番号<br>（愛称）</th>
            <th>種類</th>
            <th>性別</th>
            <th>毛色</th>
            <th>推定生年</th>
            <th>フィラリア検査</th>
            <th>備考</th>
            <th>写真</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><p>A24135<br>（アポロ）</p></td>
            <td>雑種</td>
            <td>オス<br>（去勢済）</td>
            <td>茶白</td>
            <td>2017年</td>
            <td>強陽性</td>
            <td><p>受付中</p><p>人懐っこい性格です。</p></td>
            <td>
              <p><a href="/files/001133183.jpg">写真1</a></p>
              <p><a href="/files/001133184.jpg">写真2</a></p>
              <p><a href="/files/001149263.jpg">写真3</a></p>
            </td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """


class TestCityKitakyushuAdoptionTable:
    """譲渡犬テーブル (列構造が保護犬と異なる) の抽出を検証"""

    @staticmethod
    def _adoption_site() -> SiteConfig:
        return SiteConfig(
            name="北九州市（譲渡犬）",
            prefecture="福岡県",
            prefecture_code="40",
            list_url="https://www.city.kitakyushu.lg.jp/contents/924_11834.html",
            category="adoption",
            single_page=True,
        )

    def test_age_extracted_from_birth_year_column(self):
        """譲渡犬の「推定生年」列 (例: 2017年) を age として抽出する"""
        html = _build_adoption_html_with_one_row()
        adapter = CityKitakyushuAdapter(self._adoption_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.age == "2017年"

    def test_image_urls_extracted_from_photo_anchors(self):
        """譲渡犬の「写真」列の <a href="*.jpg"> から画像 URL を抽出する"""
        html = _build_adoption_html_with_one_row()
        adapter = CityKitakyushuAdapter(self._adoption_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.image_urls == [
            "https://www.city.kitakyushu.lg.jp/files/001133183.jpg",
            "https://www.city.kitakyushu.lg.jp/files/001133184.jpg",
            "https://www.city.kitakyushu.lg.jp/files/001149263.jpg",
        ]

    def test_adoption_columns_correctly_mapped(self):
        """譲渡犬テーブルでは保護犬と異なる列順を正しくマッピングする

        保護犬列: shelter_date(0) / 期限(1) / 区(2) / 種類(3) / 毛色(4) / 性別(5) / 体格(6)
        譲渡犬列: 番号(0) / 種類(1) / 性別(2) / 毛色(3) / 推定生年(4) / フィラリア(5) / 備考(6) / 写真(7)
        """
        html = _build_adoption_html_with_one_row()
        adapter = CityKitakyushuAdapter(self._adoption_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        # 譲渡犬テーブルでは性別は col=2, 毛色は col=3
        assert "オス" in raw.sex
        assert raw.color == "茶白"
        # 保護犬テーブルにある「区」「収容日」「体格」列は譲渡犬テーブルには無い
        assert raw.size == ""
        assert raw.shelter_date == ""
        # サイト名から species=犬 と推定する既存挙動は維持
        assert raw.species == "犬"
        # phone は引き続き共通の代表電話
        assert raw.phone == "093-581-1800"

    def test_shelter_table_still_has_no_age_or_images(self):
        """保護犬テーブル (構造的に age/image 無し) の挙動は変更しない

        実サイトの保護犬ページには年齢列も画像も存在しないため、
        age='' / image_urls=[] のままが正しい (回帰防止)。
        """
        html = _build_html_with_one_row()
        adapter = CityKitakyushuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.age == ""
        assert raw.image_urls == []
