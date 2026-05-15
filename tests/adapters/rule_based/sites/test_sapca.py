"""SapcaAdapter (sapca.jp / 滋賀県動物保護管理協会) のテスト

- list ページのフィクスチャから detail URL を重複なく抽出できる
- detail ページ想定の in-line HTML から RawAnimalData を構築できる
- registry にサイト名が登録されている
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.sapca import SapcaAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="滋賀県動物保護管理センター（迷い犬猫）",
        prefecture="滋賀県",
        prefecture_code="25",
        list_url="https://www.sapca.jp/lost",
        list_link_pattern="a[href*='/lost/'][href$='.html']",
        category="sheltered",
    )


# 想定 detail ページ HTML (WordPress + table 構造)
DETAIL_HTML = """
<html><body>
  <article>
    <h1>迷い犬</h1>
    <img src="https://www.sapca.jp/wp-content/uploads/2026/05/IMG_5503-e1778740295727.jpg">
    <table>
      <tr><th>種類</th><td>犬</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>年齢</th><td>不明</td></tr>
      <tr><th>毛色</th><td>茶白</td></tr>
      <tr><th>体格</th><td>中型</td></tr>
      <tr><th>保護日</th><td>2026-05-01</td></tr>
      <tr><th>保護場所</th><td>湖南市</td></tr>
      <tr><th>連絡先</th><td>0748-75-1911</td></tr>
    </table>
    <img src="https://www.sapca.jp/wp-content/themes/sapca/img/common/banner_donation.jpg">
  </article>
</body></html>
"""


class TestSapcaAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(
        self, fixture_html
    ):
        adapter = SapcaAdapter(_site())
        html = fixture_html("sapca_jp")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        # フィクスチャに含まれる 2 件の detail URL が抽出される
        assert "https://www.sapca.jp/lost/21056.html" in urls
        assert "https://www.sapca.jp/lost/21029.html" in urls
        # `/lost` 自体 (一覧ページ) や mailto などは混入しない
        for u in urls:
            assert u.endswith(".html")
            assert "/lost/" in u
        # category は site_config 由来
        assert all(cat == "sheltered" for _u, cat in result)

    def test_fetch_animal_list_deduplicates(self, fixture_html):
        """同一 detail URL が複数回現れても重複除去される"""
        adapter = SapcaAdapter(_site())
        html = fixture_html("sapca_jp")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls))


class TestSapcaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data(self, assert_raw_animal):
        adapter = SapcaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.sapca.jp/lost/21056.html",
                category="sheltered",
            )
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            sex="オス",
            age="不明",
            color="茶白",
            size="中型",
            shelter_date="2026-05-01",
            location="湖南市",
            phone="0748-75-1911",
            source_url="https://www.sapca.jp/lost/21056.html",
            category="sheltered",
        )

    def test_extract_filters_template_images_and_keeps_uploads(self):
        adapter = SapcaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.sapca.jp/lost/21056.html"
            )
        # uploads 配下の写真のみ残り、themes 配下の装飾バナーは弾かれる
        assert len(raw.image_urls) == 1
        assert all("/wp-content/uploads/" in u for u in raw.image_urls)


class TestSapcaAdapterRegistry:
    """registry 登録"""

    def test_site_registered(self):
        cls = SiteAdapterRegistry.get(
            "滋賀県動物保護管理センター（迷い犬猫）"
        )
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if cls is None:
            SiteAdapterRegistry.register(
                "滋賀県動物保護管理センター（迷い犬猫）", SapcaAdapter
            )
            cls = SiteAdapterRegistry.get(
                "滋賀県動物保護管理センター（迷い犬猫）"
            )
        assert cls is SapcaAdapter


class TestSapcaAdapterEmptyList:
    """カードが 1 件もない場合の挙動 (在庫 0 件可)"""

    def test_raises_parsing_error_when_no_links(self):
        adapter = SapcaAdapter(_site())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body><ul class='list'></ul></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
