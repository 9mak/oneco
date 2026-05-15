"""旭川市あにまある (douaicenter.jp) アダプターのテスト

list ページのフィクスチャと、detail ページの想定構造を持つ in-line HTML を使い、
WordPressListAdapter を介した抽出フローと registry 登録を検証する。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.douaicenter import DouaicenterAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# fixture HTML には不要だがインポートで registry に副作用登録される。
# pytest 内で site_config 依存の fixture は使わず、明示的に SiteConfig を構築する。


# 譲渡犬サイト想定。fixture 名と一致させる。
def _adoption_dog_site() -> SiteConfig:
    return SiteConfig(
        name="旭川市あにまある（譲渡犬）",
        prefecture="北海道",
        prefecture_code="01",
        list_url="https://www.douaicenter.jp/animal/list/transfer/dog",
        list_link_pattern="a[href*='/animal/']",
        category="adoption",
    )


def _shelter_other_dog_site() -> SiteConfig:
    return SiteConfig(
        name="旭川市あにまある（市民保護犬）",
        prefecture="北海道",
        prefecture_code="01",
        list_url="https://www.douaicenter.jp/other-animal/list/dog",
        list_link_pattern="a[href*='/other-animal/']",
        category="sheltered",
    )


# detail ページ想定 HTML (WordPress + dt/dd 構造)
DETAIL_HTML = """
<html><body>
  <article class="animal">
    <h1>犬No.2</h1>
    <img src="https://www.douaicenter.jp/wp-content/uploads/2026/03/dog2_main.jpg">
    <dl>
      <dt>種類</dt><dd>雑種</dd>
      <dt>性別</dt><dd>メス</dd>
      <dt>年齢</dt><dd>3歳</dd>
      <dt>毛色</dt><dd>茶</dd>
      <dt>体格</dt><dd>中型</dd>
      <dt>収容日</dt><dd>2026-03-15</dd>
      <dt>収容場所</dt><dd>旭川市動物愛護センター</dd>
      <dt>連絡先</dt><dd>0166-25-5271</dd>
    </dl>
    <img src="https://www.douaicenter.jp/wp-content/themes/header-logo.png">
    <img src="https://www.douaicenter.jp/wp-content/uploads/2026/03/dog2_sub.jpg">
  </article>
</body></html>
"""


class TestDouaicenterAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_from_fixture(self, fixture_html):
        adapter = DouaicenterAdapter(_adoption_dog_site())
        html = fixture_html("douaicenter__dog")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # 同一 detail に画像リンク + テキストリンクで 2 つ <a> があるが、
        # 重複除去で 1 件になる
        assert len(result) >= 1
        urls = [u for u, _cat in result]
        assert "https://www.douaicenter.jp/animal/14691" in urls
        # /animal/list/transfer などの一覧ページ自体は混入しない
        for u in urls:
            assert "/animal/list" not in u
        # category は site_config 由来
        assert all(cat == "adoption" for _u, cat in result)


class TestDouaicenterAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data(self, assert_raw_animal):
        adapter = DouaicenterAdapter(_adoption_dog_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.douaicenter.jp/animal/14691",
                category="adoption",
            )
        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="メス",
            age="3歳",
            color="茶",
            size="中型",
            shelter_date="2026-03-15",
            location="旭川市動物愛護センター",
            phone="0166-25-5271",
            source_url="https://www.douaicenter.jp/animal/14691",
            category="adoption",
        )

    def test_extract_filters_template_images_and_keeps_uploads(self):
        adapter = DouaicenterAdapter(_adoption_dog_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details("https://www.douaicenter.jp/animal/14691")
        # uploads 配下の 2 枚のみ残り、themes 配下のロゴは弾かれる
        assert len(raw.image_urls) == 2
        assert all("/wp-content/uploads/" in u for u in raw.image_urls)


class TestDouaicenterAdapterRegistry:
    """registry に 8 サイトすべて登録されていること"""

    EXPECTED_SITE_NAMES = (
        "旭川市あにまある（譲渡犬）",
        "旭川市あにまある（譲渡猫）",
        "旭川市あにまある（譲渡その他）",
        "旭川市あにまある（収容犬）",
        "旭川市あにまある（収容猫）",
        "旭川市あにまある（収容その他）",
        "旭川市あにまある（市民保護犬）",
        "旭川市あにまある（市民保護猫）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_douaicenter_adapter(self, site_name):
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is DouaicenterAdapter, (
            f"{site_name} が DouaicenterAdapter に紐付いていません: {cls}"
        )


class TestDouaicenterAdapterOtherAnimalCategory:
    """市民保護 (/other-animal/) ルートも list 抽出が動くこと"""

    def test_other_animal_link_pattern_matches(self):
        # /other-animal/{id} の擬似 list HTML
        html = """
        <html><body>
          <div class="animal-list">
            <ul>
              <li>
                <div class="animal-list-img-box">
                  <a href="https://www.douaicenter.jp/other-animal/9999">
                    <img src="/wp-content/uploads/x.jpg">
                  </a>
                </div>
              </li>
            </ul>
          </div>
        </body></html>
        """
        adapter = DouaicenterAdapter(_shelter_other_dog_site())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert "https://www.douaicenter.jp/other-animal/9999" in urls
        assert all(cat == "sheltered" for _u, cat in result)
