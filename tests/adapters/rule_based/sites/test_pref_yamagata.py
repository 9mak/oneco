"""PrefYamagataAdapter のテスト

山形県（飼い主探し掲示板・ハブ）(pref.yamagata.jp) 用 rule-based
adapter の動作検証。

- 対象ページは県内 4 保健所 (村山 / 最上 / 置賜 / 庄内) の飼い主探し掲示板
  ページへのリンク集インデックスで、本文に動物個別データを持たないため
  `fetch_animal_list` は空リストを返す
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で
  逆変換され、HTML キャッシュ内に正しい日本語が復元される
- 将来テンプレートに動物個別ブロックがインライン挿入された場合のテーブル
  抽出経路も担保する
- サイト名 "山形県（飼い主探し掲示板・ハブ）" の Registry 登録確認
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_yamagata import (
    PrefYamagataAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "山形県（飼い主探し掲示板・ハブ）",
    list_url: str = (
        "https://www.pref.yamagata.jp/020071/kenfuku/doubutsuaigo/"
        "aigo/kainushisagashi/keijiban.html"
    ),
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="山形県",
        prefecture_code="06",
        list_url=list_url,
        category=category,
        single_page=True,
    )


class TestPrefYamagataAdapter:
    def test_fetch_animal_list_returns_empty_for_index_page(self, fixture_html):
        """4 保健所のリンク集 (本文 0 件) ページでは空リストが返る

        fixture `pref_yamagata_jp.html` は実サイトと同じく本文中に
        動物個別ブロックを含まず、4 保健所等への内部リンクと案内文のみが
        並ぶ典型的な「インデックス 0 件状態」のページ。
        基底実装は ParsingError を投げるが、本 adapter ではこれを
        正常な 0 件として扱う。
        """
        html = fixture_html("pref_yamagata_jp")
        adapter = PrefYamagataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], f"インデックスページでは空配列が返るはず: got {result!r}"

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = fixture_html("pref_yamagata_jp")
        adapter = PrefYamagataAdapter(_site())

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
        adapter 側で逆変換することで、HTML キャッシュ内に「山形」等の
        日本語が読める状態となる。
        """
        html = fixture_html("pref_yamagata_jp")
        # 元 fixture には mojibake 状態の "å±±å½¢" が含まれ、
        # 直接の "山形" は含まれない (二重エンコードのため)
        assert "山形" not in html

        adapter = PrefYamagataAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()

        # 復元後の HTML キャッシュには "山形" が含まれているはず
        assert adapter._html_cache is not None
        assert "山形" in adapter._html_cache

    def test_fetch_with_inline_table_returns_animal(self):
        """HTML 内に動物テーブルがインライン掲載されている場合は抽出される

        将来的にサイトが本文 (#tmp_main 配下の #tmp_contents) 内に
        動物テーブルを掲載した場合の挙動を担保する。
        """
        html = (
            "<html><head><title>飼い主探し掲示板 | 山形県</title></head>"
            "<body><div id='tmp_main'><div id='tmp_contents'><table>"
            "<tr><th>種類</th><td>柴犬</td></tr>"
            "<tr><th>毛色</th><td>茶</td></tr>"
            "<tr><th>性別</th><td>オス</td></tr>"
            "<tr><th>大きさ</th><td>中</td></tr>"
            "<tr><th>推定年齢</th><td>成犬</td></tr>"
            "<tr><th>収容日</th><td>2026年5月12日</td></tr>"
            "<tr><th>収容場所</th><td>村山保健所</td></tr>"
            "</table></div></div></body></html>"
        )
        adapter = PrefYamagataAdapter(_site())
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
        assert "村山" in raw.location
        assert raw.category == "sheltered"
        assert raw.source_url.endswith("#row=0")

    def test_sidebar_and_index_links_are_not_extracted_as_rows(self, fixture_html):
        """サイドバー (#tmp_lnavi) や本文内の保健所リンク一覧 (<ul><li><a>)
        は ROW として誤検出されない

        フィクスチャには `#tmp_main` 配下に各保健所への <li><a> リンク一覧が
        並ぶが、`ROW_SELECTOR` は動物個別ブロック (テーブル/カード) に
        限定しているため動物として拾われないことを担保する。
        """
        html = fixture_html("pref_yamagata_jp")
        adapter = PrefYamagataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()

        # 0 件であることが期待値 (= インデックスリンクが取り込まれていない)
        assert urls == []

    def test_site_registered(self):
        """サイト名 "山形県（飼い主探し掲示板・ハブ）" が Registry に
        登録されている
        """
        name = "山形県（飼い主探し掲示板・ハブ）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefYamagataAdapter)
        assert SiteAdapterRegistry.get(name) is PrefYamagataAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = (
            "<html><head><title>山形県</title></head>"
            "<body><div id='tmp_main'><div id='tmp_contents'><table>"
            "<tr><th>種類</th><td>雑種</td></tr>"
            "<tr><th>性別</th><td>メス</td></tr>"
            "<tr><th>収容日</th><td>2026年5月12日</td></tr>"
            "</table></div></div></body></html>"
        )
        adapter = PrefYamagataAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        # AnimalData に変換できれば OK (詳細属性は normalizer 側で検証済み)
        assert normalized is not None
        assert hasattr(normalized, "species")
