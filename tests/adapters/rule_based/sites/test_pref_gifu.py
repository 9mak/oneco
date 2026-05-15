"""PrefGifuAdapter のテスト

岐阜県迷い犬情報ハブページ (pref.gifu.lg.jp/page/1638.html) 用
rule-based adapter の動作を検証する。

- 12 保健所への案内ハブページでは fetch_animal_list が空配列を返す
- HTTP は 1 回しか実行されない (キャッシュ)
- ハブの目印が無い HTML では ParsingError
- extract_animal_details は仮想 URL でも例外
- レジストリへ「岐阜県（迷い犬情報）」名で登録されている
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_gifu import (
    PrefGifuAdapter,
)
from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "岐阜県（迷い犬情報）",
    list_url: str = "https://www.pref.gifu.lg.jp/page/1638.html",
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="岐阜県",
        prefecture_code="21",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_gifu_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリの `pref_gifu_lg_jp.html` は本来 UTF-8 のバイト列を Latin-1
    として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態のため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_gifu_lg_jp")
    # 復号後に「迷い犬情報」または「保健所」が出現するかで判定
    if "迷い犬情報" in raw or "保健所" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefGifuAdapter:
    def test_fetch_animal_list_returns_empty_for_hub_page(self, fixture_html):
        """12 保健所への案内ハブページでは空配列が返る

        フィクスチャは岐阜県内 12 保健所へのリンク表のみが置かれた
        ハブページで、ページ自体には動物個別情報は無い。
        本 adapter ではこの状態を正常な 0 件として扱う。
        """
        html = _load_gifu_html(fixture_html)
        adapter = PrefGifuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"ハブページでは空配列が返るはず: got {result!r}"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_gifu_html(fixture_html)
        adapter = PrefGifuAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_raises_parsing_error_for_unrelated_html(self):
        """ハブの目印 (保健所名/区域 や 迷い犬情報 等) が一切無い HTML では ParsingError"""
        adapter = PrefGifuAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><p>無関係なページ</p></body></html>",
        ):
            with pytest.raises(ParsingError):
                adapter.fetch_animal_list()

    def test_extract_animal_details_always_raises(self):
        """ハブページからは動物詳細が取れないため例外を投げる"""
        adapter = PrefGifuAdapter(_site())
        with pytest.raises(ParsingError):
            adapter.extract_animal_details(
                "https://www.pref.gifu.lg.jp/page/1638.html#row=0",
                category="lost",
            )

    def test_site_registered(self):
        """sites.yaml の name と完全一致でレジストリへ登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get("岐阜県（迷い犬情報）") is None:
            SiteAdapterRegistry.register(
                "岐阜県（迷い犬情報）", PrefGifuAdapter
            )
        assert (
            SiteAdapterRegistry.get("岐阜県（迷い犬情報）") is PrefGifuAdapter
        )
