"""DouaiPrefTochigiAdapter (douai.pref.tochigi.lg.jp) アダプターのテスト

list ページのフィクスチャと、detail ページの想定構造を持つ in-line HTML を
用いて、WordPressListAdapter を介した抽出フローと registry 登録を検証する。

栃木県動物愛護指導センターは 3 サイト (保護動物 / 譲渡動物 / 迷子動物) で
同一テンプレートを共有する list+detail 構造。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.douai_pref_tochigi import (
    DouaiPrefTochigiAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


# ─────────────────── SiteConfig helpers ───────────────────


def _custody_site() -> SiteConfig:
    """保護動物サイト (sheltered) - fixture と一致"""
    return SiteConfig(
        name="栃木県動物愛護指導センター（保護動物）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://www.douai.pref.tochigi.lg.jp/work_category/custody/",
        category="sheltered",
        list_link_pattern="a[href*='/news/']",
    )


def _adoption_site() -> SiteConfig:
    """譲渡動物サイト (adoption)"""
    return SiteConfig(
        name="栃木県動物愛護指導センター（譲渡動物）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://www.douai.pref.tochigi.lg.jp/jyouto/",
        category="adoption",
        list_link_pattern="a[href*='/news/']",
    )


def _lost_site() -> SiteConfig:
    """迷子動物サイト (lost)"""
    return SiteConfig(
        name="栃木県動物愛護指導センター（迷子動物）",
        prefecture="栃木県",
        prefecture_code="09",
        list_url="https://www.douai.pref.tochigi.lg.jp/work/custody-lostanimal/",
        category="lost",
        list_link_pattern="a[href*='/news/']",
    )


# ─────────────────── detail ページ想定 HTML ───────────────────
# 実サイトの WordPress 投稿は `<dl><dt>項目名</dt><dd>値</dd></dl>` 構造。
DETAIL_HTML = """
<html><body>
  <article id="post-12345">
    <h1 class="single_title">迷子犬収容情報</h1>
    <img src="https://www.douai.pref.tochigi.lg.jp/wp/wp-content/themes/serum_tcd096/img/header-logo.png">
    <img src="https://www.douai.pref.tochigi.lg.jp/wp/wp-content/uploads/2026/05/dog_main.jpg">
    <dl>
      <dt>種類</dt><dd>雑種</dd>
      <dt>性別</dt><dd>オス</dd>
      <dt>年齢</dt><dd>成犬</dd>
      <dt>毛色</dt><dd>茶白</dd>
      <dt>大きさ</dt><dd>中型</dd>
      <dt>収容日</dt><dd>2026年5月10日</dd>
      <dt>収容場所</dt><dd>栃木県動物愛護指導センター</dd>
      <dt>連絡先</dt><dd>028-684-5458</dd>
    </dl>
    <img src="https://www.douai.pref.tochigi.lg.jp/wp/wp-content/uploads/2026/05/dog_sub.jpg">
  </article>
</body></html>
"""


# ─────────────────── list 抽出 ───────────────────


class TestDouaiPrefTochigiListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_links_from_fixture(self, fixture_html):
        """fixture (custody カテゴリページ) から detail URL が抽出できる

        fixture には `#treatment_list .post_list .item a` 配下に
        サブセクションへの 3 つのリンクが含まれる。
        ヘッダ/フッタ/メニュー側のリンクは selector で除外される。
        """
        adapter = DouaiPrefTochigiAdapter(_custody_site())
        html = fixture_html("douai_pref_tochigi__custody")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        # post_list 配下の 3 リンクが抽出される
        assert (
            "https://www.douai.pref.tochigi.lg.jp/work/custody-lostanimal/"
            in urls
        )
        assert "https://www.douai.pref.tochigi.lg.jp/work/return/" in urls
        assert (
            "https://www.douai.pref.tochigi.lg.jp/work/avoid_getting_lost/"
            in urls
        )
        # category は site_config 由来
        assert all(cat == "sheltered" for _u, cat in result)

    def test_fetch_animal_list_filters_to_treatment_list_or_news(
        self, fixture_html
    ):
        """ヘッダ/フッタ/サイドのナビゲーションリンクは混入しない

        fixture の同階層リンクのうち `#treatment_list .post_list` 配下の
        ものだけが拾われ、`/access/` `/calendar/` 等のグローバルナビは
        URL リストに含まれない。
        """
        adapter = DouaiPrefTochigiAdapter(_custody_site())
        html = fixture_html("douai_pref_tochigi__custody")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        # グローバルナビ系の URL が混入していない
        assert "https://www.douai.pref.tochigi.lg.jp/access/" not in urls
        assert "https://www.douai.pref.tochigi.lg.jp/calendar/" not in urls
        assert "https://www.douai.pref.tochigi.lg.jp/jyouto/" not in urls
        assert "https://www.douai.pref.tochigi.lg.jp/" not in urls

    def test_fetch_animal_list_dedupes(self, fixture_html):
        """同じ detail URL は 1 回しか出てこない"""
        adapter = DouaiPrefTochigiAdapter(_custody_site())
        html = fixture_html("douai_pref_tochigi__custody")
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == len(set(urls)), "重複 URL がある"

    def test_news_post_links_are_picked_up(self):
        """`/news/<slug>/` 形式の WordPress 投稿リンクも一覧として拾える

        実サイトでは個別動物データは `/news/...` 投稿として公開される
        運用なので、selector がそれを取り逃さないことを確認する。
        """
        list_html = """
        <html><body>
          <main>
            <ul>
              <li>
                <a href="https://www.douai.pref.tochigi.lg.jp/news/maigo-dog-001/">
                  迷子犬情報
                </a>
              </li>
              <li>
                <a href="/news/jouto-cat-002/">譲渡猫情報</a>
              </li>
            </ul>
          </main>
        </body></html>
        """
        adapter = DouaiPrefTochigiAdapter(_adoption_site())
        with patch.object(adapter, "_http_get", return_value=list_html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert (
            "https://www.douai.pref.tochigi.lg.jp/news/maigo-dog-001/" in urls
        )
        # 相対 URL が絶対化される
        assert (
            "https://www.douai.pref.tochigi.lg.jp/news/jouto-cat-002/" in urls
        )
        assert all(cat == "adoption" for _u, cat in result)


# ─────────────────── detail 抽出 ───────────────────


class TestDouaiPrefTochigiDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data(self, assert_raw_animal):
        adapter = DouaiPrefTochigiAdapter(_lost_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.douai.pref.tochigi.lg.jp/news/maigo-001/",
                category="lost",
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="成犬",
            color="茶白",
            size="中型",
            shelter_date="2026年5月10日",
            location="栃木県動物愛護指導センター",
            phone="028-684-5458",
            source_url="https://www.douai.pref.tochigi.lg.jp/news/maigo-001/",
            category="lost",
        )

    def test_extract_filters_template_images_and_keeps_uploads(self):
        adapter = DouaiPrefTochigiAdapter(_lost_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.douai.pref.tochigi.lg.jp/news/maigo-001/"
            )
        # uploads 配下の 2 枚のみ残り、themes 配下のロゴは弾かれる
        assert len(raw.image_urls) == 2
        assert all("/wp-content/uploads/" in u for u in raw.image_urls)


# ─────────────────── normalize ───────────────────


class TestDouaiPrefTochigiNormalize:
    """RawAnimalData → AnimalData 変換"""

    def test_normalize_returns_animal_data(self):
        adapter = DouaiPrefTochigiAdapter(_lost_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details(
                "https://www.douai.pref.tochigi.lg.jp/news/maigo-001/",
                category="lost",
            )
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert hasattr(normalized, "species")


# ─────────────────── registry ───────────────────


class TestDouaiPrefTochigiRegistry:
    """3 サイトすべてが registry に登録されていること"""

    EXPECTED_SITE_NAMES = (
        "栃木県動物愛護指導センター（保護動物）",
        "栃木県動物愛護指導センター（譲渡動物）",
        "栃木県動物愛護指導センター（迷子動物）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_adapter(self, site_name):
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is DouaiPrefTochigiAdapter, (
            f"{site_name} が DouaiPrefTochigiAdapter に紐付いていません: {cls}"
        )
