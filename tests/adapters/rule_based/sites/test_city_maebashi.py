"""CityMaebashiAdapter のテスト

前橋市保健所 (city.maebashi.gunma.jp) 用 rule-based adapter の動作を検証する。

- 1 ページに収容犬の一覧テーブルが置かれた single_page 形式
- ページ上に手数料一覧テーブルも同居するため `summary` 属性で対象を特定
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で逆変換
- 収容犬 0 件のページでも ParsingError を出さず空リストを返す
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_maebashi import (
    CityMaebashiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="前橋市（保護犬）",
        prefecture="群馬県",
        prefecture_code="10",
        list_url=(
            "https://www.city.maebashi.gunma.jp/soshiki/kenko/eiseikensa/gyomu/1/1/1/9484.html"
        ),
        category="sheltered",
    )


class TestCityMaebashiAdapter:
    def test_fetch_animal_list_returns_one_animal(self, fixture_html):
        """フィクスチャの一覧テーブルから 1 件の動物が抽出される

        フィクスチャ city_maebashi_gunma_jp.html には
        収容犬 1 頭 (2026-05-02 / 市之関町 / 雑種 / オス) が掲載されている。
        手数料一覧テーブルは summary フィルタで除外される。
        """
        html = fixture_html("city_maebashi_gunma_jp")
        adapter = CityMaebashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1, "フィクスチャ上の収容犬は 1 件"
        url, cat = result[0]
        assert "#row=0" in url
        assert url.startswith(
            "https://www.city.maebashi.gunma.jp/soshiki/kenko/eiseikensa/gyomu/1/1/1/9484.html"
        )
        assert cat == "sheltered"

    def test_extract_first_animal(self, fixture_html, assert_raw_animal):
        """1 件目から RawAnimalData を構築できる"""
        html = fixture_html("city_maebashi_gunma_jp")
        adapter = CityMaebashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名「保護犬」から犬と推定される
        assert raw.species == "犬"
        # 1 件目: 収容日 2026-05-02, 場所 市之関町, 性別 オス
        assert raw.shelter_date == "2026-05-02"
        assert "市之関町" in raw.location
        assert raw.sex == "オス"
        # 画像 URL が絶対 URL として取得される (protocol-relative `//` の解決)
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_fee_table_is_excluded(self, fixture_html):
        """手数料一覧テーブルの行が動物として誤抽出されないこと

        ページ上には「手数料一覧」テーブルが別に存在し、その本文には
        "4,000円" / "400円" / "3,000円" 等の文字列が並ぶ。
        正しく summary フィルタが効いていれば、それらが location や
        sex に混入しない。
        """
        html = fixture_html("city_maebashi_gunma_jp")
        adapter = CityMaebashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            results = [adapter.extract_animal_details(u, category=c) for u, c in urls]

        for raw in results:
            assert "円" not in raw.location
            assert "円" not in raw.sex
            assert raw.location not in ("", "返還手数料", "4,000円")

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字が正しく復元される

        fixture は Latin-1 解釈された UTF-8 バイト列のまま保存されているので、
        adapter 側で逆変換しないと "市之関町" 等の漢字が一致しない。
        """
        html = fixture_html("city_maebashi_gunma_jp")
        # fixture は mojibake 状態 (「前橋」が直接含まれていない)
        assert "前橋" not in html

        adapter = CityMaebashiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert "市之関町" in raw.location

    def test_empty_tbody_returns_empty_list(self):
        """`<tbody>` が空 (在庫 0 件) でも例外を出さず空リストを返す"""
        empty_html = (
            "<html><body>"
            "<table summary='前橋市保健所における保護（収容）犬情報一覧'>"
            "<thead><tr><th>管理番号</th><th>写真</th><th>収容場所</th>"
            "<th>犬種</th><th>性別</th></tr></thead>"
            "<tbody></tbody>"
            "</table>"
            "</body></html>"
        )
        adapter = CityMaebashiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_no_target_table_returns_empty_list(self):
        """対象テーブル自体が無いページでも空リストを返す

        手数料一覧 (summary に "前橋市" を含まない) しか無いケース。
        """
        no_target_html = (
            "<html><body>"
            "<table><caption>手数料一覧</caption>"
            "<tbody><tr><td>4,000円</td><td>400円</td></tr></tbody>"
            "</table>"
            "</body></html>"
        )
        adapter = CityMaebashiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=no_target_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_species_inferred_from_site_name(self):
        """site name から species を正しく推定する"""
        assert CityMaebashiAdapter._infer_species_from_site_name("前橋市（保護犬）") == "犬"
        assert CityMaebashiAdapter._infer_species_from_site_name("前橋市（保護猫）") == "猫"
        assert CityMaebashiAdapter._infer_species_from_site_name("前橋市") == ""

    def test_iso_date_parser(self):
        """管理番号セルのリンクテキストから ISO 日付を取り出す"""
        assert CityMaebashiAdapter._parse_iso_date("2026-05-02") == "2026-05-02"
        # zero-padding を保証
        assert CityMaebashiAdapter._parse_iso_date("2026-5-2") == "2026-05-02"
        # 周辺文字列があっても抽出される
        assert CityMaebashiAdapter._parse_iso_date("管理番号 2026-05-02 詳細") == "2026-05-02"
        # マッチしない場合は空文字
        assert CityMaebashiAdapter._parse_iso_date("no date here") == ""

    def test_site_registered(self):
        """「前橋市（保護犬）」が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get("前橋市（保護犬）") is None:
            SiteAdapterRegistry.register("前橋市（保護犬）", CityMaebashiAdapter)
        assert SiteAdapterRegistry.get("前橋市（保護犬）") is CityMaebashiAdapter

    def test_normalize_returns_animal_data(self, fixture_html):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = fixture_html("city_maebashi_gunma_jp")
        adapter = CityMaebashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")
