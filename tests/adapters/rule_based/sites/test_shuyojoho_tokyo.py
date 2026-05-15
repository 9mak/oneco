"""ShuyojohoTokyoAdapter のテスト

東京都収容動物情報 (shuyojoho.metro.tokyo.lg.jp) 用 rule-based adapter
の動作を検証する。

このサイトは JS 必須 (`requires_js: true`) のため `PlaywrightFetchMixin`
を多重継承しているが、テストでは Playwright を実際に呼ばずに
`_http_get` を mock で差し替えて静的 HTML を返す。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.shuyojoho_tokyo import (
    ShuyojohoTokyoAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import (
    WordPressListAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 一覧ページを模した最小 HTML。`/animals/detail/{id}` への複数リンクと、
# 重複リンク・関係ない絞り込みリンクを含む。
LIST_HTML = """
<html><body>
<div id="topMain">
  <ul class="dateGroup">
    <li><a href="/animals/datein/2026-05-15">2026年5月15日</a></li>
  </ul>
  <ul>
    <li><a href="/animals/detail/8700">個体1</a></li>
    <li><a href="/animals/detail/8701">個体2</a></li>
    <li><a href="/animals/detail/8700">重複1</a></li>
  </ul>
  <a href="/animals/address/%E5%85%AB%E7%8E%8B%E5%AD%90%E5%B8%82">八王子市</a>
  <a href="/howtouse">サイトの使い方</a>
</div>
</body></html>
"""

# 在庫 0 件 (「現在、収容動物情報はありません。」) 状態の最小 HTML
EMPTY_HTML = """
<html><body>
<div id="topMain"><h3>現在、収容動物情報はありません。</h3></div>
</body></html>
"""

# detail ページを模した最小 HTML (実サイトの dl#dataGroup0X 構造を再現)。
# species ラベル (種類) は雑種、動物名は ネコ。
DETAIL_HTML_CAT = """
<html><body>
<div id="main">
  <div id="parsonalData">
    <div id="dataBox01">
      <p id="mainPhoto">
        <img width="360" src="/img/upload/6a06ab2ce6bdb.gif" alt="管理番号 26F7" />
      </p>
      <div class="data-col-r">
        <dl id="dataGroup01">
          <dt>収容日</dt><dd>2026/05/15</dd>
          <dt>収容期限</dt><dd>2026/05/25</dd>
          <dt>収容場所</dt><dd>練馬区 氷川台2丁目</dd>
          <dt>管理支所</dt><dd>城南島出張所</dd>
          <dt>動物名</dt><dd>ネコ</dd>
        </dl>
      </div>
    </div>
    <div id="dataBox02">
      <dl id="dataGroup02">
        <dt>種類</dt><dd>雑種</dd>
        <dt>性別</dt><dd>オス(去勢含む)</dd>
      </dl>
      <dl id="dataGroup03">
        <dt>大きさ</dt><dd>中</dd>
        <dt>毛色</dt><dd>黒/白</dd>
      </dl>
      <dl id="dataGroup04">
        <dt>毛の長さ</dt><dd>短</dd>
        <dt>首輪</dt><dd>無</dd>
      </dl>
    </div>
  </div>
  <div id="info">
    <div class="contact_box">
      <h3>城南島出張所</h3>
      <p class="tel">TEL. 03-3790-0861</p>
    </div>
  </div>
</div>
<!-- メイン以外の banner img は image_urls に拾わない -->
<img src="/img/bnr_tokyo.jpg" alt="bnr" />
</body></html>
"""

# detail ページ - 犬版。動物名 = イヌ。
DETAIL_HTML_DOG = """
<html><body>
<div id="main">
  <p id="mainPhoto">
    <img width="360" src="/img/upload/dog_001.jpg" alt="管理番号 26D1" />
  </p>
  <dl id="dataGroup01">
    <dt>収容日</dt><dd>2026/05/14</dd>
    <dt>収容場所</dt><dd>大田区 城南島</dd>
    <dt>動物名</dt><dd>イヌ</dd>
  </dl>
  <dl id="dataGroup02">
    <dt>種類</dt><dd>柴犬</dd>
    <dt>性別</dt><dd>メス</dd>
  </dl>
  <dl id="dataGroup03">
    <dt>大きさ</dt><dd>小</dd>
    <dt>毛色</dt><dd>茶</dd>
  </dl>
  <div class="contact_box">
    <p class="tel">TEL. 03-3302-3507</p>
  </div>
</div>
</body></html>
"""

# species ラベル「種類」自体を欠いた detail HTML。
# 動物名フォールバック (ネコ) の検証用。
DETAIL_HTML_NO_SPECIES_LABEL_CAT = """
<html><body>
<div id="main">
  <dl id="dataGroup01">
    <dt>収容日</dt><dd>2026/05/15</dd>
    <dt>収容場所</dt><dd>八王子市</dd>
    <dt>動物名</dt><dd>ネコ</dd>
  </dl>
  <dl id="dataGroup02">
    <dt>性別</dt><dd>メス</dd>
  </dl>
  <dl id="dataGroup03">
    <dt>毛色</dt><dd>白</dd>
  </dl>
</div>
</body></html>
"""

# 動物名すらも欠落しているケース (URL fallback の検証用)
DETAIL_HTML_NO_SPECIES_NO_ANIMAL_NAME = """
<html><body>
<div id="main">
  <dl id="dataGroup01">
    <dt>収容日</dt><dd>2026/05/14</dd>
    <dt>収容場所</dt><dd>板橋区</dd>
  </dl>
  <dl id="dataGroup02">
    <dt>性別</dt><dd>オス</dd>
  </dl>
</div>
</body></html>
"""


def _site(
    name: str,
    list_url: str,
    category: str = "sheltered",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="東京都",
        prefecture_code="13",
        list_url=list_url,
        category=category,
        requires_js=True,
        wait_selector="body",
    )


def _site_dog() -> SiteConfig:
    return _site(
        "東京都収容動物情報（犬）",
        "https://shuyojoho.metro.tokyo.lg.jp/",
        category="sheltered",
    )


def _site_cat() -> SiteConfig:
    return _site(
        "東京都収容動物情報（猫等）",
        "https://shuyojoho.metro.tokyo.lg.jp/cat",
        category="sheltered",
    )


class TestShuyojohoTokyoAdapterInheritance:
    """多重継承構造の検証"""

    def test_inherits_playwright_mixin(self):
        assert issubclass(ShuyojohoTokyoAdapter, PlaywrightFetchMixin)

    def test_inherits_wordpress_list_adapter(self):
        assert issubclass(ShuyojohoTokyoAdapter, WordPressListAdapter)

    def test_wait_selector_defined(self):
        """JS 描画完了待ちの WAIT_SELECTOR が定義されている"""
        assert ShuyojohoTokyoAdapter.WAIT_SELECTOR is not None
        assert ShuyojohoTokyoAdapter.WAIT_SELECTOR != ""

    def test_http_get_uses_playwright_fetcher(self):
        """`_http_get` が PlaywrightFetcher 経由で動くこと

        実 Playwright は呼ばずに class を mock。
        """
        adapter = ShuyojohoTokyoAdapter(_site_dog())

        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = "<html>JS-rendered</html>"

        with patch(
            "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
            return_value=mock_fetcher,
        ) as mock_cls:
            result = adapter._http_get("https://example.com/page")

        assert result == "<html>JS-rendered</html>"
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("wait_selector") == ShuyojohoTokyoAdapter.WAIT_SELECTOR


class TestShuyojohoTokyoAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls_dog(self):
        """`/animals/detail/{id}` の URL が抽出できる + 重複除外 + 絶対 URL 化"""
        adapter = ShuyojohoTokyoAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == 2
        assert any(u.endswith("/animals/detail/8700") for u in urls)
        assert any(u.endswith("/animals/detail/8701") for u in urls)
        # 全 URL が絶対 URL
        assert all(u.startswith("https://shuyojoho.metro.tokyo.lg.jp/") for u in urls)
        # category は site_config 由来
        assert all(cat == "sheltered" for _u, cat in result)
        # 関係ない絞り込み / ヘルプリンクは混入しない
        assert all("/animals/datein/" not in u for u in urls)
        assert all("/animals/address/" not in u for u in urls)
        assert all("/howtouse" not in u for u in urls)

    def test_fetch_animal_list_extracts_detail_urls_cat(self):
        """猫サイト (/cat) でも同じ `/animals/detail/{id}` パターンが拾える"""
        adapter = ShuyojohoTokyoAdapter(_site_cat())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert len(urls) == 2
        assert all("/animals/detail/" in u for u in urls)

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """「現在、収容動物情報はありません。」状態では空リストを返す"""
        adapter = ShuyojohoTokyoAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value=EMPTY_HTML):
            result = adapter.fetch_animal_list()
        assert result == []


class TestShuyojohoTokyoAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_cat(self, assert_raw_animal):
        """猫の詳細ページから各フィールドが抽出できる"""
        adapter = ShuyojohoTokyoAdapter(_site_cat())
        detail_url = "https://shuyojoho.metro.tokyo.lg.jp/animals/detail/8700"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス(去勢含む)",
            color="黒/白",
            size="中",
            shelter_date="2026/05/15",
            location="練馬区 氷川台2丁目",
            category="sheltered",
        )
        # 電話番号は "TEL. " ラベルが除去され "03-3790-0861" に正規化される
        assert raw.phone == "03-3790-0861"
        # メイン画像のみ抽出 (banner img は除外される)
        assert len(raw.image_urls) == 1
        assert "/img/upload/6a06ab2ce6bdb.gif" in raw.image_urls[0]
        assert "bnr_tokyo.jpg" not in raw.image_urls[0]
        assert raw.source_url == detail_url

    def test_extract_animal_details_dog(self, assert_raw_animal):
        """犬の詳細ページから各フィールドが抽出できる"""
        adapter = ShuyojohoTokyoAdapter(_site_dog())
        detail_url = "https://shuyojoho.metro.tokyo.lg.jp/animals/detail/8701"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")

        assert_raw_animal(
            raw,
            species="柴犬",
            sex="メス",
            color="茶",
            size="小",
            shelter_date="2026/05/14",
            location="大田区 城南島",
        )
        assert raw.phone == "03-3302-3507"
        assert any("dog_001.jpg" in u for u in raw.image_urls)

    def test_extract_animal_details_infers_species_from_animal_name_cat(self):
        """species ラベルが空でも 動物名「ネコ」から "猫" が推定される"""
        adapter = ShuyojohoTokyoAdapter(_site_cat())
        detail_url = "https://shuyojoho.metro.tokyo.lg.jp/animals/detail/9001"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_NO_SPECIES_LABEL_CAT):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")
        assert raw.species == "猫"

    def test_extract_animal_details_infers_species_from_list_url_cat(self):
        """「種類」「動物名」両方とも欠落でも /cat list URL から "猫" 推定"""
        adapter = ShuyojohoTokyoAdapter(_site_cat())
        detail_url = "https://shuyojoho.metro.tokyo.lg.jp/animals/detail/9002"
        with patch.object(
            adapter,
            "_http_get",
            return_value=DETAIL_HTML_NO_SPECIES_NO_ANIMAL_NAME,
        ):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")
        assert raw.species == "猫"

    def test_extract_animal_details_infers_species_from_site_name_dog(self):
        """猫 fallback が当たらない犬サイトでは site name から "犬" 推定"""
        adapter = ShuyojohoTokyoAdapter(_site_dog())
        detail_url = "https://shuyojoho.metro.tokyo.lg.jp/animals/detail/9003"
        with patch.object(
            adapter,
            "_http_get",
            return_value=DETAIL_HTML_NO_SPECIES_NO_ANIMAL_NAME,
        ):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")
        assert raw.species == "犬"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では ParsingError"""
        adapter = ShuyojohoTokyoAdapter(_site_dog())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    "https://shuyojoho.metro.tokyo.lg.jp/animals/detail/x"
                )


class TestShuyojohoTokyoAdapterSpeciesInference:
    """ヘルパー: 動物名 / list URL / サイト名からの動物種別推定"""

    @pytest.mark.parametrize(
        "html,expected",
        [
            (
                "<html><body><dl><dt>動物名</dt><dd>イヌ</dd></dl></body></html>",
                "犬",
            ),
            (
                "<html><body><dl><dt>動物名</dt><dd>ネコ</dd></dl></body></html>",
                "猫",
            ),
            (
                "<html><body><dl><dt>動物名</dt><dd>犬</dd></dl></body></html>",
                "犬",
            ),
            (
                "<html><body><dl><dt>動物名</dt><dd>猫</dd></dl></body></html>",
                "猫",
            ),
            (
                "<html><body><dl><dt>動物名</dt><dd>ウサギ</dd></dl></body></html>",
                "",
            ),
            ("<html><body></body></html>", ""),
        ],
    )
    def test_infer_species_from_animal_name(self, html, expected):
        soup = BeautifulSoup(html, "html.parser")
        assert ShuyojohoTokyoAdapter._infer_species_from_animal_name(soup) == expected

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://shuyojoho.metro.tokyo.lg.jp/cat", "猫"),
            ("https://shuyojoho.metro.tokyo.lg.jp/cat/", "猫"),
            ("https://shuyojoho.metro.tokyo.lg.jp/cat/foo", "猫"),
            ("https://shuyojoho.metro.tokyo.lg.jp/", ""),
            ("https://shuyojoho.metro.tokyo.lg.jp/animals/detail/100", ""),
            ("", ""),
        ],
    )
    def test_infer_species_from_list_url(self, url, expected):
        assert ShuyojohoTokyoAdapter._infer_species_from_list_url(url) == expected

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("東京都収容動物情報（犬）", "犬"),
            ("東京都収容動物情報（猫等）", "猫"),
            ("東京都収容動物情報（犬・猫）", "猫"),  # 併記時は猫優先
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert ShuyojohoTokyoAdapter._infer_species_from_site_name(name) == expected


class TestShuyojohoTokyoAdapterRegistry:
    """2 サイトすべてが SiteAdapterRegistry に登録されていること"""

    EXPECTED_SITE_NAMES = (
        "東京都収容動物情報（犬）",
        "東京都収容動物情報（猫等）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered(self, site_name):
        # registry が他テストで clear された場合の冪等性
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, ShuyojohoTokyoAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is ShuyojohoTokyoAdapter, (
            f"{site_name} が ShuyojohoTokyoAdapter に紐付いていません: {cls}"
        )

    def test_all_two_sites_registered(self):
        for name in self.EXPECTED_SITE_NAMES:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, ShuyojohoTokyoAdapter)
        registered = [
            n
            for n in self.EXPECTED_SITE_NAMES
            if SiteAdapterRegistry.get(n) is ShuyojohoTokyoAdapter
        ]
        assert len(registered) == 2
