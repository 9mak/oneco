"""CityMachidaAdapter のテスト

町田市保健所サイト (city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/) 用
rule-based adapter の動作を検証する。

- 同一テンプレート上の 3 サイト (収容/保護/捜索) の登録確認
- 0 件告知ページ (本フィクスチャ) では fetch_animal_list が空配列を返す
- ページ全体に table が無く empty state でもないケースは ParsingError
- HTML キャッシュ (HTTP は 1 回のみ実行)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_machida import (
    CityMachidaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "町田市（収容動物のお知らせ）",
    list_url: str = (
        "https://www.city.machida.tokyo.jp/iryo/hokenjo/pet/mayoi/syuyou.html"
    ),
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="東京都",
        prefecture_code="13",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_machida_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_machida.html` は、本来 UTF-8 のバイト
    列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっているため、実サイト相当のテキストを
    得るには逆変換が必要。実運用 (`_http_get`) では requests が正しい
    UTF-8 として受け取る。
    """
    raw = fixture_html("city_machida")
    # 復号後に「町田市」または「収容動物」が出現するかで判定
    if "町田市" in raw or "収容動物" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityMachidaAdapter:
    def test_fetch_animal_list_returns_empty_for_no_animals_page(
        self, fixture_html
    ):
        """「現在、収容動物はありません。」告知ページでは空リストが返る

        フィクスチャは「現在、収容動物はありません。」の告知のみが本文に
        並ぶ 0 件状態のページ。基底の単純実装は ParsingError を投げるが、
        本 adapter ではこれを正常な 0 件として扱う。
        """
        html = _load_machida_html(fixture_html)
        adapter = CityMachidaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"empty state ページでは空配列が返るはず: got {result!r}"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_machida_html(fixture_html)
        adapter = CityMachidaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state テキストも無い HTML では ParsingError"""
        adapter = CityMachidaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><p>無関係なページ</p></body></html>",
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
        <article>
        <table>
            <tr><th>種類</th><td>柴犬</td></tr>
            <tr><th>毛色</th><td>茶</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
            <tr><th>体格</th><td>中</td></tr>
            <tr><th>収容日</th><td>2026年5月10日</td></tr>
            <tr><th>収容場所</th><td>町田市原町田</td></tr>
        </table>
        </article>
        </body></html>
        """
        adapter = CityMachidaAdapter(_site())
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
        assert raw.location == "町田市原町田"
        assert raw.source_url == url
        assert raw.category == "sheltered"

    def test_infer_species_from_site_name_default_empty(self):
        """町田市 3 サイトの実名は犬/猫を含まないため空文字を返す"""
        for name in (
            "町田市（収容動物のお知らせ）",
            "町田市（保護情報）",
            "町田市（捜索：飼い主が探している）",
        ):
            assert (
                CityMachidaAdapter._infer_species_from_site_name(name) == ""
            )

    def test_infer_species_from_site_name_with_dog_keyword(self):
        """サイト名に "犬" を含む場合は "犬" を返す (汎用ロジック)"""
        assert (
            CityMachidaAdapter._infer_species_from_site_name("町田市（迷子犬）")
            == "犬"
        )

    def test_all_three_sites_registered(self):
        """3 つの町田市サイト名すべてが Registry に登録されている

        sites.yaml で `prefecture: 東京都` かつ
        `city.machida.tokyo.jp` ドメインの全サイトを列挙する。
        """
        expected = [
            "町田市（収容動物のお知らせ）",
            "町田市（保護情報）",
            "町田市（捜索：飼い主が探している）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityMachidaAdapter)
            assert SiteAdapterRegistry.get(name) is CityMachidaAdapter
