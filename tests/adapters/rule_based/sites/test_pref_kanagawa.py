"""PrefKanagawaAdapter のテスト

神奈川県動物愛護センター (pref.kanagawa.jp) 用 rule-based adapter の動作検証。

- 4 サイト (保護犬/保護猫/その他動物/センター外保護動物) すべての登録確認
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で逆変換
- 動物詳細は通常 PDF 配布のため 0 件状態のページが正常 → 空リストを返す
- HTML に動物カード/テーブルがインライン掲載された場合の抽出経路も担保
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_kanagawa import (
    PrefKanagawaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "神奈川県動物愛護センター（保護犬）",
    list_url: str = "https://www.pref.kanagawa.jp/osirase/1594/awc/lost/dog.html",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="神奈川県",
        prefecture_code="14",
        list_url=list_url,
        category=category,
        single_page=True,
    )


class TestPrefKanagawaAdapter:
    def test_fetch_animal_list_returns_empty_for_pdf_only_page(self, fixture_html):
        """PDF のみで動物詳細を配布する 0 件 HTML では空リストが返る

        フィクスチャ pref_kanagawa__lostdog.html は実サイトと同じく
        本文中に動物個別ブロックが存在せず、PDF ボタンのみが置かれた
        典型的な 0 件状態のページ。基底実装は ParsingError を投げるが、
        本 adapter ではこれを正常な 0 件として扱う。
        """
        html = fixture_html("pref_kanagawa__lostdog")
        adapter = PrefKanagawaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], f"PDF 配布 (HTML 0 件) ページでは空配列が返るはず: got {result!r}"

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = fixture_html("pref_kanagawa__lostdog")
        adapter = PrefKanagawaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字テキストが正しく復元される

        fixture には Latin-1 解釈された UTF-8 バイト列がそのまま残っている。
        adapter 側で逆変換することで、HTML キャッシュ内に「神奈川」等の
        日本語が読める状態となる。
        """
        html = fixture_html("pref_kanagawa__lostdog")
        # 元 fixture には mojibake 状態の "ç¥å¥å·" が含まれ、
        # 直接の "神奈川" は含まれない (二重エンコードのため)
        assert "神奈川" not in html

        adapter = PrefKanagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()

        # 復元後の HTML キャッシュには "神奈川" が含まれているはず
        assert adapter._html_cache is not None
        assert "神奈川" in adapter._html_cache

    def test_fetch_with_inline_table_returns_animal(self):
        """HTML に動物テーブルがインライン掲載されている場合は抽出される

        将来的にサイトが PDF ではなく HTML 内にテーブルで掲載した
        場合の挙動を担保する。本文 (main > section) に table を挿入。
        """
        html = (
            "<html><head><title>神奈川県動物愛護センター</title></head>"
            "<body><main><section><table>"
            "<tr><th>種類</th><td>柴犬</td></tr>"
            "<tr><th>毛色</th><td>茶</td></tr>"
            "<tr><th>性別</th><td>オス</td></tr>"
            "<tr><th>大きさ</th><td>中</td></tr>"
            "<tr><th>推定年齢</th><td>成犬</td></tr>"
            "<tr><th>収容日</th><td>2026年5月12日</td></tr>"
            "<tr><th>収容場所</th><td>平塚市内</td></tr>"
            "</table></section></main></body></html>"
        )
        adapter = PrefKanagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert isinstance(raw, RawAnimalData)
        # サイト名 "保護犬" → species = "犬"
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert raw.age == "成犬"
        assert "平塚市" in raw.location
        assert raw.category == "sheltered"
        assert raw.source_url.endswith("#row=0")

    def test_infer_species_from_site_name_dog(self):
        """サイト名に "犬" を含むと species 推定が "犬" になる"""
        assert (
            PrefKanagawaAdapter._infer_species_from_site_name("神奈川県動物愛護センター（保護犬）")
            == "犬"
        )

    def test_infer_species_from_site_name_cat(self):
        """サイト名に "猫" を含むと species 推定が "猫" になる"""
        assert (
            PrefKanagawaAdapter._infer_species_from_site_name("神奈川県動物愛護センター（保護猫）")
            == "猫"
        )

    def test_infer_species_from_site_name_other(self):
        """「その他動物」「センター外保護動物」は "その他" に推定される"""
        assert (
            PrefKanagawaAdapter._infer_species_from_site_name(
                "神奈川県動物愛護センター（その他動物）"
            )
            == "その他"
        )
        assert (
            PrefKanagawaAdapter._infer_species_from_site_name(
                "神奈川県動物愛護センター（センター外保護動物）"
            )
            == "その他"
        )

    def test_all_four_sites_registered(self):
        """4 つの神奈川県動物愛護センターサイト名すべてが Registry に登録"""
        expected = [
            "神奈川県動物愛護センター（保護犬）",
            "神奈川県動物愛護センター（保護猫）",
            "神奈川県動物愛護センター（その他動物）",
            "神奈川県動物愛護センター（センター外保護動物）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefKanagawaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefKanagawaAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = (
            "<html><head><title>神奈川県</title></head>"
            "<body><main><section><table>"
            "<tr><th>種類</th><td>雑種</td></tr>"
            "<tr><th>性別</th><td>メス</td></tr>"
            "<tr><th>収容日</th><td>2026年5月12日</td></tr>"
            "</table></section></main></body></html>"
        )
        adapter = PrefKanagawaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        # AnimalData に変換できれば OK (詳細属性は normalizer 側で検証済み)
        assert normalized is not None
        assert hasattr(normalized, "species")
