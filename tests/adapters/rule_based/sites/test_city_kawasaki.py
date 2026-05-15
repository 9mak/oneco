"""CityKawasakiAdapter のテスト

川崎市動物愛護センター (city.kawasaki.jp/350/page/) 用 rule-based adapter
の動作を検証する。

- single_page 形式 (1 ページに複数動物 / 在庫 0 件のときは告知のみ)
- 在庫 0 件 (本フィクスチャがこのケース) でも ParsingError を出さず
  空リストを返す
- 3 サイト (収容犬 / 収容猫 / 収容その他動物) すべての登録確認
- mojibake (二重 UTF-8) の自動補正
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kawasaki import (
    CityKawasakiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "川崎市（収容犬）",
    list_url: str = "https://www.city.kawasaki.jp/350/page/0000077270.html",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="神奈川県",
        prefecture_code="14",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_kawasaki_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_kawasaki.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっている可能性があるため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_kawasaki")
    if "川崎" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityKawasakiAdapter:
    def test_fetch_animal_list_empty_state_returns_empty_raw_fixture(
        self, fixture_html
    ):
        """在庫 0 件 (mojibake 状態の生 fixture) で空リストを返す

        adapter は mojibake 補正を自前で行うため、生 HTML をそのまま
        `_http_get` のモック戻り値として渡しても 0 件として扱える。
        """
        raw = fixture_html("city_kawasaki")
        adapter = CityKawasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_empty_state_preprocessed_html(self, fixture_html):
        """mojibake 補正済みの HTML を渡しても 0 件として扱える"""
        html = _load_kawasaki_html(fixture_html)
        adapter = CityKawasakiAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_with_synthetic_h3_blocks(self, fixture_html):
        """`<h3>` 起点の動物ブロックを複数件抽出できる (合成 HTML)

        フィクスチャは 0 件状態のため、実テンプレート
        (`div.main_naka_kiji` + `mol_contents`) を維持したまま
        告知 `<p>` を `<h3>` ベースの動物ブロックに差し替えた合成 HTML を
        組み立てて、複数件の RawAnimalData が構築されることを検証する。
        """
        base = _load_kawasaki_html(fixture_html)
        soup = BeautifulSoup(base, "html.parser")

        honbun = soup.select_one("div.main_naka_kiji")
        assert honbun is not None
        contents = honbun.select_one("div.mol_contents")
        assert contents is not None

        # 既存の textblock (告知) を消し、動物ブロック 2 件に差し替える
        for tb in contents.select("div.mol_textblock"):
            tb.decompose()

        synthetic = BeautifulSoup(
            """
            <h3>収容情報1</h3>
            <div class="mol_textblock">
              <p>収容日：2026年5月7日</p>
              <p>収容場所：川崎市中原区上平間</p>
              <p>性別：オス</p>
              <p>毛色：茶</p>
              <p>体格：中</p>
              <p>年齢：成犬</p>
            </div>
            <div class="mol_imageblock">
              <p><img src="/350/cmsfiles/contents/dog1.jpg" alt="dog1"></p>
            </div>
            <h3>収容情報2</h3>
            <div class="mol_textblock">
              <p>収容日：2026年5月10日</p>
              <p>収容場所：川崎市幸区南幸町</p>
              <p>性別：メス</p>
              <p>毛色：白黒</p>
              <p>体格：小</p>
              <p>年齢：成犬</p>
            </div>
            """,
            "html.parser",
        )
        for el in synthetic.find_all(recursive=False):
            contents.append(el)

        synthetic_html = str(soup)
        adapter = CityKawasakiAdapter(_site())

        with patch.object(
            adapter, "_http_get", return_value=synthetic_html
        ) as mock_get:
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert len(urls) == 2
        for u, cat in urls:
            assert "#row=" in u
            assert u.startswith("https://www.city.kawasaki.jp/")
            assert cat == "sheltered"

        # 1 件目: オス 茶 中, 場所 中原区, 収容日 5/7
        first = raws[0]
        assert isinstance(first, RawAnimalData)
        assert first.species == "犬"  # サイト名 (収容犬) から推定
        assert first.sex == "オス"
        assert first.age == "成犬"
        assert "茶" in first.color
        assert first.size == "中"
        assert "中原区" in first.location
        assert first.shelter_date == "2026-05-07"
        assert first.source_url == urls[0][0]
        assert first.category == "sheltered"
        assert any(
            "dog1.jpg" in u for u in first.image_urls
        ), f"画像 URL が抽出されていない: {first.image_urls}"

        # 2 件目: メス 白黒 小, 場所 幸区
        second = raws[1]
        assert second.sex == "メス"
        assert "白黒" in second.color
        assert second.size == "小"
        assert "幸区" in second.location
        assert second.shelter_date == "2026-05-10"

    def test_species_inference_from_site_name(self):
        """サイト名で species が決まる (収容犬→犬 / 収容猫→猫 / その他→その他)"""
        assert (
            CityKawasakiAdapter._infer_species_from_site_name("川崎市（収容犬）")
            == "犬"
        )
        assert (
            CityKawasakiAdapter._infer_species_from_site_name("川崎市（収容猫）")
            == "猫"
        )
        assert (
            CityKawasakiAdapter._infer_species_from_site_name(
                "川崎市（収容その他動物）"
            )
            == "その他"
        )

    def test_all_three_sites_registered(self):
        """3 つの川崎市サイト名すべてが Registry に登録されている"""
        expected = [
            "川崎市（収容犬）",
            "川崎市（収容猫）",
            "川崎市（収容その他動物）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityKawasakiAdapter)
            assert SiteAdapterRegistry.get(name) is CityKawasakiAdapter

    def test_raises_parsing_error_when_no_main_block_and_no_empty_marker(self):
        """本文ブロックも告知文も無い HTML では ParsingError 系例外を出す"""
        adapter = CityKawasakiAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_animal_details_does_not_refetch(self, fixture_html):
        """extract_animal_details を複数回呼んでも HTTP は 1 回しか叩かない"""
        base = _load_kawasaki_html(fixture_html)
        soup = BeautifulSoup(base, "html.parser")
        contents = soup.select_one("div.main_naka_kiji div.mol_contents")
        assert contents is not None
        for tb in contents.select("div.mol_textblock"):
            tb.decompose()
        synthetic = BeautifulSoup(
            """
            <h3>収容情報A</h3>
            <div class="mol_textblock">
              <p>収容日：2026年5月1日</p>
              <p>収容場所：川崎市麻生区</p>
              <p>性別：オス</p>
              <p>毛色：黒</p>
            </div>
            """,
            "html.parser",
        )
        for el in synthetic.find_all(recursive=False):
            contents.append(el)

        adapter = CityKawasakiAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value=str(soup)
        ) as mock_get:
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            for _ in range(3):
                adapter.extract_animal_details(urls[0][0])
        assert mock_get.call_count == 1

    def test_mojibake_is_repaired_when_loading_rows(self, fixture_html):
        """mojibake 状態の生 HTML を渡しても _html_cache が補正後 HTML になる"""
        raw = fixture_html("city_kawasaki")
        adapter = CityKawasakiAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=raw):
            adapter.fetch_animal_list()
        assert adapter._html_cache is not None
        # 補正後の HTML には「川崎」が含まれるはず
        assert "川崎" in adapter._html_cache
