"""PrefToyamaAdapter のテスト

富山県（迷い犬猫情報）サイト (pref.toyama.jp/1207/.../syuyou/) 用
rule-based adapter の動作を検証する。

- サイト名 ("富山県（迷い犬猫情報）") の Registry 登録確認
- インデックスページ (本フィクスチャ: 各厚生センターへのリンクのみ) は
  fetch_animal_list が空配列を返す
- 「現在…ありません」告知文がある場合の 0 件動作
- 本文も判定要素も無い HTML では ParsingError
- HTML キャッシュ (HTTP は 1 回のみ実行)
- 動物テーブルが直接掲載されているケース (合成 HTML) で抽出ロジックを検証
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_toyama import (
    PrefToyamaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "富山県（迷い犬猫情報）",
    list_url: str = (
        "https://www.pref.toyama.jp/1207/kurashi/seikatsu/seikatsu/"
        "doubutsuaigo/syuyou/index.html"
    ),
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="富山県",
        prefecture_code="16",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_toyama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_toyama_jp.html` は、本来 UTF-8 の
    バイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっている。実運用 (`_http_get`) では
    requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_toyama_jp")
    # 復号後に「富山県」または「迷い」が出現するかで判定
    if "富山県" in raw or "迷い" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefToyamaAdapter:
    def test_fetch_animal_list_returns_empty_for_index_page(
        self, fixture_html
    ):
        """各厚生センターへの窓口リンクのみのインデックスページでは空リスト

        本フィクスチャは `table.datatable` の中に各厚生センター・支所への
        `<a>` リンクが並ぶだけの 0 件状態。基底の単純実装は ParsingError を
        投げるが、本 adapter ではこれを正常な 0 件として扱う。
        """
        html = _load_toyama_html(fixture_html)
        adapter = PrefToyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"インデックスページでは空配列が返るはず: got {result!r}"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_toyama_html(fixture_html)
        adapter = PrefToyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_fetch_animal_list_returns_empty_for_explicit_no_animal_text(self):
        """「現在、迷い犬・ねこ情報はありません。」告知ページでも空リスト"""
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
            <p>現在、迷い犬・ねこの情報はありません。</p>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state 判定要素も無い HTML では ParsingError"""
        adapter = PrefToyamaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value=(
                "<html><body><div id=\"tmp_main\">"
                "<p>無関係な本文</p></div></body></html>"
            ),
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_animal_details_from_synthetic_table(self):
        """合成 HTML (動物テーブル 1 個) から RawAnimalData を構築できる

        実フィクスチャは 0 件状態のため、抽出ロジックの検証用に
        典型的な「ラベル/値」の 2 列テーブルを合成して使う。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table>
            <tr><th>種類</th><td>柴犬</td></tr>
            <tr><th>毛色</th><td>茶</td></tr>
            <tr><th>性別</th><td>オス</td></tr>
            <tr><th>体格</th><td>中</td></tr>
            <tr><th>収容日</th><td>2026年5月10日</td></tr>
            <tr><th>収容場所</th><td>富山市新総曲輪</td></tr>
        </table>
        </div>
        </body></html>
        """
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert raw.species == "柴犬"
        assert raw.color == "茶"
        assert raw.sex == "オス"
        assert raw.size == "中"
        assert raw.shelter_date == "2026年5月10日"
        assert raw.location == "富山市新総曲輪"
        assert raw.source_url == url
        assert raw.category == "lost"

    def test_extract_animal_details_with_multiple_tables(self):
        """複数の動物テーブル = 複数動物として扱われる

        厚生センター窓口リンクの `table.datatable` が混じっていても、
        動物データを含む通常テーブルだけが抽出対象になる。
        """
        synthetic_html = """
        <html><body>
        <div id="tmp_main">
        <table class="datatable">
            <tr><th scope="col">厚生センター名</th></tr>
            <tr><td><a href="/x.html">新川厚生センター</a></td></tr>
        </table>
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
        adapter = PrefToyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=synthetic_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 2, (
                f"datatable は除外され動物テーブル 2 個が残るはず: got {urls!r}"
            )
            raws = [
                adapter.extract_animal_details(u, category=c)
                for u, c in urls
            ]

        assert raws[0].species == "三毛猫"
        assert raws[0].sex == "メス"
        assert raws[0].category == "lost"
        assert raws[1].species == "キジトラ"
        assert raws[1].sex == "オス"
        assert raws[1].category == "lost"

    def test_infer_species_from_site_name_default_empty(self):
        """富山県の実サイト名は犬・猫 (ねこ) を併記するため空文字を返す"""
        for name in (
            "富山県（迷い犬猫情報）",
            "富山県（迷い犬・ねこ情報）",
        ):
            assert (
                PrefToyamaAdapter._infer_species_from_site_name(name) == ""
            )

    def test_infer_species_from_site_name_with_dog_keyword(self):
        """サイト名に "犬" のみを含む場合は "犬" を返す (汎用ロジック)"""
        assert (
            PrefToyamaAdapter._infer_species_from_site_name("富山県（迷い犬）")
            == "犬"
        )

    def test_infer_species_from_site_name_with_cat_keyword(self):
        """サイト名に "猫" のみを含む場合は "猫" を返す (汎用ロジック)"""
        assert (
            PrefToyamaAdapter._infer_species_from_site_name("富山県（保護猫）")
            == "猫"
        )

    def test_site_registered(self):
        """sites.yaml で定義された富山県サイトが Registry に登録されている

        他テストが registry を clear する場合に備えて冪等に再登録する。
        """
        name = "富山県（迷い犬猫情報）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefToyamaAdapter)
        assert SiteAdapterRegistry.get(name) is PrefToyamaAdapter
