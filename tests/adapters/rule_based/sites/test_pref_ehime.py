"""PrefEhimeAdapter のテスト

愛媛県動物愛護センター (pref.ehime.jp) 用 rule-based adapter の動作を検証する。

- 1 ページに `<table class="sp_table_wrap">` テーブルが並ぶ single_page 形式
- 2 サイト (収容中、譲渡予定) すべての登録確認
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で逆変換
- テーブル直前の `<p><strong>{月日} {市町村} {犬|猫|...}</strong></p>` から
  収容日 (月日) と species ヒントを取得
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_ehime import (
    PrefEhimeAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site_lost() -> SiteConfig:
    return SiteConfig(
        name="愛媛県動物愛護センター（収容中）",
        prefecture="愛媛県",
        prefecture_code="38",
        list_url="https://www.pref.ehime.jp/page/16976.html",
        category="lost",
        single_page=True,
    )


def _site_adoption() -> SiteConfig:
    return SiteConfig(
        name="愛媛県動物愛護センター（譲渡予定）",
        prefecture="愛媛県",
        prefecture_code="38",
        list_url="https://www.pref.ehime.jp/page/17125.html",
        category="adoption",
        single_page=True,
    )


class TestPrefEhimeAdapter:
    def test_fetch_animal_list_returns_one_animal(self, fixture_html):
        """フィクスチャから動物テーブル 1 件が抽出される

        `pref_ehime.html` には `<table class="sp_table_wrap">` のうち
        実データを保持するもの (tbody に td 行を含むもの) が 1 件、
        末尾に空の `<table class="datatable">` が 1 件あるが、後者は除外される。
        """
        html = fixture_html("pref_ehime")
        adapter = PrefEhimeAdapter(_site_lost())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1, "実データ 1 件が期待値"
        url, cat = result[0]
        assert "#row=0" in url
        assert url.startswith("https://www.pref.ehime.jp/page/16976.html")
        assert cat == "lost"

    def test_extract_first_animal(self, fixture_html):
        """1 件目から RawAnimalData を構築できる

        フィクスチャ内容:
            見出し  : "5月8日　八幡浜市　犬"
            場所    : "八幡浜市 大平"
            種類    : "バセットハウンド風"
            毛色    : "白茶"
            性別    : "メス"
            体格    : "中"
            画像    : /uploaded/image/65619.jpg, /uploaded/image/65620.jpg
            更新日  : 2026年5月8日
        """
        html = fixture_html("pref_ehime")
        adapter = PrefEhimeAdapter(_site_lost())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # species は見出しの "犬" から推定
        assert raw.species == "犬"
        # 場所はテーブル内 td (八幡浜市 + 大平) を空白区切りで取得
        assert "八幡浜市" in raw.location
        assert raw.color == "白茶"
        assert raw.sex == "メス"
        assert raw.size == "中"
        # 収容日: 見出しの "5月8日" + 更新日の年 "2026" -> 2026-05-08
        assert raw.shelter_date == "2026-05-08"
        # 画像 URL が絶対 URL に変換される
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert all("/uploaded/image/" in u for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == url
        assert raw.category == "lost"

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字が正しく復元される

        fixture には Latin-1 解釈された UTF-8 バイト列がそのまま残っている。
        adapter 側で逆変換しないと "八幡浜市" 等の漢字が一致しない。
        """
        html = fixture_html("pref_ehime")
        adapter = PrefEhimeAdapter(_site_lost())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert "八幡浜市" in raw.location
        assert raw.sex == "メス"
        assert raw.color == "白茶"

    def test_empty_page_returns_empty_list(self):
        """データテーブルが無いページ (在庫 0 件) でも例外を出さない"""
        empty_html = (
            "<html><head><title>愛媛県</title></head>"
            "<body><div id='main_body'>"
            "<h2>現在掲載中の情報はありません</h2>"
            "</div></body></html>"
        )
        adapter = PrefEhimeAdapter(_site_lost())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_table_without_tbody_rows_excluded(self):
        """tbody に td 行を持たない table は実データ扱いされない"""
        html = (
            "<html><head><title>愛媛県</title></head><body>"
            # 空の sp_table_wrap (thead だけ) -> 除外
            "<table class='sp_table_wrap'><thead>"
            "<tr><th>No.</th><th>場所</th></tr></thead>"
            "<tbody></tbody></table>"
            # 末尾の空 datatable は ROW_SELECTOR と一致しないので最初から除外
            "<table class='datatable'></table>"
            "</body></html>"
        )
        adapter = PrefEhimeAdapter(_site_lost())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_species_inferred_from_header_when_site_name_neutral(self, fixture_html):
        """サイト名が中立 (犬/猫を含まない) でも見出し段落から species を推定

        収容中・譲渡予定どちらのサイト名も「犬」「猫」を含まないため、
        サイト名のみでは "その他" としか判定できないが、
        見出し段落の "犬" を読み取って "犬" として返せる。
        """
        html = fixture_html("pref_ehime")
        adapter = PrefEhimeAdapter(_site_adoption())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        # 見出し段落の "犬" が優先される
        assert raw.species == "犬"
        assert raw.category == "adoption"

    def test_species_falls_back_to_other_without_hint(self):
        """見出し段落が無く site name も中立なら "その他" を返す"""
        html = (
            "<html><head><title>愛媛県</title></head><body>"
            "<table class='sp_table_wrap'>"
            "<thead><tr>"
            "<th>No.</th><th>拾得捕獲場所</th><th>種類</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>備考</th>"
            "</tr></thead>"
            "<tbody><tr>"
            "<td>1</td><td>松山市</td><td>雑種</td>"
            "<td>黒</td><td>オス</td><td>小</td><td></td>"
            "</tr></tbody></table>"
            "</body></html>"
        )
        adapter = PrefEhimeAdapter(_site_lost())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.species == "その他"
        assert raw.location == "松山市"
        assert raw.color == "黒"
        assert raw.sex == "オス"
        assert raw.size == "小"
        # 見出し段落も更新日も無いので shelter_date は空 (不明)
        assert raw.shelter_date == ""
        assert raw.image_urls == []

    def test_shelter_date_uses_update_year(self):
        """収容日は見出しの月日と「更新日：YYYY年」の年を組み合わせる"""
        html = (
            "<html><head><title>愛媛県</title></head><body>"
            "<span class='date'>更新日：2024年7月3日</span>"
            "<p><strong>3月15日　松山市　猫</strong></p>"
            "<table class='sp_table_wrap'>"
            "<thead><tr>"
            "<th>No.</th><th>拾得捕獲場所</th><th>種類</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>備考</th>"
            "</tr></thead>"
            "<tbody><tr>"
            "<td>1</td><td>松山市</td><td>雑種</td>"
            "<td>三毛</td><td>メス</td><td>中</td><td></td>"
            "</tr></tbody></table>"
            "</body></html>"
        )
        adapter = PrefEhimeAdapter(_site_lost())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.shelter_date == "2024-03-15"
        assert raw.species == "猫"

    def test_species_inference_helper(self):
        """`_infer_species_from_site_name` の単体動作確認

        愛媛県の現行サイト名 (収容中・譲渡予定) はいずれも犬/猫を含まないため
        "その他" を返すのが正しい。明示的に「犬」「猫」を含む将来のサイト名にも
        備える。
        """
        cases = [
            ("愛媛県動物愛護センター（収容中）", "その他"),
            ("愛媛県動物愛護センター（譲渡予定）", "その他"),
            ("愛媛県動物愛護センター（収容中・犬）", "犬"),
            ("愛媛県動物愛護センター（収容中・猫）", "猫"),
            ("愛媛県動物愛護センター（収容犬猫以外）", "その他"),
        ]
        for name, expected in cases:
            assert (
                PrefEhimeAdapter._infer_species_from_site_name(name) == expected
            ), f"{name} -> expected {expected}"

    def test_all_two_sites_registered(self):
        """2 つの愛媛県サイト名すべてが Registry に登録されている"""
        expected = [
            "愛媛県動物愛護センター（収容中）",
            "愛媛県動物愛護センター（譲渡予定）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefEhimeAdapter)
            assert SiteAdapterRegistry.get(name) is PrefEhimeAdapter

    def test_normalize_returns_animal_data(self, fixture_html):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = fixture_html("pref_ehime")
        adapter = PrefEhimeAdapter(_site_lost())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")
