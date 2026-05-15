"""CitySendaiAdapter のテスト

仙台市動物管理センター (city.sendai.jp/.../joho/) 用 rule-based adapter
の動作を検証する。

- 1 ページに「`<h3>管理番号 ...</h3>` + `<table>`」の繰り返しで動物が
  並ぶ single_page サイト (譲渡犬/譲渡猫/譲渡子猫 の 3 種)
- フィクスチャ (`city_sendai.html`) には 3 件のデータが含まれる
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_sendai import (
    CitySendaiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "仙台市アニパル（譲渡犬）",
    list_url: str = (
        "https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/"
        "hogodobutsu/joho/inu.html"
    ),
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="宮城県",
        prefecture_code="04",
        list_url=list_url,
        category="adoption",
        single_page=True,
    )


def _load_sendai_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_sendai.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態になっているため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_sendai")
    if "仙台" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_animal() -> str:
    """1 件の動物データを含む HTML を生成する (テスト用)

    実サイトの `<h3>管理番号 ...</h3>` + `<table>` の構造を再現する。
    """
    return """
    <html><body>
      <div id="tmp_contents">
        <h2>譲渡犬情報（令和8年4月17日更新)</h2>
        <h3><strong>管理番号　D24018（愛称：平助）</strong></h3>
        <table border="1">
          <tbody>
            <tr>
              <td>
                <p><img alt="譲渡犬情報第D24018号-h"
                  src="/dobutsu/kurashi/shizen/petto/hogodobutsu/joho/images/d24018-h.jpg"
                  width="241" height="200" /></p>
              </td>
              <td>
                <p><strong>基本情報</strong></p>
                <p>　種類：柴犬</p>
                <p>　性別：去勢雄</p>
                <p>　年齢：10歳</p>
                <p>　体重：約16kg</p>
                <p>　毛色：茶</p>
              </td>
            </tr>
          </tbody>
        </table>
        <table border="1">
          <tbody>
            <tr>
              <td>フィラリア検査陰性、マイクロチップ装着済、去勢手術実施済。</td>
            </tr>
          </tbody>
        </table>
        <p>電話番号：022-258-1626</p>
      </div>
    </body></html>
    """


class TestCitySendaiAdapter:
    def test_fetch_animal_list_returns_three_rows_from_fixture(
        self, fixture_html
    ):
        """実フィクスチャからは 3 件のデータが抽出される"""
        html = _load_sendai_html(fixture_html)
        adapter = CitySendaiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        for i, (url, cat) in enumerate(result):
            assert url.endswith(f"#row={i}")
            assert url.startswith("https://www.city.sendai.jp/")
            assert cat == "adoption"

    def test_fetch_animal_list_returns_empty_when_no_h3(self):
        """「管理番号」を含む h3 が無いページでは空リストを返す (在庫 0 件)"""
        html = """
        <html><body>
          <div id="tmp_contents">
            <h2>譲渡犬情報</h2>
            <p>現在、譲渡対象の犬はいません。</p>
          </div>
        </body></html>
        """
        adapter = CitySendaiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_extract_animal_details_first_row_synthetic(self):
        """1 件のシンセティック HTML から RawAnimalData を構築できる"""
        html = _build_html_with_one_animal()
        adapter = CitySendaiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "去勢雄"
        assert raw.age == "10歳"
        assert raw.color == "茶"
        assert raw.size == "約16kg"
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.sendai.jp/")
        assert any("d24018-h" in u for u in raw.image_urls)
        # ページ全体の電話番号が抽出されている
        assert raw.phone == "022-258-1626"
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "adoption"

    def test_extract_animal_details_first_row_from_fixture(self, fixture_html):
        """実フィクスチャ 1 件目から期待される値が取れる"""
        html = _load_sendai_html(fixture_html)
        adapter = CitySendaiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        # フィクスチャ先頭は D24018 (柴犬・去勢雄・10歳・約16kg・茶)
        assert raw.species == "犬"
        assert raw.sex == "去勢雄"
        assert raw.age == "10歳"
        assert "茶" in raw.color
        assert "16" in raw.size
        # 画像 URL (d24018) が絶対化されて含まれる
        assert any("d24018" in u for u in raw.image_urls)
        for u in raw.image_urls:
            assert u.startswith("https://www.city.sendai.jp/")

    def test_species_inference_for_cat_site(self):
        """サイト名 "仙台市アニパル（譲渡猫）" のときは species が "猫" になる"""
        html = _build_html_with_one_animal()
        cat_site = _site(
            name="仙台市アニパル（譲渡猫）",
            list_url=(
                "https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/"
                "hogodobutsu/joho/neko.html"
            ),
        )
        adapter = CitySendaiAdapter(cat_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.species == "猫"

    def test_species_inference_for_kitten_site(self):
        """サイト名 "仙台市アニパル（譲渡子猫）" のときも species は "猫" になる"""
        html = _build_html_with_one_animal()
        koneko_site = _site(
            name="仙台市アニパル（譲渡子猫）",
            list_url=(
                "https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/"
                "hogodobutsu/joho/koneko.html"
            ),
        )
        adapter = CitySendaiAdapter(koneko_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.species == "猫"

    def test_all_three_sites_registered(self):
        """3 つの仙台市サイト名すべてが Registry に登録されている"""
        expected = [
            "仙台市アニパル（譲渡犬）",
            "仙台市アニパル（譲渡猫）",
            "仙台市アニパル（譲渡子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CitySendaiAdapter)
            assert SiteAdapterRegistry.get(name) is CitySendaiAdapter

    def test_returns_empty_when_only_unrelated_h3(self):
        """「管理番号」を含まない h3 のみのページでは空リストを返す"""
        html = """
        <html><body>
          <h3>犬の家族募集について</h3>
          <p>説明文</p>
          <table><tr><td>説明テーブル</td></tr></table>
        </body></html>
        """
        adapter = CitySendaiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_extract_all_three_rows_from_fixture(self, fixture_html):
        """フィクスチャの 3 件すべてが個別に抽出でき、種別/性別が取れる"""
        html = _load_sendai_html(fixture_html)
        adapter = CitySendaiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        # 3 件取得できても HTTP 呼び出しは 1 回に抑えられている (キャッシュ)
        assert mock_get.call_count == 1
        assert len(raws) == 3
        for raw in raws:
            assert raw.species == "犬"
            # 全件で性別 (去勢雄等) が取れている
            assert raw.sex
            # 各動物の画像 URL が抽出されている
            assert raw.image_urls

    def test_raises_parsing_error_when_row_index_out_of_range(self):
        """範囲外 row index を指定したら ParsingError を出す"""
        from data_collector.adapters.municipality_adapter import ParsingError

        html = _build_html_with_one_animal()
        adapter = CitySendaiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    f"{adapter.site_config.list_url}#row=99",
                    category="adoption",
                )
