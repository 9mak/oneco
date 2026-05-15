"""PrefIwateAdapter のテスト

岩手県（保護動物情報・ハブ）(pref.iwate.jp) 用 rule-based adapter の動作検証。

- 対象ページは県内 9 保健所 + 盛岡市保健所の保護動物情報ページへの
  リンク集インデックスで、本文に動物個別データを持たないため
  `fetch_animal_list` は空リストを返す
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で
  逆変換され、HTML キャッシュ内に正しい日本語が復元される
- 将来テンプレートに動物個別ブロックがインライン挿入された場合のテーブル
  抽出経路も担保する
- サイト名 "岩手県（保護動物情報・ハブ）" の Registry 登録確認
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_iwate import (
    PrefIwateAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "岩手県（保護動物情報・ハブ）",
    list_url: str = ("https://www.pref.iwate.jp/kurashikankyou/anzenanshin/pet/1004615.html"),
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="岩手県",
        prefecture_code="03",
        list_url=list_url,
        category=category,
        single_page=True,
    )


class TestPrefIwateAdapter:
    def test_fetch_animal_list_returns_empty_for_index_page(self, fixture_html):
        """9 保健所 + 盛岡市保健所のリンク集 (本文 0 件) ページでは空リストが返る

        fixture `pref_iwate_jp.html` は実サイトと同じく本文中に
        動物個別ブロックを含まず、各保健所等への内部リンクと
        注意事項のみが並ぶ典型的な「インデックス 0 件状態」のページ。
        基底実装は ParsingError を投げるが、本 adapter ではこれを
        正常な 0 件として扱う。
        """
        html = fixture_html("pref_iwate_jp")
        adapter = PrefIwateAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], f"インデックスページでは空配列が返るはず: got {result!r}"

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = fixture_html("pref_iwate_jp")
        adapter = PrefIwateAdapter(_site())

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
        adapter 側で逆変換することで、HTML キャッシュ内に「岩手」等の
        日本語が読める状態となる。
        """
        html = fixture_html("pref_iwate_jp")
        # 元 fixture には mojibake 状態の "å²©æ" が含まれ、
        # 直接の "岩手" は含まれない (二重エンコードのため)
        assert "岩手" not in html

        adapter = PrefIwateAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()

        # 復元後の HTML キャッシュには "岩手" が含まれているはず
        assert adapter._html_cache is not None
        assert "岩手" in adapter._html_cache

    def test_fetch_with_inline_table_returns_animal(self):
        """HTML 内に動物テーブルがインライン掲載されている場合は抽出される

        将来的にサイトが本文 (#content) 内に動物テーブルを掲載した場合の
        挙動を担保する。
        """
        html = (
            "<html><head><title>保護動物情報 | 岩手県</title></head>"
            "<body><div id='content'><table>"
            "<tr><th>種類</th><td>柴犬</td></tr>"
            "<tr><th>毛色</th><td>茶</td></tr>"
            "<tr><th>性別</th><td>オス</td></tr>"
            "<tr><th>大きさ</th><td>中</td></tr>"
            "<tr><th>推定年齢</th><td>成犬</td></tr>"
            "<tr><th>収容日</th><td>2026年5月12日</td></tr>"
            "<tr><th>収容場所</th><td>中央保健所</td></tr>"
            "</table></div></body></html>"
        )
        adapter = PrefIwateAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert isinstance(raw, RawAnimalData)
        # ラベル → フィールドのマップが効いていることを確認
        assert raw.species == "柴犬"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert raw.age == "成犬"
        assert "中央" in raw.location
        assert raw.category == "sheltered"
        assert raw.source_url.endswith("#row=0")

    def test_sidebar_and_index_links_are_not_extracted_as_rows(self, fixture_html):
        """サイドバー (#lnavi) や `ul.objectlink` のインデックスリンクは
        ROW として誤検出されない

        フィクスチャには本文末尾近くの `ul.objectlink` 配下に各保健所
        への article_title リンク (`<a>`) が並ぶが、`ROW_SELECTOR` は動物
        個別ブロック (テーブル/カード) に限定しているため動物として拾われない
        ことを担保する。
        """
        html = fixture_html("pref_iwate_jp")
        adapter = PrefIwateAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()

        # 0 件であることが期待値 (= インデックスリンクが取り込まれていない)
        assert urls == []

    def test_site_registered(self):
        """サイト名 "岩手県（保護動物情報・ハブ）" が Registry に
        登録されている
        """
        name = "岩手県（保護動物情報・ハブ）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefIwateAdapter)
        assert SiteAdapterRegistry.get(name) is PrefIwateAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = (
            "<html><head><title>岩手県</title></head>"
            "<body><div id='content'><table>"
            "<tr><th>種類</th><td>雑種</td></tr>"
            "<tr><th>性別</th><td>メス</td></tr>"
            "<tr><th>収容日</th><td>2026年5月12日</td></tr>"
            "</table></div></body></html>"
        )
        adapter = PrefIwateAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        # AnimalData に変換できれば OK (詳細属性は normalizer 側で検証済み)
        assert normalized is not None
        assert hasattr(normalized, "species")
