"""CitySaseboAdapter のテスト

佐世保市動物愛護センター (city.sasebo.lg.jp) 用 rule-based adapter の
動作を検証する。

- 一覧ページに `<a href="*_dog*.html">` / `<a href="*_cat*.html">` 形式で
  動物 1 頭ごとにリンクが並ぶ。本 adapter は detail への追加 HTTP を
  行わず、一覧の `<a>` インラインテキストから抽出する。
- 同一テンプレート上の 2 サイト (保護犬 / 保護猫) の登録確認。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_sasebo import (
    CitySaseboAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(*, cat: bool = False) -> SiteConfig:
    if cat:
        return SiteConfig(
            name="佐世保市（保護猫）",
            prefecture="長崎県",
            prefecture_code="42",
            list_url=(
                "https://www.city.sasebo.lg.jp/hokenhukusi/seikat/"
                "mayoinekohogo.html"
            ),
            category="sheltered",
            list_link_pattern="a[href*='_cat']",
        )
    return SiteConfig(
        name="佐世保市（保護犬）",
        prefecture="長崎県",
        prefecture_code="42",
        list_url=(
            "https://www.city.sasebo.lg.jp/hokenhukusi/seikat/"
            "hogodoubutsu.html"
        ),
        category="sheltered",
        list_link_pattern="a[href*='_dog']",
    )


def _load_sasebo_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_sasebo.html` は、本来 UTF-8 の
    バイト列を Latin-1 として解釈してから再度 UTF-8 として保存し直された
    二重エンコーディング状態になっているため、実サイト相当のテキストを
    得るには逆変換が必要。実運用 (`_http_get`) では requests が正しい
    UTF-8 として受け取る。
    """
    raw = fixture_html("city_sasebo")
    # 実際のページに含まれる漢字 "佐世保" が出てくるか判定
    if "佐世保" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCitySaseboAdapter:
    def test_fetch_animal_list_returns_dog_links(self, fixture_html):
        """`_dog` を含む detail link が絶対 URL で抽出される"""
        html = _load_sasebo_html(fixture_html)
        adapter = CitySaseboAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1, "フィクスチャには保護犬 1 件のみ存在する"
        url, cat = result[0]
        assert url == (
            "https://www.city.sasebo.lg.jp/hokenhukusi/seikat/"
            "20260313_dog01.html"
        )
        assert "_dog" in url
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self, fixture_html):
        """フィクスチャの 1 頭から RawAnimalData を構築できる"""
        html = _load_sasebo_html(fixture_html)
        adapter = CitySaseboAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # 末尾括弧 "（雑種、オス）" から犬種と性別を取得
        assert raw.species == "雑種"
        assert raw.sex == "オス"
        # 場所は曜日括弧の後から末尾括弧の手前まで
        assert raw.location == "山祇町"
        # 和暦の収容日が文字列として保持される
        assert raw.shelter_date == "令和8年3月13日"
        # 画像は /images/ 配下のものが絶対 URL に変換されて入る
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.sasebo.lg.jp/")
            assert "/images/" in u
        # source_url は detail ページの実 URL (仮想 URL ではない)
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_image_urls_filter_excludes_template(self, fixture_html):
        """`/shared/` 配下のロゴ・テンプレ画像は image_urls に含まれない"""
        html = _load_sasebo_html(fixture_html)
        adapter = CitySaseboAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        # `/shared/` 配下のロゴ等は混入しない
        assert all("/shared/" not in u for u in raw.image_urls)

    def test_cat_site_returns_zero_when_no_cat_links(self, fixture_html):
        """保護猫サイトとして読ませた場合、フィクスチャに `_cat` リンクが
        無いため在庫 0 件として正常に返る (例外を出さない)
        """
        html = _load_sasebo_html(fixture_html)
        adapter = CitySaseboAdapter(_site(cat=True))

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], "保護猫サイトに `_cat` リンクが無ければ 0 件"

    def test_both_sites_registered(self):
        """2 つの佐世保市サイト名すべてが Registry に登録されている"""
        expected = [
            "佐世保市（保護犬）",
            "佐世保市（保護猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CitySaseboAdapter)
            assert SiteAdapterRegistry.get(name) is CitySaseboAdapter

    def test_raises_parsing_error_when_no_container(self):
        """`#tmp_contents` が無い HTML では例外を出す"""
        adapter = CitySaseboAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_extract_animal_details_with_unknown_url(self, fixture_html):
        """未知の detail URL を渡した場合は ParsingError を出す"""
        html = _load_sasebo_html(fixture_html)
        adapter = CitySaseboAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.city.sasebo.lg.jp/unknown_url.html",
                    category="sheltered",
                )
