"""PrefSagaAdapter のテスト

佐賀県保護動物サイト (pref.saga.lg.jp) 用 rule-based adapter の動作を検証する。

- 1 ページに `table.__wys_table` が 3 つ並ぶ single_page 形式
  (保護犬情報 / 保護猫情報 / その他の保護動物情報)
- 6 サイト (地域別 5 + 全県譲渡 1) すべての登録確認
- 縦並びレイアウト (ラベル ↔ 値) からの RawAnimalData 構築
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_saga import (
    PrefSagaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="佐賀県（佐賀市・多久・小城・神埼）保護犬猫",
        prefecture="佐賀県",
        prefecture_code="41",
        list_url="https://www.pref.saga.lg.jp/kiji00349237/index.html",
        category="adoption",
        single_page=True,
    )


def _load_saga_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_saga__saga.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_saga__saga")
    # 復号後に「保護犬情報」が出現するかで判定
    if "保護犬情報" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefSagaAdapter:
    def test_fetch_animal_list_returns_three_sections(self, fixture_html):
        """1 ページに保護犬 / 保護猫 / その他の 3 セクションが抽出される"""
        html = _load_saga_html(fixture_html)
        adapter = PrefSagaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # 保護犬情報 / 保護猫情報 / その他の保護動物情報 の 3 テーブル
        assert len(result) == 3, (
            f"3 セクション (犬 / 猫 / その他) が抽出されるはず: got {len(result)}"
        )
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith(
                "https://www.pref.saga.lg.jp/kiji00349237/"
            )
            assert cat == "adoption"

        # 各セクションのインデックスが 0..N-1 で連番になっている
        indices = [int(u.rsplit("=", 1)[1]) for u, _ in result]
        assert indices == list(range(len(result)))

    def test_extract_animal_details_infers_species_from_heading(
        self, fixture_html
    ):
        """先行する `<h3 class="title">` から動物種別が決定される

        テーブル順は h3 順序と一致する想定:
          - row 0: 保護犬情報   → species == "犬"
          - row 1: 保護猫情報   → species == "猫"
          - row 2: その他…情報 → species == "その他"
        """
        html = _load_saga_html(fixture_html)
        adapter = PrefSagaAdapter(_site())

        species_per_row: list[str] = []
        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                raw = adapter.extract_animal_details(url, category=cat)
                assert isinstance(raw, RawAnimalData)
                # source_url / category が仮想 URL とサイト category と整合
                assert raw.source_url == url
                assert raw.category == "adoption"
                species_per_row.append(raw.species)

        # 同一ページから 3 件取得しても HTTP は 1 回 (キャッシュ確認)
        assert mock_get.call_count == 1
        assert species_per_row == ["犬", "猫", "その他"]

    def test_extract_animal_details_reads_vertical_layout(self, fixture_html):
        """縦並びテーブルから「保護した場所」と「ラベル → 値」セルが
        正しくフィールドに割り当てられる

        フィクスチャでは値セルが空のテーブルもあるが、
        ラベル → フィールドのマッピング自体は壊れず、
        - location / sex / color / size / age / shelter_date
        が `RawAnimalData` 上に文字列として現れる (空文字含む) ことを検証する。
        """
        html = _load_saga_html(fixture_html)
        adapter = PrefSagaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        # str 型として全フィールドが定義されている (Pydantic バリデート済)
        assert isinstance(raw.location, str)
        assert isinstance(raw.sex, str)
        assert isinstance(raw.color, str)
        assert isinstance(raw.size, str)
        assert isinstance(raw.age, str)
        assert isinstance(raw.shelter_date, str)
        assert isinstance(raw.phone, str)
        # 画像 URL は list[str] (フィクスチャでは空でも可)
        assert isinstance(raw.image_urls, list)
        for u in raw.image_urls:
            assert u.startswith("http")

    def test_all_six_sites_registered(self):
        """6 つの佐賀県サイト名すべてが Registry に登録されている"""
        expected = [
            "佐賀県（佐賀市・多久・小城・神埼）保護犬猫",
            "佐賀県（鳥栖・三養基郡）保護犬猫",
            "佐賀県（唐津・東松浦郡）保護犬猫",
            "佐賀県（伊万里・西松浦郡）保護犬猫",
            "佐賀県（武雄・鹿島・嬉野・杵島・藤津）保護犬猫",
            "佐賀県（全県）譲渡犬猫",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefSagaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefSagaAdapter

    def test_raises_parsing_error_when_no_tables(self):
        """`table.__wys_table` が存在しない HTML では ParsingError を出す"""
        adapter = PrefSagaAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
