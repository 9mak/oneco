"""PrefOkayamaAdapter のテスト

岡山県動物愛護センター (pref.okayama.jp) 用 rule-based adapter の動作検証。

- `<div id="main_body">` 配下に犬/猫/その他の 3 つの `<table>` が並ぶ
  single_page 形式
- 各テーブルの最初の行は `<th>` のみのヘッダ、続いて 1 列目=収容日 …
  10 列目=写真 のデータ行が並ぶ
- フィクスチャは二重 UTF-8 mojibake 状態のため adapter 側で逆変換
- `その他` テーブルは原則プレースホルダ行 (全セル空) のためスキップ
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_okayama import (
    PrefOkayamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "岡山県動物愛護センター（保護動物）",
    list_url: str = "https://www.pref.okayama.jp/page/859555.html",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="岡山県",
        prefecture_code="33",
        list_url=list_url,
        category=category,
        single_page=True,
    )


class TestPrefOkayamaAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """フィクスチャから 1 件以上のデータ行が抽出できる"""
        html = fixture_html("pref_okayama_jp")
        adapter = PrefOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 1, "少なくとも 1 件のデータ行が抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.okayama.jp/")
            assert cat == "sheltered"

    def test_extract_dog_row_from_fixture(self, fixture_html):
        """犬テーブル 1 件目から RawAnimalData を構築できる"""
        html = fixture_html("pref_okayama_jp")
        adapter = PrefOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一インスタンスでの繰り返し HTTP 呼び出しは 1 回のみ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # 犬テーブルが先頭に来るので 1 件目は犬
        assert raw.species == "犬"
        # フィクスチャ犬: 性別 "メス"
        assert raw.sex == "メス"
        # 年齢 "成犬"
        assert raw.age == "成犬"
        # 毛色 "茶"
        assert raw.color == "茶"
        # 体格 "中"
        assert raw.size == "中"
        # 場所 "津山市久米川南"
        assert "津山市" in raw.location
        # 収容日: "令和８年５月１５日" (全角数字含む)
        assert "令和" in raw.shelter_date
        # 画像: <img> が 1 つ以上、絶対 URL 化される
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("http")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_extract_cat_row_from_fixture(self, fixture_html):
        """猫テーブルの行から species="猫" が抽出できる"""
        html = fixture_html("pref_okayama_jp")
        adapter = PrefOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        cats = [r for r in raws if r.species == "猫"]
        assert cats, "猫テーブルから少なくとも 1 件抽出されるはず"
        cat = cats[0]
        # 猫フィクスチャ: 性別 "オス"
        assert cat.sex == "オス"
        # 毛色 "茶白"、年齢 "成猫"
        assert cat.color == "茶白"
        assert cat.age == "成猫"
        # 場所 "笠岡市笠岡"
        assert "笠岡市" in cat.location
        # 画像も絶対 URL 化されている
        assert cat.image_urls
        for u in cat.image_urls:
            assert u.startswith("http")

    def test_html_caches_after_first_call(self, fixture_html):
        """同一インスタンスでの繰り返し fetch_animal_list は HTTP 1 回のみ"""
        html = fixture_html("pref_okayama_jp")
        adapter = PrefOkayamaAdapter(_site())

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
        adapter 側で逆変換することで、HTML キャッシュ内に「岡山」等の
        日本語が読める状態となる。
        """
        html = fixture_html("pref_okayama_jp")
        # 元 fixture には mojibake 状態の文字列のみが含まれ、
        # 直接の "岡山" は含まれないことを前提にする
        assert "岡山" not in html

        adapter = PrefOkayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()

        # 復元後の HTML キャッシュには "岡山" が含まれているはず
        assert adapter._html_cache is not None
        assert "岡山" in adapter._html_cache

    def test_zero_inventory_returns_empty_list(self):
        """データ行が無い 0 件 HTML では空リストが返り、例外は出ない"""
        # ヘッダ行のみ + プレースホルダ (全セル空) 行のみのテーブル
        html = (
            "<html><head><title>動物の保護収容情報 - 岡山県ホームページ</title></head>"
            "<body><div id='main_body'>"
            "<div class='detail_free'>"
            "<table>"
            "<caption><p>保護収容情報（犬）</p></caption>"
            "<tbody>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>"
            "<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>"
            "<td>&nbsp;</td><td>&nbsp;</td></tr>"
            "</tbody>"
            "</table>"
            "</div></div></body></html>"
        )
        adapter = PrefOkayamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"在庫 0 件ページは空リストが返るはず: got {result!r}"
        )

    def test_inline_dog_row_is_extracted(self):
        """直接組み立てた HTML から犬の RawAnimalData が抽出できる"""
        html = (
            "<html><head><title>動物の保護収容情報 - 岡山県ホームページ</title></head>"
            "<body><div id='main_body'>"
            "<div class='detail_free'>"
            "<table>"
            "<caption><p>保護収容情報（犬）</p></caption>"
            "<tbody>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "<tr>"
            "<td>令和8年5月20日</td><td>2610099</td><td>柴犬</td>"
            "<td>3歳</td><td>茶</td><td>雄</td><td>小</td>"
            "<td>赤色首輪</td><td>岡山市北区</td>"
            "<td><img alt='dog' src='/uploaded/image/300001.JPG'></td>"
            "</tr>"
            "</tbody>"
            "</table>"
            "</div></div></body></html>"
        )
        adapter = PrefOkayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        # "雄" → "オス" に正規化される
        assert raw.sex == "オス"
        assert raw.age == "3歳"
        assert raw.color == "茶"
        assert raw.size == "小"
        assert "岡山市北区" in raw.location
        assert "令和8年5月20日" in raw.shelter_date
        # 画像が 1 件、絶対 URL 化されている
        assert len(raw.image_urls) == 1
        assert raw.image_urls[0].startswith("https://www.pref.okayama.jp/")
        assert raw.category == "sheltered"

    def test_dog_and_cat_tables_are_both_extracted(self):
        """犬テーブル + 猫テーブルが連続する HTML で両方独立に抽出される"""
        html = (
            "<html><body><div id='main_body'>"
            "<div class='detail_free'>"
            "<table>"
            "<caption><p>保護収容情報（犬）</p></caption>"
            "<tbody>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "<tr>"
            "<td>令和8年5月1日</td><td>D001</td><td>雑種</td>"
            "<td>成犬</td><td>白黒</td><td>雌</td><td>大</td>"
            "<td>無</td><td>津山市</td>"
            "<td><img src='/img/dog.jpg'></td>"
            "</tr>"
            "</tbody>"
            "</table>"
            "</div>"
            "<div class='detail_free'>"
            "<table>"
            "<caption><p>保護収容情報（猫）</p></caption>"
            "<tbody>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "<tr>"
            "<td>令和8年5月2日</td><td>C001</td><td>雑種</td>"
            "<td>子猫</td><td>三毛</td><td>雌</td><td>小</td>"
            "<td>無</td><td>倉敷市</td>"
            "<td><img src='/img/cat.jpg'></td>"
            "</tr>"
            "</tbody>"
            "</table>"
            "</div>"
            "</div></body></html>"
        )
        adapter = PrefOkayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        assert len(raws) == 2
        # 並びは犬 → 猫
        assert raws[0].species == "犬"
        assert "津山市" in raws[0].location
        assert raws[0].sex == "メス"
        assert raws[1].species == "猫"
        assert "倉敷市" in raws[1].location
        assert raws[1].sex == "メス"

    def test_other_table_placeholder_row_is_skipped(self):
        """`その他` テーブルの全セル空プレースホルダ行はスキップされる"""
        html = (
            "<html><body><div id='main_body'>"
            "<div class='detail_free'>"
            "<table>"
            "<caption><p>保護収容情報（犬）</p></caption>"
            "<tbody>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "<tr>"
            "<td>令和8年5月3日</td><td>D002</td><td>柴</td>"
            "<td>成犬</td><td>茶</td><td>オス</td><td>中</td>"
            "<td>無</td><td>岡山市</td>"
            "<td><img src='/img/dog2.jpg'></td>"
            "</tr>"
            "</tbody>"
            "</table>"
            "</div>"
            "<div class='detail_free'>"
            "<table>"
            "<caption>&nbsp;</caption>"
            "<thead>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "</thead>"
            "<tbody>"
            "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>"
            "<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>"
            "<td>&nbsp;</td><td>&nbsp;</td></tr>"
            "</tbody>"
            "</table>"
            "</div>"
            "</div></body></html>"
        )
        adapter = PrefOkayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()

        # 犬テーブルの 1 件のみが残る (その他の空行は除外)
        assert len(urls) == 1

    def test_caption_species_inference(self):
        """ヘルパー: caption テキストから species を判定する規則を直接テストする"""
        from bs4 import BeautifulSoup

        def _table(caption_text: str):
            html = (
                f"<table><caption>{caption_text}</caption>"
                "<tr><td>x</td></tr></table>"
            )
            return BeautifulSoup(html, "html.parser").find("table")

        assert (
            PrefOkayamaAdapter._infer_species_from_caption(
                _table("保護収容情報（犬）")
            )
            == "犬"
        )
        assert (
            PrefOkayamaAdapter._infer_species_from_caption(
                _table("保護収容情報（猫）")
            )
            == "猫"
        )
        # 判定不能 caption は空文字 (上流 normalizer に委譲)
        assert (
            PrefOkayamaAdapter._infer_species_from_caption(_table("&nbsp;"))
            == ""
        )

    def test_pref_okayama_site_registered(self):
        """岡山県動物愛護センターが Registry に登録されている

        岡山市 (city.okayama.jp) と倉敷市 (city.kurashiki.okayama.jp) は
        別テンプレートのため本 adapter の登録対象には含めない。
        """
        name = "岡山県動物愛護センター（保護動物）"
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefOkayamaAdapter)
        assert SiteAdapterRegistry.get(name) is PrefOkayamaAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        html = (
            "<html><body><div id='main_body'>"
            "<div class='detail_free'>"
            "<table>"
            "<caption><p>保護収容情報（犬）</p></caption>"
            "<tbody>"
            "<tr><th>収容日</th><th>管理番号</th><th>種類</th><th>年齢</th>"
            "<th>毛色</th><th>性別</th><th>体格</th><th>特徴</th>"
            "<th>場所</th><th>写真</th></tr>"
            "<tr>"
            "<td>令和8年5月10日</td><td>N001</td><td>柴犬</td>"
            "<td>4歳</td><td>茶</td><td>雄</td><td>中</td>"
            "<td>無</td><td>岡山市中区</td>"
            "<td><img src='/img/n.jpg'></td>"
            "</tr>"
            "</tbody>"
            "</table>"
            "</div></div></body></html>"
        )
        adapter = PrefOkayamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        # AnimalData に変換できれば OK (詳細属性は normalizer 側で検証済み)
        assert normalized is not None
        assert hasattr(normalized, "species")
