"""CityNagasakiLgAdapter のテスト

長崎市動物愛護管理センター (city.nagasaki.lg.jp/site/doubutsuaigo/) 用
rule-based adapter の動作を検証する。

- single_page 形式 (1 ページに複数記事 / 在庫 0 件のときは告知のみ)
- 在庫 0 件相当 (本フィクスチャは 1 件の告知記事のみ) でも動作する
- 2 サイト (犬里親募集 / 猫里親募集) すべての登録確認
- mojibake (二重 UTF-8) の自動補正
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_nagasaki_lg import (
    CityNagasakiLgAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "長崎市動物愛護管理センター（犬里親募集）",
    list_url: str = "https://www.city.nagasaki.lg.jp/site/doubutsuaigo/list7-19.html",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="長崎県",
        prefecture_code="42",
        list_url=list_url,
        category="adoption",
        single_page=True,
    )


def _load_nagasaki_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_nagasaki_lg.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_nagasaki_lg")
    if "長崎" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityNagasakiLgAdapter:
    def test_fetch_animal_list_from_raw_fixture(self, fixture_html):
        """mojibake 状態の生 fixture からも `list_pack` を抽出できる

        adapter は mojibake 補正を自前で行うため、生 HTML をそのまま
        `_http_get` のモック戻り値として渡しても動作する。
        フィクスチャは現時点で 1 件の記事 (告知) のみを含む。
        """
        raw = fixture_html("city_nagasaki_lg")
        adapter = CityNagasakiLgAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw):
            result = adapter.fetch_animal_list()

        # フィクスチャには `<li>` が 1 件含まれる
        assert len(result) == 1
        url, cat = result[0]
        assert "#row=0" in url
        assert url.startswith(
            "https://www.city.nagasaki.lg.jp/site/doubutsuaigo/"
        )
        assert cat == "adoption"

    def test_fetch_animal_list_preprocessed_html(self, fixture_html):
        """mojibake 補正済みの HTML を渡しても同等に動作する"""
        html = _load_nagasaki_html(fixture_html)
        adapter = CityNagasakiLgAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1

    def test_extract_animal_details_from_fixture(self, fixture_html):
        """フィクスチャの 1 件目から RawAnimalData を構築できる

        - 種別はサイト名 (犬里親募集) から「犬」と推定される
        - shelter_date は `span.article_date` の「2026年4月21日更新」から
          ISO 8601 (`2026-04-21`) に変換される
        - location は記事タイトル (告知文) がそのまま入る
        - source_url は仮想 URL (#row=0) になる
        """
        raw = fixture_html("city_nagasaki_lg")
        adapter = CityNagasakiLgAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            data = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(data, RawAnimalData)
        assert data.species == "犬"
        assert data.shelter_date == "2026-04-21"
        # 告知記事のタイトル文字列が location に格納される
        assert "見学" in data.location or "保護犬" in data.location
        assert data.source_url == first_url
        assert data.category == "adoption"

    def test_species_inference_for_cat_site(self, fixture_html):
        """猫里親募集サイトでは species が「猫」と推定される"""
        raw = fixture_html("city_nagasaki_lg")
        adapter = CityNagasakiLgAdapter(
            _site(
                name="長崎市動物愛護管理センター（猫里親募集）",
                list_url=(
                    "https://www.city.nagasaki.lg.jp/site/doubutsuaigo/"
                    "list7-18.html"
                ),
            )
        )

        with patch.object(adapter, "_http_get", return_value=raw):
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            data = adapter.extract_animal_details(first_url, category=category)

        assert data.species == "猫"

    def test_fetch_animal_list_empty_state_returns_empty(self):
        """`info_list_wrap` はあるが `list_pack` が無い場合は空リストを返す

        在庫 0 件の期間に告知文だけが入るケースを想定。
        """
        adapter = CityNagasakiLgAdapter(_site())
        empty_html = (
            "<html><body>長崎市"
            "<div id='main_body'>"
            "<div class='info_list_wrap'>"
            "<p>現在、里親募集の犬はおりません。</p>"
            "</div></div></body></html>"
        )
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_synthetic_multiple_list_packs(self, fixture_html):
        """合成 HTML で複数件の `list_pack` を抽出できる

        フィクスチャは 1 件のみだが、実運用では複数件並ぶことを想定し、
        `list_pack` を 2 件追加した合成 HTML で複数件抽出を検証する。
        """
        base = _load_nagasaki_html(fixture_html)
        soup = BeautifulSoup(base, "html.parser")
        ul = soup.select_one("div.info_list ul")
        assert ul is not None

        synthetic = BeautifulSoup(
            """
            <li>
              <div class="list_pack">
                <div class="article_txt">
                  <span class="article_date">2026年5月10日更新</span>
                  <span class="article_title">
                    <a href="/site/doubutsuaigo/3001.html">里親募集中のミックス犬</a>
                  </span>
                </div>
              </div>
            </li>
            <li>
              <div class="list_pack">
                <div class="article_txt">
                  <span class="article_date">2026年5月12日更新</span>
                  <span class="article_title">
                    <a href="/site/doubutsuaigo/3002.html">柴犬の里親募集</a>
                  </span>
                </div>
              </div>
            </li>
            """,
            "html.parser",
        )
        for el in synthetic.find_all("li", recursive=False):
            ul.append(el)

        synthetic_html = str(soup)
        adapter = CityNagasakiLgAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value=synthetic_html
        ) as mock_get:
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        # 同一ページから複数取得しても HTTP は 1 回だけ
        assert mock_get.call_count == 1
        # フィクスチャの 1 件 + 追加 2 件 = 計 3 件
        assert len(urls) == 3
        for u, cat in urls:
            assert "#row=" in u
            assert cat == "adoption"

        # 2 件目 (追加の最初) の検証
        second = raws[1]
        assert isinstance(second, RawAnimalData)
        assert second.species == "犬"
        assert second.shelter_date == "2026-05-10"
        assert "ミックス犬" in second.location

        # 3 件目 (追加の 2 番目) の検証
        third = raws[2]
        assert third.shelter_date == "2026-05-12"
        assert "柴犬" in third.location

    def test_extract_animal_details_does_not_refetch(self, fixture_html):
        """extract_animal_details を複数回呼んでも HTTP は 1 回しか叩かない"""
        raw = fixture_html("city_nagasaki_lg")
        adapter = CityNagasakiLgAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=raw) as mock_get:
            urls = adapter.fetch_animal_list()
            assert len(urls) >= 1
            for _ in range(3):
                adapter.extract_animal_details(urls[0][0])
        assert mock_get.call_count == 1

    def test_mojibake_is_repaired_when_loading_rows(self, fixture_html):
        """mojibake 状態の生 HTML を渡しても _html_cache が補正後 HTML になる"""
        raw = fixture_html("city_nagasaki_lg")
        adapter = CityNagasakiLgAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=raw):
            adapter.fetch_animal_list()
        assert adapter._html_cache is not None
        # 補正後の HTML には「長崎」が含まれるはず
        assert "長崎" in adapter._html_cache

    def test_species_inference_helper(self):
        """サイト名で species が決まる (犬里親募集→犬 / 猫里親募集→猫)"""
        assert (
            CityNagasakiLgAdapter._infer_species_from_site_name(
                "長崎市動物愛護管理センター（犬里親募集）"
            )
            == "犬"
        )
        assert (
            CityNagasakiLgAdapter._infer_species_from_site_name(
                "長崎市動物愛護管理センター（猫里親募集）"
            )
            == "猫"
        )

    def test_parse_iso_date_helper(self):
        """日付パーサが 「YYYY年M月D日更新」を ISO 8601 に変換する"""
        assert (
            CityNagasakiLgAdapter._parse_iso_date("2026年4月21日更新")
            == "2026-04-21"
        )
        assert (
            CityNagasakiLgAdapter._parse_iso_date("2026/5/3")
            == "2026-05-03"
        )
        # 該当パターンが無ければ空文字
        assert CityNagasakiLgAdapter._parse_iso_date("") == ""
        assert CityNagasakiLgAdapter._parse_iso_date("更新情報なし") == ""

    def test_all_two_sites_registered(self):
        """2 つの長崎市サイト名すべてが Registry に登録されている"""
        expected = [
            "長崎市動物愛護管理センター（犬里親募集）",
            "長崎市動物愛護管理センター（猫里親募集）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityNagasakiLgAdapter)
            assert SiteAdapterRegistry.get(name) is CityNagasakiLgAdapter

    def test_raises_parsing_error_when_no_main_block(self):
        """本文ブロックも告知も無い HTML では ParsingError 系例外を出す"""
        adapter = CityNagasakiLgAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
