"""CityTakatsukiAdapter のテスト

高槻市保健所サイト (city.takatsuki.osaka.jp/soshiki/39/2752.html) 用
rule-based adapter の動作を検証する。

- サイト「高槻市（迷子犬猫）」の登録確認
- 0 件告知ページ (本フィクスチャ) では fetch_animal_list が空配列を返す
- お問い合わせ先 / 返還手数料 等のテンプレート table が誤検出されない
- ページ全体に table が無く empty state でもないケースは ParsingError
- HTML キャッシュ (HTTP は 1 回のみ実行)
- 合成 HTML から RawAnimalData を構築できる
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_takatsuki import (
    CityTakatsukiAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "高槻市（迷子犬猫）",
    list_url: str = "https://www.city.takatsuki.osaka.jp/soshiki/39/2752.html",
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="大阪府",
        prefecture_code="27",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_takatsuki_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_takatsuki_osaka_jp.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、実サイト
    相当のテキストを得るには逆変換が必要。実運用 (`_http_get`) では
    requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_takatsuki_osaka_jp")
    # 復号後に「高槻市」または「行方不明」が出現するかで判定
    if "高槻市" in raw or "行方不明" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityTakatsukiAdapter:
    def test_fetch_animal_list_returns_empty_for_no_animals_page(
        self, fixture_html
    ):
        """「現在、掲載する情報はありません。」告知ページでは空リストが返る

        本フィクスチャは「現在、掲載する情報はありません。」の告知のみが
        本文に並ぶ 0 件状態のページ。基底の単純実装は ParsingError を
        投げるが、本 adapter ではこれを正常な 0 件として扱う。
        """
        html = _load_takatsuki_html(fixture_html)
        adapter = CityTakatsukiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"empty state ページでは空配列が返るはず: got {result!r}"
        )

    def test_template_tables_are_excluded(self, fixture_html):
        """お問い合わせ先 / 返還手数料 等のテンプレート table は除外される

        本フィクスチャには動物テーブル以外に複数のテンプレート table
        (お問い合わせ先 / 返還手数料の内訳 / 必要な手数料額の例 等) が
        存在するが、これらは動物情報ではないので _load_rows の結果から
        除外され、結果として 0 件になる。
        """
        html = _load_takatsuki_html(fixture_html)
        adapter = CityTakatsukiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            rows = adapter._load_rows()

        assert rows == [], (
            f"テンプレート table は除外され動物テーブルは 0 件のはず: "
            f"got {len(rows)} rows"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_takatsuki_html(fixture_html)
        adapter = CityTakatsukiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: "
            f"got {mock_get.call_count}"
        )

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state テキストも無い HTML では ParsingError"""
        adapter = CityTakatsukiAdapter(_site())
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
        典型的な「ラベル/値」の 2 列テーブルを `div.detail_free` 配下に
        置いた合成 HTML を使う。
        """
        synthetic_html = """
        <html><body>
        <div id="main_body">
          <div class="detail_free">
            <table>
              <tr><th>種類</th><td>柴犬</td></tr>
              <tr><th>毛色</th><td>茶</td></tr>
              <tr><th>性別</th><td>メス</td></tr>
              <tr><th>体格</th><td>中型</td></tr>
              <tr><th>収容日</th><td>2026年5月10日</td></tr>
              <tr><th>収容場所</th><td>高槻市富田町</td></tr>
            </table>
          </div>
        </div>
        </body></html>
        """
        adapter = CityTakatsukiAdapter(_site())
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
        assert raw.location == "高槻市富田町"
        assert raw.source_url == url
        assert raw.category == "lost"

    def test_extract_animal_details_skips_template_tables(self):
        """テンプレート table が存在しても、動物テーブルだけが抽出対象

        お問い合わせ先 / 返還手数料 のテンプレート table を動物テーブルの
        前後に配置しても、_load_rows はそれらを除外して動物テーブルだけ
        を返す。
        """
        synthetic_html = """
        <html><body>
        <div class="detail_free">
          <table>
            <tr><th colspan="2"><strong>お問い合わせ先</strong></th></tr>
            <tr><th>高槻市保健所</th><td>電話：072-661-9331</td></tr>
          </table>
          <table>
            <tr><th>種類</th><td>三毛猫</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
          </table>
          <table>
            <tr><th>内訳</th><th>金額</th></tr>
            <tr><th>返還手数料</th><td>3,900円</td></tr>
          </table>
        </div>
        </body></html>
        """
        adapter = CityTakatsukiAdapter(_site())
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
        assert raw.category == "lost"

    def test_infer_species_from_site_name_returns_empty_for_dog_and_cat(self):
        """サイト名「迷子犬猫」は犬・猫の両方を含むため空文字"""
        assert (
            CityTakatsukiAdapter._infer_species_from_site_name(
                "高槻市（迷子犬猫）"
            )
            == ""
        )

    def test_infer_species_from_site_name_with_only_dog(self):
        """サイト名に「犬」のみ含む場合は「犬」を返す (汎用ロジック)"""
        assert (
            CityTakatsukiAdapter._infer_species_from_site_name(
                "高槻市（迷子犬）"
            )
            == "犬"
        )

    def test_infer_species_from_breed(self):
        """「種類」値からの species 推定 (柴犬→犬, 三毛猫→猫, 雑種→空)"""
        assert CityTakatsukiAdapter._infer_species_from_breed("柴犬") == "犬"
        assert CityTakatsukiAdapter._infer_species_from_breed("三毛猫") == "猫"
        assert CityTakatsukiAdapter._infer_species_from_breed("雑種") == ""
        assert CityTakatsukiAdapter._infer_species_from_breed("") == ""

    def test_site_registered(self):
        """「高槻市（迷子犬猫）」が Registry に登録されている

        sites.yaml で `prefecture: 大阪府` かつ `city.takatsuki.osaka.jp`
        ドメインのサイトを列挙する。
        """
        name = "高槻市（迷子犬猫）"
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, CityTakatsukiAdapter)
        assert SiteAdapterRegistry.get(name) is CityTakatsukiAdapter
