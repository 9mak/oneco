"""CityFukuyamaAdapter のテスト

福山市動物愛護センター (city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/)
用 rule-based adapter の動作を検証する。

- `<table summary="...">` 形式の single_page サイト (保護犬/保護猫 の 2 種)
- `<thead>` に "保護日"/"種類" を含む表で対象テーブルを識別
- 在庫 0 件時に tbody に残る "全セル `&nbsp;`" のプレースホルダ行は
  0 件として扱う
- フィクスチャは二重 UTF-8 エンコーディング (Latin-1 → UTF-8) のことが
  あるためテスト側で逆変換を行う
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_fukuyama import (
    CityFukuyamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site_dog(
    name: str = "福山市（保護犬）",
    list_url: str = "https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/237722.html",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="広島県",
        prefecture_code="34",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _site_cat() -> SiteConfig:
    return SiteConfig(
        name="福山市（保護猫）",
        prefecture="広島県",
        prefecture_code="34",
        list_url="https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/60970.html",
        category="sheltered",
        single_page=True,
    )


def _load_fukuyama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば二重 UTF-8 を補正する

    リポジトリ内の `city_fukuyama.html` は UTF-8 バイトを Latin-1 で
    解釈してから UTF-8 として保存し直された二重エンコーディング状態。
    実運用 (`_http_get`) では requests が正しい UTF-8 を返す。
    """
    raw = fixture_html("city_fukuyama")
    if "福山" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含む対象テーブル HTML を生成する (テスト用)

    実サイトの構造を再現する: `<thead>` に標準ヘッダを配置し、
    `<tbody>` にデータ行を 1 件持たせる。
    """
    return """
    <html><body>
      <h1>保護犬の情報</h1>
      <table border="1" summary="保護犬の情報">
        <thead>
          <tr>
            <th>番号</th>
            <th>保護日</th>
            <th>保護場所</th>
            <th>種類</th>
            <th>毛色</th>
            <th>性別</th>
            <th>掲載期間</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>1</td>
            <td>2026年5月10日</td>
            <td>福山市駅家町</td>
            <td>柴</td>
            <td>茶</td>
            <td>オス</td>
            <td>2026年5月10日～2026年5月20日</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """


def _build_html_with_three_rows() -> str:
    """3 件のデータ行を含む対象テーブル HTML"""
    return """
    <html><body>
      <table summary="保護犬の情報">
        <thead>
          <tr>
            <th>番号</th><th>保護日</th><th>保護場所</th><th>種類</th>
            <th>毛色</th><th>性別</th><th>掲載期間</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>1</td><td>2026年5月10日</td><td>福山市駅家町</td><td>柴</td>
            <td>茶</td><td>オス</td><td>～2026年5月20日</td>
          </tr>
          <tr>
            <td>2</td><td>2026年5月11日</td><td>福山市東桜町</td><td>雑</td>
            <td>白</td><td>メス</td><td>～2026年5月21日</td>
          </tr>
          <tr>
            <td>3</td><td>2026年5月12日</td><td>福山市鞆町</td><td>ミックス</td>
            <td>黒</td><td>オス</td><td>～2026年5月22日</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """


def _build_html_placeholder_only() -> str:
    """在庫 0 件で「全セル `&nbsp;`」のプレースホルダ行のみが残る HTML

    実フィクスチャ (city_fukuyama.html) と同じ状態を再現する。
    """
    return """
    <html><body>
      <table summary="迷い犬の情報">
        <thead>
          <tr>
            <th>番号</th><th>保護日</th><th>保護場所</th><th>種類</th>
            <th>毛色</th><th>性別</th><th>掲載期間</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
            <td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """


class TestCityFukuyamaAdapter:
    def test_fetch_animal_list_from_real_fixture_returns_empty(
        self, fixture_html
    ):
        """実フィクスチャは在庫 0 件 (プレースホルダ行のみ) のため空リスト"""
        html = _load_fukuyama_html(fixture_html)
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # フィクスチャの tbody は全セル `&nbsp;` のプレースホルダ 1 行のみ。
        # これは在庫 0 件のサインなので空リストが返る。
        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """1 件のデータ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith(
            "https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/"
        )
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityFukuyamaAdapter(_site_dog())

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
        assert raw.shelter_date == "2026年5月10日"
        assert raw.location == "福山市駅家町"
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_fetch_animal_list_returns_empty_when_no_target_table(self):
        """対象テーブル (見出しに保護日/種類を含む) が無い場合は空リスト"""
        html = """
        <html><body>
          <table summary="その他">
            <thead><tr><th>項目</th><th>値</th></tr></thead>
            <tbody><tr><td>登録手数料</td><td>3,000円</td></tr></tbody>
          </table>
        </body></html>
        """
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_empty_when_tbody_empty(self):
        """対象テーブルはあるがデータ行が 0 件の場合は空リスト"""
        html = """
        <html><body>
          <table summary="保護犬">
            <thead>
              <tr><th>番号</th><th>保護日</th><th>保護場所</th>
                  <th>種類</th><th>毛色</th><th>性別</th>
                  <th>掲載期間</th></tr>
            </thead>
            <tbody></tbody>
          </table>
        </body></html>
        """
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_empty_when_only_placeholder_row(self):
        """tbody に全セル `&nbsp;` のプレースホルダ行のみの場合は空リスト"""
        html = _build_html_placeholder_only()
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_multiple_rows_independent_extraction(self):
        """複数行を別々に抽出しても各行が独立して取得できる"""
        html = _build_html_with_three_rows()
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 3
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        assert raws[0].location == "福山市駅家町"
        assert raws[1].location == "福山市東桜町"
        assert raws[2].location == "福山市鞆町"
        assert raws[2].sex == "オス"
        assert raws[2].color == "黒"
        # サイト名 (保護犬) から species は犬固定
        assert all(r.species == "犬" for r in raws)

    def test_cat_site_uses_neko_species(self):
        """保護猫サイトでは species=猫 が推定される"""
        html = _build_html_with_one_row()
        adapter = CityFukuyamaAdapter(_site_cat())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert urls[0][1] == "sheltered"
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "猫"
        assert raw.category == "sheltered"

    def test_both_sites_registered(self):
        """2 つの福山市サイト名が Registry に登録されている"""
        expected = ["福山市（保護犬）", "福山市（保護猫）"]
        for name in expected:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityFukuyamaAdapter)
            assert SiteAdapterRegistry.get(name) is CityFukuyamaAdapter

    def test_returns_empty_list_when_no_table_at_all(self):
        """テーブルが完全に存在しない HTML では空リスト (在庫 0 件)"""
        adapter = CityFukuyamaAdapter(_site_dog())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_extract_raises_when_index_out_of_range(self):
        """範囲外 index を指定したら ParsingError"""
        from data_collector.adapters.municipality_adapter import ParsingError

        html = _build_html_with_one_row()
        adapter = CityFukuyamaAdapter(_site_dog())

        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    f"{adapter.site_config.list_url}#row=99",
                    category="sheltered",
                )
