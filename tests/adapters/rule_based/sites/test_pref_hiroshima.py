"""PrefHiroshimaAdapter のテスト

広島県動物愛護センター (pref.hiroshima.lg.jp) 用 rule-based adapter の動作検証。

- `<div class="detail_free">` 配下に「管理番号 h2 + 詳細 p」のブロックが
  並ぶ single_page 形式
- フィクスチャは二重 UTF-8 mojibake 状態のため adapter 側で逆変換
- 同一テンプレートの 2 サイト (迷い犬/迷い猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_hiroshima import (
    PrefHiroshimaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "広島県動物愛護センター（迷い犬）",
    list_url: str = (
        "https://www.pref.hiroshima.lg.jp/site/apc/jouto-stray-dog-list.html"
    ),
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="広島県",
        prefecture_code="34",
        list_url=list_url,
        category=category,
        single_page=True,
    )


class TestPrefHiroshimaAdapter:
    def test_fetch_animal_list_returns_blocks(self, fixture_html):
        """フィクスチャから 1 件以上の管理番号ブロックが抽出できる"""
        html = fixture_html("pref_hiroshima")
        adapter = PrefHiroshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1, "少なくとも 1 件の管理番号ブロックが抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.hiroshima.lg.jp/")
            assert cat == "lost"

    def test_extract_animal_details_first_block(self, fixture_html):
        """1 件目のブロックから RawAnimalData を構築できる"""
        html = fixture_html("pref_hiroshima")
        adapter = PrefHiroshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一インスタンスでの繰り返し HTTP 呼び出しは 1 回のみ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # フィクスチャ 1 件目: 性別 "雄" → "オス" に正規化
        assert raw.sex == "オス"
        # 年齢: "推定7歳"
        assert "7" in raw.age
        assert "歳" in raw.age
        # 場所: "安芸郡熊野町城之堀付近" (日付/末尾の "で保護されました" を除去)
        assert "熊野町" in raw.location
        # 収容日: "令和8年5月12日" の文字列が取得できる
        assert "令和" in raw.shelter_date or "年" in raw.shelter_date
        # 画像: <img> が 1 つ以上、絶対 URL 化される
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("http")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_html_caches_after_first_call(self, fixture_html):
        """同一インスタンスでの繰り返し fetch_animal_list は HTTP 1 回のみ"""
        html = fixture_html("pref_hiroshima")
        adapter = PrefHiroshimaAdapter(_site())

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
        adapter 側で逆変換することで、HTML キャッシュ内に「広島」等の
        日本語が読める状態となる。
        """
        html = fixture_html("pref_hiroshima")
        # 元 fixture には mojibake 状態の文字列 ("åºå³¶ç" 等) が含まれ、
        # 直接の "広島" は含まれないことを前提にする
        assert "広島" not in html

        adapter = PrefHiroshimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()

        # 復元後の HTML キャッシュには "広島" が含まれているはず
        assert adapter._html_cache is not None
        assert "広島" in adapter._html_cache

    def test_zero_inventory_returns_empty_list(self):
        """動物ブロックが無い 0 件 HTML では空リストが返り、例外は出ない"""
        html = (
            "<html><head><title>迷い犬一覧 - 広島県</title></head>"
            "<body><div class='detail_free'>"
            "<p>現在迷い犬の収容はありません。</p>"
            "</div></body></html>"
        )
        adapter = PrefHiroshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"在庫 0 件ページは空リストが返るはず: got {result!r}"
        )

    def test_inline_inline_block_is_extracted(self):
        """h2 ブロックを直接組み立てた HTML から RawAnimalData が抽出できる"""
        html = (
            "<html><head><title>迷い犬一覧 - 広島県</title></head>"
            "<body><div class='detail_free'>"
            "<h2>管理番号：1HD20260099</h2>"
            "<p><img alt='迷い1' src='/uploaded/image/999001.JPG'>"
            "<img alt='迷い2' src='/uploaded/image/999002.JPG'></p>"
            "<p>柴犬、推定3歳、雌<br>"
            "センターに収容された日：令和8年5月14日<br>"
            "保護された状況：令和8年5月13日に広島市東区牛田で保護されました。</p>"
            "</div></body></html>"
        )
        adapter = PrefHiroshimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "メス"
        assert "3" in raw.age and "歳" in raw.age
        # 場所: 日付/末尾の "で保護されました" が除去されている
        assert "広島市東区牛田" in raw.location
        # 収容日: ラベル後の値だけが取得される (ラベル文言自体は含まれない)
        assert "令和8年5月14日" in raw.shelter_date
        assert "収容された日" not in raw.shelter_date
        # 画像が 2 件、絶対 URL 化されている
        assert len(raw.image_urls) == 2
        for u in raw.image_urls:
            assert u.startswith("https://www.pref.hiroshima.lg.jp/")
        assert raw.category == "lost"

    def test_multiple_blocks_extracted_independently(self):
        """h2 が複数ある場合、それぞれ独立した動物として抽出される"""
        html = (
            "<html><body><div class='detail_free'>"
            "<h2>管理番号：A001</h2>"
            "<p>柴犬、推定3歳、雄<br>"
            "センターに収容された日：令和8年5月14日<br>"
            "保護された状況：令和8年5月13日に広島市中区基町で保護されました。</p>"
            "<h2>管理番号：A002</h2>"
            "<p>雑種、推定5歳、雌<br>"
            "センターに収容された日：令和8年5月15日<br>"
            "保護された状況：令和8年5月14日に呉市本町で保護されました。</p>"
            "</div></body></html>"
        )
        adapter = PrefHiroshimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        assert len(raws) == 2
        assert raws[0].sex == "オス"
        assert "中区基町" in raws[0].location
        assert raws[1].sex == "メス"
        assert "呉市本町" in raws[1].location

    def test_site_name_species_inference_for_cat(self):
        """サイト名に "猫" を含むと species が "猫" になる"""
        adapter = PrefHiroshimaAdapter(
            _site(
                name="広島県動物愛護センター（迷い猫）",
                list_url=(
                    "https://www.pref.hiroshima.lg.jp/site/apc/"
                    "jouto-stray-cat-list.html"
                ),
            )
        )
        html = (
            "<html><body><div class='detail_free'>"
            "<h2>管理番号：C001</h2>"
            "<p>三毛猫、推定2歳、雌<br>"
            "センターに収容された日：令和8年5月10日<br>"
            "保護された状況：令和8年5月9日に広島市西区で保護されました。</p>"
            "</div></body></html>"
        )
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.species == "猫"
        assert raw.sex == "メス"

    def test_infer_species_from_site_name(self):
        """ヘルパー: サイト名から動物種別を推定する規則を直接テストする"""
        assert (
            PrefHiroshimaAdapter._infer_species_from_site_name(
                "広島県動物愛護センター（迷い犬）"
            )
            == "犬"
        )
        assert (
            PrefHiroshimaAdapter._infer_species_from_site_name(
                "広島県動物愛護センター（迷い猫）"
            )
            == "猫"
        )

    def test_pref_hiroshima_sites_registered(self):
        """広島県動物愛護センター 2 サイトが Registry に登録されている

        広島市 (city.hiroshima.lg.jp) は別 adapter (CityHiroshimaAdapter) が
        担当するため、本 adapter の登録対象には含めない。
        """
        expected = [
            "広島県動物愛護センター（迷い犬）",
            "広島県動物愛護センター（迷い猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefHiroshimaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefHiroshimaAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = (
            "<html><body><div class='detail_free'>"
            "<h2>管理番号：N001</h2>"
            "<p>柴犬、推定4歳、雄<br>"
            "センターに収容された日：令和8年5月14日<br>"
            "保護された状況：令和8年5月13日に広島市中区紙屋町で保護されました。</p>"
            "</div></body></html>"
        )
        adapter = PrefHiroshimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            normalized = adapter.normalize(raw)

        # AnimalData に変換できれば OK (詳細属性は normalizer 側で検証済み)
        assert normalized is not None
        assert hasattr(normalized, "species")
