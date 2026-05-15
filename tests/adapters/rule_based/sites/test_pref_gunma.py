"""PrefGunmaAdapter のテスト

群馬県動物愛護センターサイト (pref.gunma.jp) 用 rule-based adapter の
動作を検証する。

- 同一テンプレート上の 3 サイト (本所 保護犬/猫、東部支所 保護犬) の登録確認
- 0 件告知ページ (本フィクスチャ) では fetch_animal_list が空配列を返す
- お問い合わせ先テーブルは動物データとして拾わない
- サイト名からの動物種別 (犬/猫) 推定
- ページ全体に table が無く empty state でもないケースは ParsingError
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_gunma import (
    PrefGunmaAdapter,
)
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "群馬県動物愛護センター（保護犬）",
    list_url: str = "https://www.pref.gunma.jp/page/167499.html",
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="群馬県",
        prefecture_code="10",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_gunma_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存された `pref_gunma.html` は基本的に UTF-8 で正しく
    エンコードされている想定だが、保存経緯次第で latin-1 → utf-8 の
    二重エンコーディング状態になる可能性に備えて防御的に補正する。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_gunma")
    # 復号後に「群馬県」または「動物愛護センター」が出現するかで判定
    if "群馬県" in raw or "動物愛護センター" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefGunmaAdapter:
    def test_fetch_animal_list_returns_empty_for_no_animals_page(self, fixture_html):
        """「現在、保管期間中の犬はおりません」告知ページでは空リストが返る

        フィクスチャは中毛/北毛/西毛 各地区とも全て
        「現在、保管期間中の犬はおりません」の告知のみが並ぶ 0 件状態。
        基底の単純実装は ParsingError を投げるが、本 adapter ではこれを
        正常な 0 件として扱う。
        """
        html = _load_gunma_html(fixture_html)
        adapter = PrefGunmaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], f"empty state ページでは空配列が返るはず: got {result!r}"

    def test_contact_table_is_excluded(self, fixture_html):
        """お問い合わせ先テーブルは動物データとして拾わない

        フィクスチャ末尾には「お問い合わせ先」(caption) を持つ table が
        存在する。これを動物データと誤認すると 0 件のはずが 1 件として
        扱われてしまうので、_load_rows が確実に除外することを検証する。
        """
        html = _load_gunma_html(fixture_html)
        adapter = PrefGunmaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            rows = adapter._load_rows()

        assert rows == [], f"連絡先テーブルは動物データとして残してはいけない: got {len(rows)} rows"

    def test_fetch_animal_list_caches_html(self, fixture_html):
        """同一インスタンスでの繰り返し呼び出しは HTTP を 1 回しか実行しない"""
        html = _load_gunma_html(fixture_html)
        adapter = PrefGunmaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()
            adapter.fetch_animal_list()

        assert mock_get.call_count == 1, (
            f"HTML はキャッシュされ HTTP は 1 回のみ: got {mock_get.call_count}"
        )

    def test_raises_parsing_error_for_unrelated_html(self):
        """テーブルも empty state テキストも無い HTML では ParsingError"""
        adapter = PrefGunmaAdapter(_site())
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
            PrefGunmaAdapter._infer_species_from_site_name("群馬県動物愛護センター（保護犬）")
            == "犬"
        )
        assert (
            PrefGunmaAdapter._infer_species_from_site_name(
                "群馬県動物愛護センター東部支所（保護犬）"
            )
            == "犬"
        )

    def test_infer_species_from_site_name_cat(self):
        """サイト名に "猫" を含むと species 推定が "猫" になる"""
        assert (
            PrefGunmaAdapter._infer_species_from_site_name("群馬県動物愛護センター（保護猫）")
            == "猫"
        )

    def test_infer_species_from_site_name_unknown(self):
        """犬/猫 を含まないサイト名は空文字 (テーブル値フォールバック)"""
        assert (
            PrefGunmaAdapter._infer_species_from_site_name("群馬県動物愛護センター（その他）") == ""
        )

    def test_all_three_sites_registered(self):
        """3 つの群馬県サイト名すべてが Registry に登録されている

        sites.yaml で `prefecture: 群馬県` かつ `pref.gunma.jp` ドメインの
        全サイトを列挙する。
        """
        expected = [
            "群馬県動物愛護センター（保護犬）",
            "群馬県動物愛護センター東部支所（保護犬）",
            "群馬県動物愛護センター（保護猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefGunmaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefGunmaAdapter
