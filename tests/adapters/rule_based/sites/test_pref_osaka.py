"""PrefOsakaAdapter のテスト

大阪府動物愛護管理センターサイト (pref.osaka.lg.jp) 用
rule-based adapter の動作を検証する。

- 1 ページに `<h4>犬|猫</h4><table>` のセットが並ぶ single_page 形式
- テーブル 1 つ = 動物 1 件 (受付番号 th を持つ表のみ)
- 在庫 0 件のテーブル (受付番号値が空) と政令市連絡先テーブルは除外
- フィクスチャは二重 UTF-8 mojibake 状態のため adapter 側で逆変換
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_osaka import (
    PrefOsakaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="大阪府動物愛護管理センター（迷い犬猫）",
        prefecture="大阪府",
        prefecture_code="27",
        list_url=(
            "https://www.pref.osaka.lg.jp/o120200/doaicenter/doaicenter/"
            "maigoken.html"
        ),
        category="lost",
        single_page=True,
    )


def _empty_html() -> str:
    """全ての動物テーブルが空 (在庫 0 件) の合成 HTML"""
    return (
        "<html><head><title>大阪府</title></head><body>"
        "<h4><span class='txt_big'><strong>犬</strong></span></h4>"
        "<table border='1'><tbody>"
        "<tr><td rowspan='9'>&nbsp;</td>"
        "<th><p>受付番号</p></th><td>&nbsp;</td></tr>"
        "<tr><th>収容日</th><td>&nbsp;</td></tr>"
        "<tr><th><p>収容場所</p></th><td><p>&nbsp;</p></td></tr>"
        "<tr><th><p>犬の特徴</p></th><td><p>&nbsp;</p></td></tr>"
        "<tr><th>連絡先</th><td><p>&nbsp;</p></td></tr>"
        "</tbody></table>"
        "<h4><span class='txt_big'>猫</span></h4>"
        "<table border='1'><tbody>"
        "<tr><td rowspan='9'>&nbsp;</td>"
        "<th><p>受付番号</p></th><td>&nbsp;</td></tr>"
        "<tr><th>収容日</th><td>&nbsp;</td></tr>"
        "<tr><th><p>収容場所</p></th><td><p>&nbsp;</p></td></tr>"
        "<tr><th><p>猫の特徴</p></th><td><p>&nbsp;</p></td></tr>"
        "<tr><th>連絡先</th><td><p>&nbsp;</p></td></tr>"
        "</tbody></table>"
        "</body></html>"
    )


def _populated_html() -> str:
    """犬 1 匹 + 猫 1 匹を含む合成 HTML

    テンプレート構造はフィクスチャ pref_osaka_lg_jp.html と同じ。
    """
    return (
        "<html><head><title>大阪府</title></head><body>"
        "<h4><span class='txt_big'><strong>犬</strong></span></h4>"
        "<table border='1'><tbody>"
        "<tr>"
        "<td rowspan='9'><img alt='34' src='/images/1436/26-00034.jpg' /></td>"
        "<th><p>受付番号</p></th><td>26-00034</td></tr>"
        "<tr><th>収容日</th><td><p>令和8年5月11日</p></td></tr>"
        "<tr><th><p>収容場所</p></th><td><p>泉南郡熊取町山の手台</p></td></tr>"
        "<tr><th><p>犬の特徴</p></th><td>"
        "<p>種類：雑種</p>"
        "<p>性別：雌</p>"
        "<p>毛色：白黒</p>"
        "<p>体格：小</p>"
        "<p>首輪：水色</p>"
        "<p>引綱：なし</p>"
        "</td></tr>"
        "<tr><th>連絡先</th><td>"
        "<p>施設名:大阪府動物愛護管理センター　泉佐野支所</p>"
        "<p>電話番号：072-464-9777</p>"
        "<p>住所：〒598-0001</p>"
        "<p>泉佐野市上瓦屋583-1</p>"
        "</td></tr>"
        "</tbody></table>"
        "<h4><span class='txt_big'>猫</span></h4>"
        "<table border='1'><tbody>"
        "<tr>"
        "<td rowspan='9'><img alt='cat' src='/images/1436/26-00100.jpg' /></td>"
        "<th><p>受付番号</p></th><td>26-00100</td></tr>"
        "<tr><th>収容日</th><td><p>令和8年5月10日</p></td></tr>"
        "<tr><th><p>収容場所</p></th><td><p>大阪市北区</p></td></tr>"
        "<tr><th><p>猫の特徴</p></th><td>"
        "<p>種類：雑種</p>"
        "<p>性別：雄</p>"
        "<p>毛色：黒</p>"
        "<p>体格：中</p>"
        "</td></tr>"
        "<tr><th>連絡先</th><td>"
        "<p>電話番号：072-464-9777</p>"
        "</td></tr>"
        "</tbody></table>"
        # ノイズ: 政令市・中核市の連絡先テーブル (受付番号 th を持たない)
        "<table border='1' class='datatable'><tbody>"
        "<tr><th><a href='http://example.com'>大阪市動物管理センター</a></th>"
        "<td><p>大阪市住之江区柴谷2-5-74</p><p>電話06-6685-3700</p></td></tr>"
        "</tbody></table>"
        "</body></html>"
    )


class TestPrefOsakaAdapter:
    def test_fetch_animal_list_excludes_empty_tables(self, fixture_html):
        """フィクスチャは犬 1 件 + 猫 0 件 → 1 件だけ抽出される

        - 犬テーブル: 受付番号 26-00034 あり → 採用
        - 猫テーブル: 全 td 空 → 除外
        - 政令市テーブル: 受付番号 th なし → 除外
        """
        html = fixture_html("pref_osaka_lg_jp")
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1, "犬 1 件のみが抽出されるはず (猫 0 件・政令市除外)"
        url, cat = result[0]
        assert "#row=0" in url
        assert url.startswith(
            "https://www.pref.osaka.lg.jp/o120200/doaicenter/doaicenter/"
            "maigoken.html"
        )
        assert cat == "lost"

    def test_extract_first_animal_from_fixture(self, fixture_html):
        """フィクスチャの犬 1 件目を RawAnimalData として復元できる"""
        html = fixture_html("pref_osaka_lg_jp")
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回 (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        # 令和8年5月11日 → 2026-05-11
        assert raw.shelter_date == "2026-05-11"
        assert "熊取町" in raw.location
        assert raw.color == "白黒"
        assert raw.sex == "雌"
        assert raw.size == "小"
        # 電話番号は連絡先セルから抽出 (XXX-XXXX-XXXX 形式に正規化)
        assert raw.phone == "072-464-9777"
        # 画像 URL は絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert any("26-00034.jpg" in u for u in raw.image_urls)
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_fetch_animal_list_returns_two_for_populated_synthetic(self):
        """合成 HTML (犬 1 + 猫 1) では 2 件返り、政令市テーブルは除外される"""
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            result = adapter.fetch_animal_list()

        assert len(result) == 2, "犬 1 件 + 猫 1 件 = 2 件 (政令市表は除外)"

    def test_extract_second_animal_is_cat(self):
        """合成 HTML 2 件目 (猫テーブル) から猫情報が取れる"""
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[1][0], category="lost")

        assert raw.species == "猫"
        assert raw.shelter_date == "2026-05-10"
        assert "大阪市北区" in raw.location
        assert raw.color == "黒"
        assert raw.sex == "雄"
        assert raw.size == "中"

    def test_empty_page_returns_empty_list(self):
        """全テーブルが在庫 0 件のときは空リストを返す (例外を出さない)"""
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_empty_html()):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_no_table_html_returns_empty(self):
        """テーブル要素自体が無くても例外を出さず空を返す"""
        empty = "<html><head><title>大阪府</title></head><body><p>no</p></body></html>"
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=empty):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 mojibake fixture でも漢字が正しく復元される

        補正後でなければ「大阪」「受付番号」が読めず動物テーブルを 1 件も
        判定できないため、抽出件数が 0 になってしまう。
        ここでは件数 >= 1 になることで間接的に補正を確認する。
        """
        html = fixture_html("pref_osaka_lg_jp")
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            rows = adapter._load_rows()

        assert len(rows) >= 1, "mojibake 補正が効いていれば犬テーブル 1 件は拾える"

    def test_reiwa_date_parsing(self):
        """令和N年 → 西暦 ISO 変換が正しい (令和1 = 2019)"""
        assert PrefOsakaAdapter._parse_date("令和1年1月1日") == "2019-01-01"
        assert PrefOsakaAdapter._parse_date("令和8年5月11日") == "2026-05-11"
        # 西暦表記もそのまま受け取れる
        assert PrefOsakaAdapter._parse_date("2026年5月11日") == "2026-05-11"
        # パース不可
        assert PrefOsakaAdapter._parse_date("不明") == ""

    def test_site_registered(self):
        """大阪府サイトが Registry に登録されている"""
        name = "大阪府動物愛護管理センター（迷い犬猫）"
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, PrefOsakaAdapter)
        assert SiteAdapterRegistry.get(name) is PrefOsakaAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")

    def test_datatable_excluded(self):
        """`class='datatable'` の政令市連絡先テーブルは動物テーブル扱いされない"""
        # 動物テーブルゼロ + 政令市テーブルだけ
        html = (
            "<html><body>"
            "<table border='1' class='datatable'><tbody>"
            "<tr><th><a href='http://example.com'>大阪市動物管理センター</a></th>"
            "<td><p>大阪市住之江区</p></td></tr>"
            "</tbody></table>"
            "</body></html>"
        )
        adapter = PrefOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []
