"""PrefKyotoAdapter のテスト

京都府保護動物サイト (pref.kyoto.jp) 用 rule-based adapter の動作を検証する。

- 同一テンプレート上の 5 サイト (山城北/山城南/南丹) の登録確認
- 0 件告知ページ (本フィクスチャ) では fetch_animal_list が空配列を返す
- サイト名からの動物種別 (犬/猫) 推定
- ページ全体に table が無く empty state でもないケースは ParsingError
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_kyoto import (
    PrefKyotoAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "京都府 山城北保健所（迷子犬）",
    list_url: str = "https://www.pref.kyoto.jp/yamashiro/ho-kita/121852245466.html",
    category: str = "lost",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="京都府",
        prefecture_code="26",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_kyoto_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_kyoto__yamashiro.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_kyoto__yamashiro")
    # 復号後に「迷子犬情報」または「保護している」が出現するかで判定
    if "迷子犬情報" in raw or "保護している" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefKyotoAdapter:
    def test_fetch_animal_list_returns_empty_for_no_animals_page(
        self, fixture_html
    ):
        """「保護している犬はありません」告知ページでは空リストが返る

        フィクスチャは「現在、当所で保護している犬はありません。」の
        告知のみが本文に並ぶ 0 件状態のページ。基底の単純実装は
        ParsingError を投げるが、本 adapter ではこれを正常な 0 件として扱う。
        """
        html = _load_kyoto_html(fixture_html)
        adapter = PrefKyotoAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], (
            f"empty state ページでは空配列が返るはず: got {result!r}"
        )

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_kyoto_html(fixture_html)
        adapter = PrefKyotoAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state テキストも無い HTML では ParsingError"""
        adapter = PrefKyotoAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><p>無関係なページ</p></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_infer_species_from_site_name_dog(self):
        """サイト名に "犬" を含むと species 推定が "犬" になる"""
        assert (
            PrefKyotoAdapter._infer_species_from_site_name(
                "京都府 山城北保健所（迷子犬）"
            )
            == "犬"
        )
        assert (
            PrefKyotoAdapter._infer_species_from_site_name(
                "京都府 南丹保健所（迷子犬）"
            )
            == "犬"
        )

    def test_infer_species_from_site_name_cat(self):
        """サイト名に "猫" を含むと species 推定が "猫" になる"""
        assert (
            PrefKyotoAdapter._infer_species_from_site_name(
                "京都府 山城北保健所（迷子猫）"
            )
            == "猫"
        )
        assert (
            PrefKyotoAdapter._infer_species_from_site_name(
                "京都府 南丹保健所（迷子猫）"
            )
            == "猫"
        )

    def test_infer_species_from_site_name_unknown(self):
        """犬/猫 を含まないサイト名 (飼い主不明動物) は空文字"""
        assert (
            PrefKyotoAdapter._infer_species_from_site_name(
                "京都府 山城南保健所（飼い主不明動物）"
            )
            == ""
        )

    def test_all_five_sites_registered(self):
        """5 つの京都府サイト名すべてが Registry に登録されている

        sites.yaml で `prefecture: 京都府` かつ `pref.kyoto.jp` ドメインの
        全サイトを列挙する。京都市ペットラブ (専用ドメイン) は別 adapter
        の責務なので含まない。
        """
        expected = [
            "京都府 山城北保健所（迷子犬）",
            "京都府 山城北保健所（迷子猫）",
            "京都府 山城南保健所（飼い主不明動物）",
            "京都府 南丹保健所（迷子犬）",
            "京都府 南丹保健所（迷子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefKyotoAdapter)
            assert SiteAdapterRegistry.get(name) is PrefKyotoAdapter
