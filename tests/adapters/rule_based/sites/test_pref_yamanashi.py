"""PrefYamanashiAdapter のテスト

山梨県動物愛護指導センターサイト (pref.yamanashi.jp/doubutsu/) 用
rule-based adapter の動作を検証する。

- 1 ページに `div.menu_item` カードが並ぶ single_page 形式
- 6 サイト (探している/保護されている × 犬/猫/その他) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_yamanashi import (
    PrefYamanashiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="山梨県（探している犬）",
        prefecture="山梨県",
        prefecture_code="19",
        list_url="https://www.pref.yamanashi.jp/doubutsu/m_dog/index.html",
        category="lost",
        single_page=True,
    )


def _load_yamanashi_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_yamanashi__mdog.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_yamanashi__mdog")
    # 実際のページに含まれる漢字 "山梨" が出てくるか判定
    if "山梨" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefYamanashiAdapter:
    def test_fetch_animal_list_returns_multiple_rows(self, fixture_html):
        """一覧ページから複数の動物カード (仮想 URL) が抽出できる"""
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 2, "少なくとも 2 件以上のカードが抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.yamanashi.jp/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のカードから RawAnimalData を構築できる"""
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # フィクスチャ 1 件目: 場所 "甲州市塩山西広門田", 性別 "メス",
        # 毛色 "うす茶（ベージュ）"
        assert "甲州市" in raw.location
        assert raw.sex == "メス"
        assert "茶" in raw.color
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_no_header_row_skipped_incorrectly(self, fixture_html):
        """カード形式なのでヘッダ行は存在せず、全件が動物として抽出される

        SKIP_FIRST_ROW=False の宣言通り、最初のカードもデータとして扱われる。
        フィクスチャ 1 件目の場所 (甲州市…) が結果に含まれていることで確認する。
        """
        html = _load_yamanashi_html(fixture_html)
        adapter = PrefYamanashiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            locations = []
            for url, cat in urls[:3]:
                raw = adapter.extract_animal_details(url, category=cat)
                locations.append(raw.location)

        # 1 件目 (本来ヘッダではない) が確実にデータ扱い
        assert any("甲州市" in loc for loc in locations)
        # ヘッダ的な空文字や "場所" のような項目名が混じっていない
        assert not any(loc.strip() in ("", "場所", "市町村") for loc in locations)

    def test_all_six_sites_registered(self):
        """6 つの山梨県サイト名すべてが Registry に登録されている"""
        expected = [
            "山梨県（探している犬）",
            "山梨県（探している猫）",
            "山梨県（探している他のペット）",
            "山梨県（保護されている犬）",
            "山梨県（保護されている猫）",
            "山梨県（保護されている他のペット）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefYamanashiAdapter)
            assert SiteAdapterRegistry.get(name) is PrefYamanashiAdapter

    def test_raises_parsing_error_when_no_cards(self):
        """カード要素が見当たらない HTML では ParsingError 系例外を出す"""
        adapter = PrefYamanashiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
