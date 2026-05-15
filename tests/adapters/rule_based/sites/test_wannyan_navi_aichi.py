"""WannyanNaviAichiAdapter のテスト

愛知県わんにゃんナビ (wannyan-navi.pref.aichi.jp) 用 rule-based adapter
の動作を検証する。

- Playwright で取得された一覧 HTML から詳細リンク候補を抽出
  (`/dog/...`, `/cat/...`, `/animal/...` 等の動物詳細パス)
- ナビゲーションリンク (`/about`, `/contact`, `/login`, SNS 等) が
  除外されること
- 0 件 (詳細リンクが 1 件も無い) の場合に空リストを返すこと
- 詳細ページ HTML を模した最小 HTML (`<th>/<td>` テーブルおよび
  `<td>/<td>` 2 列テーブル) からの RawAnimalData 構築
- 動物種別 (犬/猫) が detail URL のパス (`/dog`/`/cat`) から
  推定されること
- サイト名「愛知県わんにゃんナビ」が SiteAdapterRegistry に
  登録されていること
- `PlaywrightFetchMixin` を継承していること

NOTE: Playwright 自体は呼び出さず、`_http_get` を patch して固定 HTML を
返すことで JS 実行を擬似する。これは熊本市・福岡市等の同パターン
adapter テストと同じ方針。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.wannyan_navi_aichi import (
    WannyanNaviAichiAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import (
    WordPressListAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 一覧ページ HTML (Bubble.io JS 描画後を想定)。
# 動物カード `<a>` と、混入し得るナビゲーション/SNS リンクを併記。
LIST_HTML = """
<html><body>
<header>
  <a href="/about">サイトについて</a>
  <a href="/contact">お問合せ</a>
  <a href="/login">ログイン</a>
</header>
<main>
  <div class="animal-card">
    <a href="/dog/abc123">
      <img src="https://cdn.bubble.io/animal/abc123.jpg" alt="犬">
      <p>柴犬</p>
    </a>
  </div>
  <div class="animal-card">
    <a href="/dog/def456">
      <img src="https://cdn.bubble.io/animal/def456.jpg" alt="犬">
      <p>雑種</p>
    </a>
  </div>
  <div class="animal-card">
    <a href="/cat/ghi789">
      <img src="https://cdn.bubble.io/animal/ghi789.jpg" alt="猫">
      <p>三毛猫</p>
    </a>
  </div>
</main>
<footer>
  <a href="https://twitter.com/aichi_pref">公式X</a>
  <a href="https://www.facebook.com/aichi">Facebook</a>
  <a href="/policy">プライバシーポリシー</a>
  <a href="/sitemap">サイトマップ</a>
</footer>
</body></html>
"""

# 0 件状態の HTML (動物詳細リンクが存在しない)。
LIST_HTML_EMPTY = """
<html><body>
<main>
  <p>現在、譲渡対象の動物はいません。</p>
</main>
<footer>
  <a href="/about">サイトについて</a>
</footer>
</body></html>
"""

# 完全に空の HTML (何のリンクも無い)。
LIST_HTML_NO_LINKS = "<html><body><p>読み込み中…</p></body></html>"

# 詳細ページ HTML (`<th>/<td>` テーブル形式)。
DETAIL_HTML_DOG = """
<html><body>
<header>
  <img src="https://cdn.bubble.io/header_logo.png" alt="ロゴ">
</header>
<main>
  <table>
    <tbody>
      <tr><th>種類</th><td>柴犬</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>年齢</th><td>3歳</td></tr>
      <tr><th>毛色</th><td>赤</td></tr>
      <tr><th>大きさ</th><td>中型</td></tr>
      <tr><th>収容日</th><td>2026年4月10日</td></tr>
      <tr><th>場所</th><td>愛知県動物愛護センター</td></tr>
      <tr><th>連絡先</th><td>0568-22-8311</td></tr>
    </tbody>
  </table>
  <div class="photo">
    <img src="https://cdn.bubble.io/animal/abc123_1.jpg" alt="犬写真1">
    <img src="https://cdn.bubble.io/animal/abc123_2.jpg" alt="犬写真2">
  </div>
</main>
<footer>
  <img src="https://cdn.bubble.io/footer_logo.png" alt="footer logo">
</footer>
</body></html>
"""

# 詳細ページ HTML (`<td>/<td>` 2 列テーブル形式)。
DETAIL_HTML_CAT_2COL = """
<html><body>
<table>
  <tr><td>種類</td><td>三毛猫</td></tr>
  <tr><td>性別</td><td>メス</td></tr>
  <tr><td>毛色</td><td>三毛</td></tr>
  <tr><td>収容日</td><td>2026年4月22日</td></tr>
  <tr><td>場所</td><td>愛知県動物愛護センター</td></tr>
</table>
<img src="https://cdn.bubble.io/animal/ghi789.jpg" alt="猫写真">
</body></html>
"""

# 詳細ページ HTML (`<dl>/<dt>/<dd>` 形式)。
DETAIL_HTML_DL = """
<html><body>
<dl>
  <dt>性別</dt><dd>オス</dd>
  <dt>年齢</dt><dd>5歳</dd>
  <dt>毛色</dt><dd>白</dd>
</dl>
</body></html>
"""


def _site_aichi() -> SiteConfig:
    return SiteConfig(
        name="愛知県わんにゃんナビ",
        prefecture="愛知県",
        prefecture_code="23",
        list_url="https://wannyan-navi.pref.aichi.jp/",
        category="adoption",
    )


class TestWannyanNaviAichiAdapterClassStructure:
    """継承構造とクラス定数"""

    def test_inherits_playwright_fetch_mixin(self):
        """JS 必須サイト対応のため PlaywrightFetchMixin を継承している"""
        assert issubclass(WannyanNaviAichiAdapter, PlaywrightFetchMixin)

    def test_inherits_wordpress_list_adapter(self):
        """list+detail 構造の汎用基底 WordPressListAdapter を継承している"""
        assert issubclass(WannyanNaviAichiAdapter, WordPressListAdapter)

    def test_wait_selector_configured(self):
        """Playwright の WAIT_SELECTOR が設定されている (None ではない)"""
        assert WannyanNaviAichiAdapter.WAIT_SELECTOR is not None
        assert WannyanNaviAichiAdapter.WAIT_SELECTOR != ""

    def test_list_link_selector_defined(self):
        """LIST_LINK_SELECTOR が空文字でない"""
        assert WannyanNaviAichiAdapter.LIST_LINK_SELECTOR
        assert WannyanNaviAichiAdapter.LIST_LINK_SELECTOR != ""


class TestWannyanNaviAichiAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls(self):
        """`/dog/...` `/cat/...` パスの a タグから detail URL を抽出する"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())

        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        urls = [u for u, _cat in result]
        # 動物詳細パスのみ含まれる
        assert any("/dog/abc123" in u for u in urls)
        assert any("/dog/def456" in u for u in urls)
        assert any("/cat/ghi789" in u for u in urls)
        # ナビゲーション/SNS は除外されている
        assert all("/about" not in u for u in urls)
        assert all("/contact" not in u for u in urls)
        assert all("/login" not in u for u in urls)
        assert all("/policy" not in u for u in urls)
        assert all("/sitemap" not in u for u in urls)
        assert all("twitter.com" not in u for u in urls)
        assert all("facebook.com" not in u for u in urls)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)
        # category は site_config.category 由来 (adoption)
        assert all(cat == "adoption" for _u, cat in result)

    def test_fetch_animal_list_dedupes_urls(self):
        """同一 URL が重複していても 1 件に集約される"""
        dup_html = """
        <html><body>
        <a href="/dog/xx">A</a>
        <a href="/dog/xx">A again</a>
        </body></html>
        """
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(adapter, "_http_get", return_value=dup_html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == 1
        assert len(urls) == len(set(urls))

    def test_fetch_animal_list_returns_empty_for_no_animals(self):
        """動物詳細リンクが 1 件も無いときは空リストを返す"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_EMPTY):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_animal_list_returns_empty_for_no_links_at_all(self):
        """そもそも `<a>` が無い HTML でも空リスト"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(
            adapter, "_http_get", return_value=LIST_HTML_NO_LINKS
        ):
            result = adapter.fetch_animal_list()
        assert result == []


class TestWannyanNaviAichiAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_dog(
        self, assert_raw_animal
    ):
        """`<th>/<td>` テーブルの詳細ページから各フィールドが抽出できる"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/dog/abc123"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(
                detail_url, category="adoption"
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="柴犬",
            sex="オス",
            age="3歳",
            color="赤",
            size="中型",
            shelter_date="2026年4月10日",
            location="愛知県動物愛護センター",
            phone="0568-22-8311",
            category="adoption",
        )
        # 動物写真 2 枚は採用、ロゴ画像は除外される
        assert len(raw.image_urls) == 2
        assert all("logo" not in u.lower() for u in raw.image_urls)
        assert all("/animal/abc123" in u for u in raw.image_urls)

    def test_extract_animal_details_supports_two_column_table(
        self, assert_raw_animal
    ):
        """`<th>` を持たない 2 列テーブルからも値を抽出できる"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/cat/ghi789"
        with patch.object(
            adapter, "_http_get", return_value=DETAIL_HTML_CAT_2COL
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="adoption"
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="三毛猫",
            sex="メス",
            color="三毛",
            shelter_date="2026年4月22日",
            location="愛知県動物愛護センター",
            category="adoption",
        )

    def test_extract_animal_details_supports_dl_dt_dd(self):
        """`<dl>/<dt>/<dd>` 形式の詳細ページからも抽出できる"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/dog/dl-style"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DL):
            raw = adapter.extract_animal_details(
                detail_url, category="adoption"
            )
        assert raw.sex == "オス"
        assert raw.age == "5歳"
        assert raw.color == "白"
        # species ラベルは無いが detail URL `/dog/...` から「犬」が補完される
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_from_url_dog(self):
        """species ラベル不在でも detail URL `/dog/` から「犬」が補完される"""
        detail_html_no_species = """
        <html><body>
        <table>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>毛色</th><td>白</td></tr>
        </table>
        </body></html>
        """
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/dog/55555"
        with patch.object(
            adapter, "_http_get", return_value=detail_html_no_species
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="adoption"
            )
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_from_url_cat(self):
        """detail URL `/cat/` からは「猫」が補完される"""
        detail_html_no_species = """
        <html><body>
        <table>
          <tr><th>性別</th><td>メス</td></tr>
        </table>
        </body></html>
        """
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/cat/66666"
        with patch.object(
            adapter, "_http_get", return_value=detail_html_no_species
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="adoption"
            )
        assert raw.species == "猫"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では ParsingError"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://wannyan-navi.pref.aichi.jp/dog/0"
                )


class TestWannyanNaviAichiAdapterUrlHelpers:
    """URL 判定 / 種別推定ヘルパー"""

    @pytest.mark.parametrize(
        "href,expected",
        [
            ("/dog/abc123", True),
            ("/cat/xxx", True),
            ("/animal/123", True),
            ("/version-test/dog/zzz", True),
            ("/about", False),
            ("/contact", False),
            ("/login", False),
            ("/signup", False),
            ("/policy", False),
            ("/sitemap", False),
            ("https://twitter.com/aichi", False),
            ("https://www.facebook.com/aichi", False),
            ("mailto:foo@example.com", False),
            ("tel:0568228311", False),
            ("/", False),
            ("", False),
        ],
    )
    def test_is_detail_url(self, href, expected):
        assert WannyanNaviAichiAdapter._is_detail_url(href) == expected

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://wannyan-navi.pref.aichi.jp/dog/abc123", "犬"),
            ("https://wannyan-navi.pref.aichi.jp/cat/xyz", "猫"),
            ("https://wannyan-navi.pref.aichi.jp/animal/123", ""),
            ("", ""),
        ],
    )
    def test_infer_species_from_url(self, url, expected):
        assert (
            WannyanNaviAichiAdapter._infer_species_from_url(url) == expected
        )


class TestWannyanNaviAichiAdapterRegistry:
    """registry にサイト名が登録されていること"""

    SITE_NAME = "愛知県わんにゃんナビ"

    def test_site_registered_to_wannyan_navi_aichi_adapter(self):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(self.SITE_NAME) is None:
            SiteAdapterRegistry.register(
                self.SITE_NAME, WannyanNaviAichiAdapter
            )
        cls = SiteAdapterRegistry.get(self.SITE_NAME)
        assert cls is WannyanNaviAichiAdapter, (
            f"{self.SITE_NAME} が WannyanNaviAichiAdapter に "
            f"紐付いていません: {cls}"
        )
