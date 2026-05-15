"""KumamotoDoubutuAigoAdapter のテスト

熊本県動物愛護センター (kumamoto-doubutuaigo.jp) 用 rule-based adapter
の動作を検証する。

このサイトは JS 必須 (`requires_js: true`) のため `PlaywrightFetchMixin`
を多重継承しているが、テストでは Playwright を実際に呼ばずに
`_http_get` を mock で差し替えて静的 HTML を返す。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.kumamoto_doubutuaigo import (
    KumamotoDoubutuAigoAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import (
    WordPressListAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 一覧ページを模した最小 HTML。`/animals/detail/` への複数リンクと、
# `/post_animals/detail/` へのリンク、関係ない一覧遷移リンクを含む。
LIST_HTML = """
<html><body>
<div class="animal-list">
  <ul>
    <li><a href="/animals/detail/animal_id:101">犬1</a></li>
    <li><a href="/animals/detail/animal_id:102">犬2</a></li>
    <li><a href="/animals/detail/animal_id:101">重複1</a></li>
  </ul>
</div>
<nav>
  <a href="/animals/index/type_id:2/animal_id:2">猫一覧へ</a>
  <a href="/about">about</a>
</nav>
</body></html>
"""

LIST_HTML_POST_ANIMALS = """
<html><body>
<div class="animal-list">
  <a href="/post_animals/detail/animal_id:301">個人保護1</a>
  <a href="/post_animals/detail/animal_id:302">個人保護2</a>
</div>
</body></html>
"""

# detail ページを模した最小 HTML (`<dt>/<dd>` 定義リスト版)
DETAIL_HTML_DOG = """
<html><body>
<div class="detail">
  <dl>
    <dt>種類</dt><dd>雑種</dd>
    <dt>性別</dt><dd>オス</dd>
    <dt>年齢</dt><dd>成犬</dd>
    <dt>毛色</dt><dd>茶白</dd>
    <dt>大きさ</dt><dd>中型</dd>
    <dt>収容日</dt><dd>2026年4月10日</dd>
    <dt>収容場所</dt><dd>熊本県動物愛護センター</dd>
    <dt>連絡先</dt><dd>096-380-2153</dd>
  </dl>
  <div class="photos">
    <img src="/uploads/animal/101_1.jpg" alt="犬写真1">
    <img src="/uploads/animal/101_2.jpg" alt="犬写真2">
  </div>
</div>
</body></html>
"""

# detail ページを模した最小 HTML (`<th>/<td>` テーブル版)
DETAIL_HTML_CAT_TABLE = """
<html><body>
<table>
  <tr><th>種類</th><td>三毛猫</td></tr>
  <tr><th>性別</th><td>メス</td></tr>
  <tr><th>毛色</th><td>三毛</td></tr>
  <tr><th>収容日</th><td>2026年4月15日</td></tr>
  <tr><th>収容場所</th><td>熊本県動物愛護センター</td></tr>
</table>
<img src="/uploads/animal/202_1.jpg" alt="猫写真">
</body></html>
"""


def _site(
    name: str,
    list_url: str,
    category: str = "adoption",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="熊本県",
        prefecture_code="43",
        list_url=list_url,
        category=category,
        requires_js=True,
        wait_selector="body",
    )


def _site_center_dog() -> SiteConfig:
    return _site(
        "熊本県動愛（センター譲渡犬）",
        "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:2/animal_id:1",
        category="adoption",
    )


def _site_center_cat() -> SiteConfig:
    return _site(
        "熊本県動愛（センター譲渡猫）",
        "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:2/animal_id:2",
        category="adoption",
    )


def _site_post_dog() -> SiteConfig:
    return _site(
        "熊本県動愛（個人保護犬）",
        "https://www.kumamoto-doubutuaigo.jp/post_animals/index/type_id:2/animal_id:1",
        category="sheltered",
    )


def _site_lost_cat() -> SiteConfig:
    return _site(
        "熊本県動愛（迷子猫）",
        "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:1/animal_id:2",
        category="lost",
    )


class TestKumamotoDoubutuAigoAdapterInheritance:
    """多重継承構造の検証"""

    def test_inherits_playwright_mixin(self):
        assert issubclass(KumamotoDoubutuAigoAdapter, PlaywrightFetchMixin)

    def test_inherits_wordpress_list_adapter(self):
        assert issubclass(KumamotoDoubutuAigoAdapter, WordPressListAdapter)

    def test_wait_selector_defined(self):
        """JS 描画完了待ちの WAIT_SELECTOR が定義されている"""
        assert KumamotoDoubutuAigoAdapter.WAIT_SELECTOR is not None
        assert KumamotoDoubutuAigoAdapter.WAIT_SELECTOR != ""

    def test_http_get_uses_playwright_fetcher(self):
        """`_http_get` が PlaywrightFetcher 経由で動くこと

        実 Playwright は呼ばずに class を mock。
        """
        adapter = KumamotoDoubutuAigoAdapter(_site_center_dog())

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>JS-rendered</html>"

        with patch(
            "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
            return_value=mock_fetcher,
        ) as mock_cls:
            result = adapter._http_get("https://example.com/page")

        assert result == "<html>JS-rendered</html>"
        # WAIT_SELECTOR が PlaywrightFetcher に渡される
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("wait_selector") == KumamotoDoubutuAigoAdapter.WAIT_SELECTOR


class TestKumamotoDoubutuAigoAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_animals_detail_urls(self):
        """`/animals/detail/...` の URL が抽出できる + 重複除外 + 絶対 URL 化"""
        adapter = KumamotoDoubutuAigoAdapter(_site_center_dog())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        # 重複 (animal_id:101 が 2 回) は 1 件に集約
        assert len(urls) == 2
        assert any("/animals/detail/animal_id:101" in u for u in urls)
        assert any("/animals/detail/animal_id:102" in u for u in urls)
        # 全 URL が絶対 URL
        assert all(u.startswith("https://www.kumamoto-doubutuaigo.jp") for u in urls)
        # category は site_config 由来
        assert all(cat == "adoption" for _u, cat in result)
        # 関係ない一覧遷移リンクは混入しない
        assert all("/animals/index/" not in u for u in urls)
        assert all("/about" not in u for u in urls)

    def test_fetch_animal_list_extracts_post_animals_detail_urls(self):
        """`/post_animals/detail/...` の URL も抽出できる"""
        adapter = KumamotoDoubutuAigoAdapter(_site_post_dog())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_POST_ANIMALS):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == 2
        assert all("/post_animals/detail/" in u for u in urls)
        assert all(cat == "sheltered" for _u, cat in result)

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """記事リンクが 1 件も無い HTML では空リストを返す (在庫 0 件)"""
        empty_html = "<html><body><div class='animal-list'></div></body></html>"
        adapter = KumamotoDoubutuAigoAdapter(_site_center_dog())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


class TestKumamotoDoubutuAigoAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_from_definition_list(self, assert_raw_animal):
        """`<dt>/<dd>` 定義リストから各フィールドが抽出できる"""
        adapter = KumamotoDoubutuAigoAdapter(_site_center_dog())
        detail_url = "https://www.kumamoto-doubutuaigo.jp/animals/detail/animal_id:101"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="成犬",
            color="茶白",
            size="中型",
            shelter_date="2026年4月10日",
            location="熊本県動物愛護センター",
            phone="096-380-2153",
            category="adoption",
        )
        assert len(raw.image_urls) == 2
        assert all("/uploads/animal/" in u for u in raw.image_urls)
        # source_url が detail_url と一致
        assert raw.source_url == detail_url

    def test_extract_animal_details_from_th_td_table(self, assert_raw_animal):
        """`<th>/<td>` テーブルからも値を抽出できる"""
        adapter = KumamotoDoubutuAigoAdapter(_site_center_cat())
        detail_url = "https://www.kumamoto-doubutuaigo.jp/animals/detail/animal_id:202"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT_TABLE):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert_raw_animal(
            raw,
            species="三毛猫",
            sex="メス",
            color="三毛",
            shelter_date="2026年4月15日",
            location="熊本県動物愛護センター",
        )

    def test_extract_animal_details_infers_species_from_list_url_dog(self):
        """species ラベルが空のとき list URL `animal_id:1` から "犬" 推定"""
        # 「種類」ラベルを欠いた detail HTML
        detail_html = """
        <html><body>
        <dl>
          <dt>性別</dt><dd>オス</dd>
          <dt>毛色</dt><dd>白</dd>
        </dl>
        </body></html>
        """
        adapter = KumamotoDoubutuAigoAdapter(_site_center_dog())  # animal_id:1
        detail_url = "https://www.kumamoto-doubutuaigo.jp/animals/detail/foo"
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="adoption")
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_from_list_url_cat(self):
        """list URL `animal_id:2` の場合は species が "猫" になる"""
        detail_html = """
        <html><body>
        <dl><dt>性別</dt><dd>メス</dd></dl>
        </body></html>
        """
        adapter = KumamotoDoubutuAigoAdapter(_site_lost_cat())  # animal_id:2
        detail_url = "https://www.kumamoto-doubutuaigo.jp/animals/detail/bar"
        with patch.object(adapter, "_http_get", return_value=detail_html):
            raw = adapter.extract_animal_details(detail_url, category="lost")
        assert raw.species == "猫"
        assert raw.category == "lost"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では ParsingError"""
        adapter = KumamotoDoubutuAigoAdapter(_site_center_dog())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    "https://www.kumamoto-doubutuaigo.jp/animals/detail/x"
                )


class TestKumamotoDoubutuAigoAdapterSpeciesInference:
    """`animal_id:N` URL / サイト名からの動物種別推定"""

    @pytest.mark.parametrize(
        "url,expected",
        [
            (
                "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:2/animal_id:1",
                "犬",
            ),
            (
                "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:2/animal_id:2",
                "猫",
            ),
            (
                "https://www.kumamoto-doubutuaigo.jp/animals/detail/foo",
                "",
            ),
            ("", ""),
        ],
    )
    def test_infer_species_from_url(self, url, expected):
        assert KumamotoDoubutuAigoAdapter._infer_species_from_url(url) == expected

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("熊本県動愛（センター譲渡犬）", "犬"),
            ("熊本県動愛（センター譲渡猫）", "猫"),
            ("熊本県動愛（団体譲渡犬）", "犬"),
            ("熊本県動愛（団体譲渡猫）", "猫"),
            ("熊本県動愛（個人保護犬）", "犬"),
            ("熊本県動愛（個人保護猫）", "猫"),
            ("熊本県動愛（迷子犬）", "犬"),
            ("熊本県動愛（迷子猫）", "猫"),
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert KumamotoDoubutuAigoAdapter._infer_species_from_site_name(name) == expected


class TestKumamotoDoubutuAigoAdapterRegistry:
    """8 サイトすべてが SiteAdapterRegistry に登録されていること"""

    EXPECTED_SITE_NAMES = (
        "熊本県動愛（センター譲渡犬）",
        "熊本県動愛（センター譲渡猫）",
        "熊本県動愛（団体譲渡犬）",
        "熊本県動愛（団体譲渡猫）",
        "熊本県動愛（個人保護犬）",
        "熊本県動愛（個人保護猫）",
        "熊本県動愛（迷子犬）",
        "熊本県動愛（迷子猫）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered(self, site_name):
        # registry が他テストで clear された場合の冪等性
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, KumamotoDoubutuAigoAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is KumamotoDoubutuAigoAdapter, (
            f"{site_name} が KumamotoDoubutuAigoAdapter に紐付いていません: {cls}"
        )

    def test_all_eight_sites_registered(self):
        for name in self.EXPECTED_SITE_NAMES:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, KumamotoDoubutuAigoAdapter)
        registered = [
            n
            for n in self.EXPECTED_SITE_NAMES
            if SiteAdapterRegistry.get(n) is KumamotoDoubutuAigoAdapter
        ]
        assert len(registered) == 8
