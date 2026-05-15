"""PrefFukushimaAdapter のテスト

福島県動物愛護センター (pref.fukushima.lg.jp) 用 rule-based adapter
の動作を検証する。

- 1 ページに `<table>` (1 動物 = 1 table) が複数並ぶ single_page 形式
- 6 サイト (中通り/会津/相双 × 迷子犬/迷子猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_fukushima import (
    PrefFukushimaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="福島県（中通り 迷子犬）",
        prefecture="福島県",
        prefecture_code="07",
        list_url=("https://www.pref.fukushima.lg.jp/sec/21620a/honshomaigoinu.html"),
        category="lost",
        single_page=True,
    )


def _load_fukushima_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要なら mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_fukushima__maigo.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態のため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_fukushima__maigo")
    if "福島" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefFukushimaAdapter:
    def test_fetch_animal_list_returns_multiple_tables(self, fixture_html):
        """一覧ページから複数の動物 (仮想 URL) が抽出できる

        フィクスチャの main_body には 3 個の table が並ぶ
        (= 3 件の迷子情報)。
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 2, "少なくとも 2 件以上の動物が抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.fukushima.lg.jp/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(self, fixture_html, assert_raw_animal):
        """1 件目のテーブルから RawAnimalData が構築できる

        フィクスチャ 1 件目:
            保護日 (管理番号): 令和8年4月28日（火曜日）（n080428-1）
            保護場所:           伊達市梁川町広瀬町
            種類／体格:         雑／中
            毛の色／長さ:       茶白／中
            性別:               メス
            推定年月齢:         6歳
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # ラベルベース抽出値の検証
        assert raw.sex == "メス"
        assert "6" in raw.age  # "6歳"
        # "茶白／中" の前半 (毛色) のみ取り出される
        assert raw.color == "茶白"
        # "雑／中" の後半が size に分離される
        assert raw.size == "中"
        # 場所末尾の全角空白等が除去されている
        assert "伊達市" in raw.location
        assert raw.location.strip() == raw.location
        # 保護日には "令和8年" が含まれる
        assert "令和" in raw.shelter_date
        # 画像 URL が絶対 URL に変換されている (1 件目は写真あり)
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_extract_second_row_handles_label_variants(self, fixture_html):
        """2 件目の表記揺れラベルでもフィールドが取り出される

        フィクスチャ 2 件目はラベルが "保護日（管理番号）" "種類/体格"
        "毛の色/長さ" "その他特徴等" のように半角/全角や末尾差異がある。
        正規化により同じフィールドにマップされることを確認する。
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) >= 2
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert raw.species == "犬"
        assert raw.sex == "メス"
        # "田村市都路町..." 等が場所として取れる
        assert "田村市" in raw.location
        # "茶／短" → 毛色は "茶"
        assert raw.color == "茶"
        # "雑／中" → size = "中"
        assert raw.size == "中"
        # 保護日は "令和8年5月" 含む
        assert "令和" in raw.shelter_date

    def test_all_six_sites_registered(self):
        """6 つの福島県サイト名すべてが Registry に登録されている"""
        expected = [
            "福島県（中通り 迷子犬）",
            "福島県（中通り 迷子猫）",
            "福島県（会津 迷子犬）",
            "福島県（会津 迷子猫）",
            "福島県（相双 迷子犬）",
            "福島県（相双 迷子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefFukushimaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefFukushimaAdapter

    def test_species_inferred_from_site_name_for_cat(self, fixture_html):
        """サイト名に "猫" が含まれる場合 species が "猫" になる"""
        html = _load_fukushima_html(fixture_html)
        cat_site = SiteConfig(
            name="福島県（会津 迷子猫）",
            prefecture="福島県",
            prefecture_code="07",
            list_url=("https://www.pref.fukushima.lg.jp/sec/21620a/aizumaigoneko.html"),
            category="lost",
            single_page=True,
        )
        adapter = PrefFukushimaAdapter(cat_site)
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.species == "猫"

    def test_raises_parsing_error_when_no_tables(self):
        """テーブルが見当たらない HTML では ParsingError 系例外を出す"""
        adapter = PrefFukushimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
