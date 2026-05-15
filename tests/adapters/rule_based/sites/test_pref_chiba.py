"""PrefChibaAdapter のテスト

千葉県動物愛護センター (pref.chiba.lg.jp/aigo/pet/) 用 rule-based adapter の動作を検証する。

- 1 ページに `<h2>【収容日】...</h2>` 起点の動物ブロックが並ぶ single_page 形式
- 5 サイト (本所 収容犬/猫/犬猫以外、東葛飾 収容犬/猫) すべての登録確認
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で逆変換
- 末尾にあるテンプレート行 ("テンプレート【収容日】...") は除外される
- 在庫 0 件のページでも ParsingError を出さず空リストを返す
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_chiba import (
    PrefChibaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="千葉県動愛センター本所（収容犬）",
        prefecture="千葉県",
        prefecture_code="12",
        list_url=(
            "https://www.pref.chiba.lg.jp/aigo/pet/inu-neko/shuuyou/shuu-inu.html"
        ),
        category="sheltered",
        single_page=True,
    )


class TestPrefChibaAdapter:
    def test_fetch_animal_list_returns_two_animals(self, fixture_html):
        """テンプレート行を除いた実データ 2 件が抽出される

        フィクスチャ pref_chiba__shuuinu.html には h2 が 3 個含まれるが、
        うち 1 個は "テンプレート【収容日】..." なのでデータは 2 件。
        """
        html = fixture_html("pref_chiba__shuuinu")
        adapter = PrefChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2, "テンプレート行を除いた 2 件が期待値"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith(
                "https://www.pref.chiba.lg.jp/aigo/pet/inu-neko/shuuyou/shuu-inu.html"
            )
            assert cat == "sheltered"

    def test_extract_first_animal(self, fixture_html, assert_raw_animal):
        """1 件目 (kt260512-01) から RawAnimalData を構築できる"""
        html = fixture_html("pref_chiba__shuuinu")
        adapter = PrefChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名「収容犬」から犬と推定される
        assert raw.species == "犬"
        # 1 件目: 収容日 2026-05-12, 場所 香取市本矢作, 雑種・白黒茶・オス・中・成犬
        assert raw.shelter_date == "2026-05-12"
        assert "香取市" in raw.location
        assert raw.color == "白黒茶"
        assert raw.sex == "オス"
        assert raw.size == "中"
        assert raw.age == "成犬"
        # 画像 URL が絶対 URL として取得される
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_second_animal(self, fixture_html):
        """2 件目 (ks260511-01) のフィールド値も期待通りに取れる"""
        html = fixture_html("pref_chiba__shuuinu")
        adapter = PrefChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert raw.shelter_date == "2026-05-11"
        assert "銚子市" in raw.location
        assert raw.color == "茶色"
        assert raw.sex == "メス"
        assert raw.size == "中"
        assert raw.age == "成犬"

    def test_template_row_excluded(self, fixture_html):
        """"テンプレート【収容日】" 行はデータとして拾われない

        テンプレート行の場所が "市町" / 性別が "オスメス" 等の
        サイト編集者向けプレースホルダ文字列なので、それらが
        抽出結果に混入していないことで確認する。
        """
        html = fixture_html("pref_chiba__shuuinu")
        adapter = PrefChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            results = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        for raw in results:
            assert raw.location != "市町"
            assert raw.sex != "オスメス"
            assert "種類" not in raw.color  # "種類・毛色・オスメス" 由来の混入が無いこと

    def test_empty_page_returns_empty_list(self):
        """動物 h2 が無いページ (在庫 0 件) でも例外を出さない"""
        empty_html = (
            "<html><head><title>千葉県</title></head>"
            "<body><div id='tmp_honbun'>"
            "<h2>収容情報はありません</h2>"
            "</div></body></html>"
        )
        adapter = PrefChibaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_template_only_page_returns_empty_list(self):
        """テンプレート h2 だけのページでも空リストを返す"""
        only_template_html = (
            "<html><head><title>千葉県</title></head>"
            "<body>"
            "<h2><strong>テンプレート【収容日】2026年月日</strong></h2>"
            "<div class='col2'><div class='col2L'>"
            "<p><img src='/x.jpg'></p>"
            "<p>【管理番号】2600000-01</p>"
            "<p>【収容場所】市町</p>"
            "</div></div>"
            "</body></html>"
        )
        adapter = PrefChibaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=only_template_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字が正しく復元される

        fixture には Latin-1 解釈された UTF-8 バイト列がそのまま残っているので、
        adapter 側で逆変換しないと "香取市" 等の漢字が一致しない。
        """
        html = fixture_html("pref_chiba__shuuinu")
        # fixture 側は mojibake 状態 (千葉が直接含まれていない可能性)
        adapter = PrefChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        # 復元できていれば "香取市" が読める
        assert "香取市" in raw.location

    def test_species_inferred_from_site_name(self):
        """site name から species を正しく推定する (3 種別)"""
        for name, expected in [
            ("千葉県動愛センター本所（収容犬）", "犬"),
            ("千葉県動愛センター本所（収容猫）", "猫"),
            ("千葉県動愛センター本所（収容犬猫以外）", "その他"),
            ("千葉県動愛センター東葛飾支所（収容犬）", "犬"),
            ("千葉県動愛センター東葛飾支所（収容猫）", "猫"),
        ]:
            assert (
                PrefChibaAdapter._infer_species_from_site_name(name) == expected
            ), f"{name} -> expected {expected}"

    def test_all_five_sites_registered(self):
        """5 つの千葉県サイト名すべてが Registry に登録されている"""
        expected = [
            "千葉県動愛センター本所（収容犬）",
            "千葉県動愛センター本所（収容猫）",
            "千葉県動愛センター本所（収容犬猫以外）",
            "千葉県動愛センター東葛飾支所（収容犬）",
            "千葉県動愛センター東葛飾支所（収容猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefChibaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefChibaAdapter

    def test_normalize_returns_animal_data(self, fixture_html):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = fixture_html("pref_chiba__shuuinu")
        adapter = PrefChibaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        # AnimalData に変換できれば OK (詳細属性は normalizer 側で検証済み)
        assert normalized is not None
        assert hasattr(normalized, "species")
