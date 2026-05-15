"""CityMitoAdapter のテスト

水戸市動物愛護センターサイト (city.mito.lg.jp/site/doubutsuaigo/) 用
rule-based adapter の動作を検証する。

- 同一テンプレート上の 2 サイト (迷子ペット情報 / 収容中の動物たち) の登録確認
- 0 件状態のインデックスページ (本フィクスチャ) では fetch_animal_list が
  空配列を返す
- ページ全体に table が無く empty state の判定要素も無いケースは ParsingError
- HTML キャッシュ (HTTP は 1 回のみ実行)
- データ行があるときは合成 HTML で抽出ロジックを検証
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_mito import (
    CityMitoAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "水戸市（迷子ペット情報）",
    list_url: str = (
        "https://www.city.mito.lg.jp/site/doubutsuaigo/list358.html"
    ),
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="茨城県",
        prefecture_code="08",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_mito_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_mito.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重
    エンコーディング状態になっているケースがあるため、実サイト相当の
    テキストを得るには逆変換が必要。実運用 (`_http_get`) では requests が
    正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_mito")
    # 復号後に「水戸市」または「迷子」が出現するかで判定
    if "水戸市" in raw or "迷子" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityMitoAdapter:
    def test_fetch_animal_list_returns_empty_for_index_page(
        self, fixture_html
    ):
        """サブカテゴリ案内のみのインデックスページでは空リストが返る

        フィクスチャは `div.info_list` のサブ記事リンクのみが本文に並ぶ
        0 件状態のページ。基底の単純実装は ParsingError を投げるが、
        本 adapter ではこれを正常な 0 件として扱う。
        """
        html = _load_mito_html(fixture_html)
        adapter = CityMitoAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"empty state ページでは空配列が返るはず: got {result!r}"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_mito_html(fixture_html)
        adapter = CityMitoAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_fetch_animal_list_returns_empty_for_explicit_no_animal_text(self):
        """「現在、収容動物はありません。」告知ページでも空リストを返す

        本文に動物テーブルが無く、明示的な 0 件告知文がある場合の検証。
        """
        synthetic_html = """
        <html><body>
        <div id="main_body">
            <p>現在、収容動物はおりません。</p>
        </div>
        </body></html>
        """
        adapter = CityMitoAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state 判定要素も無い HTML では ParsingError"""
        adapter = CityMitoAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value=(
                "<html><body><div id=\"main_body\">"
                "<p>無関係な本文</p></div></body></html>"
            ),
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_animal_details_from_synthetic_table(self):
        """合成 HTML (table 1 個) から RawAnimalData を構築できる

        実フィクスチャは 0 件状態のため、抽出ロジックの検証用に
        典型的な「ラベル/値」の 2 列テーブルを合成して使う。
        """
        synthetic_html = """
        <html><body>
        <div id="main_body">
        <table>
            <tr><th>種類</th><td>柴犬</td></tr>
            <tr><th>毛色</th><td>茶</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
            <tr><th>体格</th><td>中</td></tr>
            <tr><th>収容日</th><td>2026年5月10日</td></tr>
            <tr><th>収容場所</th><td>水戸市笠原町</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = CityMitoAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.species == "柴犬"
        assert raw.color == "茶"
        assert raw.sex == "メス"
        assert raw.size == "中"
        assert raw.shelter_date == "2026年5月10日"
        assert raw.location == "水戸市笠原町"
        assert raw.source_url == url
        assert raw.category == "lost"

    def test_extract_animal_details_with_multiple_tables(self):
        """複数 table = 複数動物として扱われる"""
        synthetic_html = """
        <html><body>
        <div id="main_body">
        <table>
            <tr><th>種類</th><td>三毛猫</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
        </table>
        <table>
            <tr><th>種類</th><td>キジトラ</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
        </table>
        </div>
        </body></html>
        """
        sheltered_site = _site(
            name="水戸市（愛護センター収容中の動物たち）",
            list_url="https://www.city.mito.lg.jp/site/doubutsuaigo/2043.html",
            category="sheltered",
        )
        adapter = CityMitoAdapter(sheltered_site)
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2
            raws = [
                adapter.extract_animal_details(u, category=c)
                for u, c in urls
            ]

        assert raws[0].species == "三毛猫"
        assert raws[0].sex == "メス"
        assert raws[0].category == "sheltered"
        assert raws[1].species == "キジトラ"
        assert raws[1].sex == "オス"
        assert raws[1].category == "sheltered"

    def test_infer_species_from_site_name_default_empty(self):
        """水戸市 2 サイトの実名は犬/猫を含まないため空文字を返す"""
        for name in (
            "水戸市（迷子ペット情報）",
            "水戸市（愛護センター収容中の動物たち）",
        ):
            assert (
                CityMitoAdapter._infer_species_from_site_name(name) == ""
            )

    def test_infer_species_from_site_name_with_dog_keyword(self):
        """サイト名に "犬" を含む場合は "犬" を返す (汎用ロジック)"""
        assert (
            CityMitoAdapter._infer_species_from_site_name("水戸市（迷子犬）")
            == "犬"
        )

    def test_infer_species_from_site_name_with_cat_keyword(self):
        """サイト名に "猫" を含む場合は "猫" を返す (汎用ロジック)"""
        assert (
            CityMitoAdapter._infer_species_from_site_name("水戸市（保護猫）")
            == "猫"
        )

    def test_all_two_sites_registered(self):
        """2 つの水戸市サイト名すべてが Registry に登録されている

        sites.yaml で `prefecture: 茨城県` かつ
        `city.mito.lg.jp` ドメインの全サイトを列挙する。
        """
        expected = [
            "水戸市（迷子ペット情報）",
            "水戸市（愛護センター収容中の動物たち）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityMitoAdapter)
            assert SiteAdapterRegistry.get(name) is CityMitoAdapter
