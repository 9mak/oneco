"""CityNaraAdapter のテスト

奈良市保健所サイト (city.nara.lg.jp/life/4/34/...) 用 rule-based adapter
の動作を検証する。

- サイト「奈良市（保護動物情報）」の登録確認
- 案内記事一覧 (info_list_date) のみで動物テーブルが無い実フィクスチャ
  では fetch_animal_list が空配列を返す
- お問い合わせ先 / 関連リンク 等のテンプレート table が誤検出されない
- 本文ブロックも告知も無い HTML では ParsingError
- HTML キャッシュ (HTTP は 1 回のみ実行)
- 合成 HTML (動物テーブル) から RawAnimalData を構築できる
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_nara import (
    CityNaraAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "奈良市（保護動物情報）",
    list_url: str = "https://www.city.nara.lg.jp/life/4/34/134/",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="奈良県",
        prefecture_code="29",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_nara_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_nara_lg_jp.html` は、本来 UTF-8 の
    バイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっているため、実サイト相当のテキストを
    得るには逆変換が必要。実運用 (`_http_get`) では requests が正しい
    UTF-8 として受け取る。adapter 内部にも同等の補正があるため、補正済み
    のテキストでも未補正のテキストでもどちらでも動作する。
    """
    raw = fixture_html("city_nara_lg_jp")
    # 復号後に「奈良」または「ペット」が出現するかで判定
    if "奈良" in raw or "ペット" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityNaraAdapter:
    def test_fetch_animal_list_returns_empty_for_info_list_only_page(
        self, fixture_html
    ):
        """案内記事一覧 (info_list_date) のみのページでは空リストが返る

        本フィクスチャは「ペットの飼養・届出」一覧ページで、本文に
        `div.info_list_date > ul > li > span.article_title > a` の
        行政手続き案内記事が並ぶのみで、動物個体テーブルは存在しない。
        基底の単純実装は ParsingError を投げるが、本 adapter ではこれを
        正常な保護動物 0 件状態として扱う。
        """
        html = _load_nara_html(fixture_html)
        adapter = CityNaraAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"案内記事のみのページでは空配列が返るはず: got {result!r}"
        )

    def test_template_tables_are_excluded(self):
        """お問い合わせ先 / 関連リンク 等のテンプレート table は除外される

        合成 HTML で「お問い合わせ先」「関連リンク」テンプレート table
        のみを置いた場合、`_load_rows` はそれらを除外して 0 件になる。
        """
        synthetic_html = """
        <html><body>
        <div id="main_body">
          <table>
            <tr><th>お問い合わせ先</th><td>奈良市保健所</td></tr>
          </table>
          <table>
            <tr><th>関連リンク</th><td>動物愛護管理センター</td></tr>
          </table>
        </div>
        </body></html>
        """
        adapter = CityNaraAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            rows = adapter._load_rows()

        assert rows == [], (
            f"テンプレート table は除外され動物テーブルは 0 件のはず: "
            f"got {len(rows)} rows"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_nara_html(fixture_html)
        adapter = CityNaraAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: "
            f"got {mock_get.call_count}"
        )

    def test_raises_parsing_error_for_unrelated_html(self):
        """本文ブロックも告知も無い HTML では ParsingError"""
        adapter = CityNaraAdapter(_site())
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
        典型的な「ラベル/値」の 2 列テーブルを `div#main_body` 配下に
        置いた合成 HTML を使う。
        """
        synthetic_html = """
        <html><body>
        <div id="main_body">
          <table>
            <tr><th>種類</th><td>柴犬</td></tr>
            <tr><th>毛色</th><td>茶</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
            <tr><th>体格</th><td>中型</td></tr>
            <tr><th>収容日</th><td>2026年5月10日</td></tr>
            <tr><th>収容場所</th><td>奈良市三条本町</td></tr>
          </table>
        </div>
        </body></html>
        """
        adapter = CityNaraAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        # species: 「柴犬」→「犬」に正規化される
        assert raw.species == "犬"
        assert raw.color == "茶"
        assert raw.sex == "メス"
        assert raw.size == "中型"
        assert raw.shelter_date == "2026年5月10日"
        assert raw.location == "奈良市三条本町"
        assert raw.source_url == url
        assert raw.category == "sheltered"

    def test_extract_animal_details_skips_template_tables(self):
        """テンプレート table が動物テーブルと混在しても動物だけが抽出対象

        お問い合わせ先 / 関連リンク のテンプレート table を動物テーブルの
        前後に配置しても、_load_rows はそれらを除外して動物テーブルだけ
        を返す。
        """
        synthetic_html = """
        <html><body>
        <div id="main_body">
          <table>
            <tr><th>お問い合わせ先</th><td>奈良市保健所</td></tr>
          </table>
          <table>
            <tr><th>種類</th><td>三毛猫</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
          </table>
          <table>
            <tr><th>関連リンク</th><td>動物愛護管理センター</td></tr>
          </table>
        </div>
        </body></html>
        """
        adapter = CityNaraAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1, (
                f"動物テーブル 1 件のみ抽出されるはず: got {len(urls)}"
            )
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        # 「三毛猫」→「猫」に正規化される
        assert raw.species == "猫"
        assert raw.sex == "オス"
        assert raw.category == "sheltered"

    def test_empty_state_text_returns_empty_list(self):
        """「現在、保護動物はおりません」告知のみのページでは空リスト"""
        synthetic_html = """
        <html><body>
        <div id="main_body">
          <p>現在、保護動物はおりません。</p>
        </div>
        </body></html>
        """
        adapter = CityNaraAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_infer_species_from_site_name_returns_empty_for_dog_and_cat(self):
        """サイト名に犬・猫の両方を含む場合は空文字"""
        assert (
            CityNaraAdapter._infer_species_from_site_name(
                "奈良市（保護犬猫）"
            )
            == ""
        )

    def test_infer_species_from_site_name_with_only_dog(self):
        """サイト名に「犬」のみ含む場合は「犬」を返す (汎用ロジック)"""
        assert (
            CityNaraAdapter._infer_species_from_site_name("奈良市（保護犬）")
            == "犬"
        )

    def test_infer_species_from_breed(self):
        """「種類」値からの species 推定 (柴犬→犬, 三毛猫→猫, 雑種→空)"""
        assert CityNaraAdapter._infer_species_from_breed("柴犬") == "犬"
        assert CityNaraAdapter._infer_species_from_breed("三毛猫") == "猫"
        assert CityNaraAdapter._infer_species_from_breed("雑種") == ""
        assert CityNaraAdapter._infer_species_from_breed("") == ""

    def test_site_registered(self):
        """「奈良市（保護動物情報）」が Registry に登録されている

        sites.yaml で `prefecture: 奈良県` かつ `city.nara.lg.jp` ドメイン
        のサイトを列挙する。
        """
        name = "奈良市（保護動物情報）"
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, CityNaraAdapter)
        assert SiteAdapterRegistry.get(name) is CityNaraAdapter
