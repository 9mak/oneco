"""CityToyonakaAdapter のテスト

豊中市 (大阪府) サイト (city.toyonaka.osaka.jp) 用 rule-based adapter の
動作を検証する。

- 対象 URL は「ペットが迷子になった時の対応方法について」案内ページで、
  動物リストを持たない。adapter は在庫 0 件 (空リスト) として扱う。
- 案内ページ判定が外れた場合は ParsingError を投げる安全側の挙動を確認。
- Registry へのサイト名登録を確認。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_toyonaka import (
    CityToyonakaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="豊中市（迷子犬猫）",
        prefecture="大阪府",
        prefecture_code="27",
        list_url=(
            "https://www.city.toyonaka.osaka.jp/"
            "kurashi/pettp-inuneko/maigo.html"
        ),
        category="lost",
        single_page=True,
    )


def _load_toyonaka_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_toyonaka_osaka_jp.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_toyonaka_osaka_jp")
    if "豊中" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityToyonakaAdapter:
    def test_fetch_animal_list_returns_empty_for_announcement_page(
        self, fixture_html
    ):
        """案内ページなので空リストが返る (ParsingError は発生しない)"""
        html = _load_toyonaka_html(fixture_html)
        adapter = CityToyonakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_announcement_pattern_detection(self, fixture_html):
        """案内ページと判定する内部ヘルパが期待どおり動く"""
        html = _load_toyonaka_html(fixture_html)
        assert CityToyonakaAdapter._is_announcement_page(html) is True

    def test_non_announcement_unknown_layout_raises(self):
        """案内ページパターンに一致せず行も無いときは ParsingError"""
        adapter = CityToyonakaAdapter(_site())
        # 案内パターンに一致しないが、データ行も持たない HTML
        unknown_html = (
            "<html><head><title>豊中市</title></head>"
            "<body><h1>その他のページ</h1></body></html>"
        )
        with patch.object(adapter, "_http_get", return_value=unknown_html):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_http_called_only_once(self, fixture_html):
        """fetch_animal_list 1 回呼出しでも HTTP は 1 回だけ (キャッシュ)"""
        html = _load_toyonaka_html(fixture_html)
        adapter = CityToyonakaAdapter(_site())

        with patch.object(
            adapter, "_http_get", return_value=html
        ) as mock_get:
            adapter.fetch_animal_list()
            # 案内ページ判定で空が返ったあと、再度呼んでもキャッシュ利用
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1

    def test_site_registered(self):
        """sites.yaml の `豊中市（迷子犬猫）` が Registry に登録済み"""
        name = "豊中市（迷子犬猫）"
        # 他テストで registry が clear される可能性に備えて冪等再登録
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, CityToyonakaAdapter)
        assert SiteAdapterRegistry.get(name) is CityToyonakaAdapter
