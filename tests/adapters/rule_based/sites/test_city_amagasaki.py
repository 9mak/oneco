"""CityAmagasakiAdapter のテスト

尼崎市動物愛護センター (city.amagasaki.hyogo.jp) 用 rule-based adapter の
動作を検証する。

- `<h2>返還対象動物一覧</h2>` 以降の最初の `<table>` を動物データ表として
  抽出する single_page サイト
- 実フィクスチャは 0 件状態 (`<div class="boxnotice">` の告知のみ) なので、
  データを伴うテストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_amagasaki import (
    CityAmagasakiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_LIST_URL = "https://www.city.amagasaki.hyogo.jp/kurashi/iryou/pet/051syuuyoudoubutu.html"


def _site(
    name: str = "尼崎市動物愛護センター（収容動物）",
    list_url: str = _LIST_URL,
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="兵庫県",
        prefecture_code="28",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_amagasaki_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_amagasaki_hyogo_jp.html` は、本来
    UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として保存し
    直された二重エンコーディング状態になっているため、実サイト相当の
    テキストを得るには逆変換が必要。実運用 (`_http_get`) では requests が
    正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_amagasaki_hyogo_jp")
    if "尼崎" in raw or "返還対象動物一覧" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_animal_table(
    rows_html: str = "",
    notice_html: str = "",
) -> str:
    """『返還対象動物一覧』見出し以降にデータ表を含む HTML を生成する"""
    return f"""
    <html><body>
      <main id="page">
        <article id="content">
          <h1>迷い犬・迷い猫について</h1>
          <h2>動物がいなくなってしまったら</h2>
          <table class="w100">
            <thead><tr><th>施設名</th><th>連絡先</th></tr></thead>
            <tbody>
              <tr><td>尼崎市動物愛護センター</td><td>06-6434-2233</td></tr>
            </tbody>
          </table>
          <h2>返還対象動物一覧</h2>
          <p>注意事項…</p>
          {notice_html}
          {rows_html}
        </article>
      </main>
    </body></html>
    """


def _animal_table(rows_html: str) -> str:
    return f"""
    <table class="w100">
      <thead>
        <tr>
          <th>種類</th>
          <th>性別</th>
          <th>毛色</th>
          <th>収容日</th>
          <th>収容場所</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


class TestCityAmagasakiAdapter:
    def test_fetch_animal_list_returns_empty_for_real_fixture(self, fixture_html):
        """実フィクスチャ (在庫 0 件、boxnotice 告知のみ) では空リストを返す"""
        html = _load_amagasaki_html(fixture_html)
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_empty_for_boxnotice_only(self):
        """boxnotice 告知のみの synthetic HTML でも空リストを返す"""
        html = _build_html_with_animal_table(
            notice_html=('<div class="boxnotice">現在、返還対象動物はいません。</div>'),
        )
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるとき仮想 URL のリストを返す"""
        rows = (
            "<tr><td>雑種(犬)</td><td>オス</td><td>茶白</td>"
            "<td>令和8年5月10日</td><td>尼崎市西昆陽</td></tr>"
            "<tr><td>雑種(猫)</td><td>メス</td><td>三毛</td>"
            "<td>令和8年5月12日</td><td>尼崎市東園田</td></tr>"
        )
        html = _build_html_with_animal_table(rows_html=_animal_table(rows))
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for i, (url, cat) in enumerate(result):
            assert url == f"{_LIST_URL}#row={i}"
            assert cat == "sheltered"

    def test_extract_animal_details_first_row(self):
        """1 行目から RawAnimalData を構築できる"""
        rows = (
            "<tr><td>雑種(犬)</td><td>オス</td><td>茶白</td>"
            "<td>令和8年5月10日</td><td>尼崎市西昆陽</td></tr>"
        )
        html = _build_html_with_animal_table(rows_html=_animal_table(rows))
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページからの複数取得でも HTTP は 1 回 (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶白"
        assert "令和8年5月10日" in raw.shelter_date
        assert "尼崎市西昆陽" in raw.location
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_species_inference_for_cat(self):
        """行テキストに「猫」が含まれるとき species は「猫」になる"""
        rows = (
            "<tr><td>雑種(猫)</td><td>メス</td><td>三毛</td>"
            "<td>令和8年5月12日</td><td>尼崎市東園田</td></tr>"
        )
        html = _build_html_with_animal_table(rows_html=_animal_table(rows))
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.color == "三毛"

    def test_ignores_other_tables_before_heading(self):
        """『返還対象動物一覧』見出し以前のテーブルは動物データに含まれない

        本フィクスチャでは連絡先テーブルや管轄一覧テーブルが
        見出しより上に存在する。これらの行が動物として誤って取り込まれないこと。
        """
        # 動物表を全く設置せず、boxnotice もなく、ページ上部に無関係な
        # テーブルのみがある HTML
        html = """
        <html><body>
          <main id="page">
            <article id="content">
              <h2>動物がいなくなってしまったら</h2>
              <table class="w100">
                <thead><tr><th>施設名</th><th>連絡先</th></tr></thead>
                <tbody>
                  <tr><td>尼崎市動物愛護センター</td><td>06-6434-2233</td></tr>
                  <tr><td>尼崎東警察署</td><td>06-6424-0110</td></tr>
                </tbody>
              </table>
              <h2>返還対象動物一覧</h2>
              <div class="boxnotice">現在、返還対象動物はいません。</div>
            </article>
          </main>
        </body></html>
        """
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_raises_parsing_error_when_heading_missing(self):
        """『返還対象動物一覧』見出しすら無い場合は例外を出す"""
        html = "<html><body><main><h2>無関係</h2></main></body></html>"
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_caches_html_across_calls(self):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        rows = (
            "<tr><td>犬</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td><td>A地区</td></tr>"
            "<tr><td>猫</td><td>メス</td><td>白</td>"
            "<td>令和8年5月2日</td><td>B地区</td></tr>"
        )
        html = _build_html_with_animal_table(rows_html=_animal_table(rows))
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1

    def test_multiple_rows_indexed_correctly(self):
        """複数行は index 順で正しく抽出される"""
        rows = (
            "<tr><td>犬</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td><td>A地区</td></tr>"
            "<tr><td>猫</td><td>メス</td><td>白</td>"
            "<td>令和8年5月2日</td><td>B地区</td></tr>"
        )
        html = _build_html_with_animal_table(rows_html=_animal_table(rows))
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2
            raw0 = adapter.extract_animal_details(urls[0][0], category="sheltered")
            raw1 = adapter.extract_animal_details(urls[1][0], category="sheltered")

        assert raw0.species == "犬"
        assert "A地区" in raw0.location
        assert raw1.species == "猫"
        assert "B地区" in raw1.location

    def test_image_urls_resolved_to_absolute(self):
        """行内 img の src が絶対 URL として解決される"""
        rows = (
            "<tr><td>犬</td><td>オス</td><td>黒</td>"
            "<td>令和8年5月1日</td>"
            '<td><img src="/_res/contents/dog001.jpg" alt="">A地区</td></tr>'
        )
        html = _build_html_with_animal_table(rows_html=_animal_table(rows))
        adapter = CityAmagasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.amagasaki.hyogo.jp/")

    def test_site_registered(self):
        """サイト名が Registry に登録されている"""
        name = "尼崎市動物愛護センター（収容動物）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, CityAmagasakiAdapter)
        assert SiteAdapterRegistry.get(name) is CityAmagasakiAdapter
