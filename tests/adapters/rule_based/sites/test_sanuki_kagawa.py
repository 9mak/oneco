"""SanukiKagawaAdapter (pref.kagawa.lg.jp) アダプターのテスト

さぬき動物愛護センター（譲渡犬猫）用 rule-based adapter の動作を検証。

検証観点:
- 一覧ページから PDF リンク (`/documents/6103/...pdf`) を抽出する。
- PDF URL は detail HTML を持たないため、`extract_animal_details` は
  ネットワークアクセスせずファイル名から species を推定して
  最小 RawAnimalData を構築する。
- 在庫 0 件 (PDF が掲示されない状態) は ParsingError ではなく
  空リストを返す。
- requires_js のため PlaywrightFetchMixin と多重継承する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.sanuki_kagawa import (
    SanukiKagawaAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import (
    WordPressListAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────── SiteConfig ───────────────────


def _site() -> SiteConfig:
    """sites.yaml と同じ list_url を持つ SiteConfig"""
    return SiteConfig(
        name="さぬき動物愛護センター（譲渡犬猫）",
        prefecture="香川県",
        prefecture_code="37",
        list_url=(
            "https://www.pref.kagawa.lg.jp/s-doubutuaigo/sanukidouaicenter/"
            "jyouto/s04u6e190311095146.html"
        ),
        category="adoption",
        requires_js=True,
        pdf_link_pattern="a[href*='/documents/6103/'][href$='.pdf']",
        pdf_multi_animal=True,
    )


# ─────────────────── 想定 HTML フィクスチャ ───────────────────
# 実ページの簡易再現。PDF リンク 2 件 (犬・猫) と
# ナビゲーション/装飾の非対象リンクを含める。

LIST_HTML = """
<html><body>
  <div id="main">
    <h1>譲渡犬猫情報</h1>
    <ul>
      <li>
        <a href="/documents/6103/0318dog.pdf">譲渡犬一覧 (3/18 更新)</a>
      </li>
      <li>
        <a href="/documents/6103/0321cat.pdf">譲渡猫一覧 (3/21 更新)</a>
      </li>
    </ul>
    <p>
      <a href="/s-doubutuaigo/sanukidouaicenter/index.html">トップへ戻る</a>
      <a href="/documents/9999/other.pdf">その他のお知らせ (対象外)</a>
    </p>
  </div>
</body></html>
"""

# 重複 PDF URL を含む HTML (dedupe 検証用)
LIST_HTML_DUPLICATE = """
<html><body>
  <ul>
    <li><a href="/documents/6103/0318dog.pdf">譲渡犬</a></li>
    <li><a href="/documents/6103/0318dog.pdf">譲渡犬 (再掲)</a></li>
    <li><a href="/documents/6103/0321cat.pdf">譲渡猫</a></li>
  </ul>
</body></html>
"""

# 在庫 0 件 (PDF が一切貼られていない状態)
EMPTY_HTML = """
<html><body>
  <div id="main">
    <p>現在掲載中の譲渡対象動物はいません。</p>
  </div>
</body></html>
"""


# ─────────────────── list 抽出 ───────────────────


class TestSanukiKagawaListExtraction:
    """fetch_animal_list が PDF リンクを正しく抽出すること"""

    def test_fetch_returns_pdf_urls(self):
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        urls = [u for u, _ in result]
        assert "https://www.pref.kagawa.lg.jp/documents/6103/0318dog.pdf" in urls
        assert "https://www.pref.kagawa.lg.jp/documents/6103/0321cat.pdf" in urls

    def test_fetch_urls_are_absolute(self):
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        for url, _ in result:
            assert url.startswith("https://www.pref.kagawa.lg.jp/")

    def test_fetch_excludes_non_target_links(self):
        """`/documents/6103/` 配下以外の PDF やナビゲーションリンクは除外"""
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        for url, _ in result:
            assert "/documents/6103/" in url
            assert url.endswith(".pdf")
            assert "/documents/9999/" not in url

    def test_fetch_category_is_from_site_config(self):
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        assert all(c == "adoption" for _, c in result)

    def test_fetch_dedupes_duplicate_pdf_urls(self):
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_DUPLICATE):
            result = adapter.fetch_animal_list()
        urls = [u for u, _ in result]
        assert len(urls) == 2
        assert len(set(urls)) == 2

    def test_empty_inventory_returns_empty_list_without_error(self):
        """PDF が無い状態でも ParsingError を出さず空リストを返す"""
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=EMPTY_HTML):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_uses_list_url_from_config(self):
        adapter = SanukiKagawaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML) as mock_get:
            adapter.fetch_animal_list()
        assert mock_get.called
        called_url = mock_get.call_args.args[0]
        assert called_url == _site().list_url


# ─────────────────── detail (PDF URL → RawAnimalData) ───────────────────


class TestSanukiKagawaDetailExtraction:
    """extract_animal_details が PDF URL から最小 RawAnimalData を構築する"""

    def test_dog_pdf_infers_species_dog(self, assert_raw_animal):
        adapter = SanukiKagawaAdapter(_site())
        url = "https://www.pref.kagawa.lg.jp/documents/6103/0318dog.pdf"
        raw = adapter.extract_animal_details(url, category="adoption")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            category="adoption",
            source_url=url,
        )
        assert raw.location == "さぬき動物愛護センター"

    def test_cat_pdf_infers_species_cat(self, assert_raw_animal):
        adapter = SanukiKagawaAdapter(_site())
        url = "https://www.pref.kagawa.lg.jp/documents/6103/0321cat.pdf"
        raw = adapter.extract_animal_details(url, category="adoption")

        assert_raw_animal(
            raw,
            species="猫",
            category="adoption",
            source_url=url,
        )

    def test_pdf_url_stored_in_image_urls(self):
        """PDF URL を image_urls に入れて pipeline 後段で参照可能にする"""
        adapter = SanukiKagawaAdapter(_site())
        url = "https://www.pref.kagawa.lg.jp/documents/6103/0318dog.pdf"
        raw = adapter.extract_animal_details(url)
        assert raw.image_urls == [url]

    def test_extract_does_not_fetch_pdf(self):
        """PDF はバイナリのため `_http_get` は呼ばない"""
        adapter = SanukiKagawaAdapter(_site())
        url = "https://www.pref.kagawa.lg.jp/documents/6103/0318dog.pdf"
        with patch.object(adapter, "_http_get") as mock_get:
            adapter.extract_animal_details(url)
        mock_get.assert_not_called()

    def test_phone_is_normalized_center_phone(self):
        adapter = SanukiKagawaAdapter(_site())
        url = "https://www.pref.kagawa.lg.jp/documents/6103/0318dog.pdf"
        raw = adapter.extract_animal_details(url)
        assert raw.phone == "087-815-2255"

    def test_unknown_filename_yields_empty_species(self):
        """ファイル名に dog/cat が無い PDF は species 空のまま返す"""
        adapter = SanukiKagawaAdapter(_site())
        url = "https://www.pref.kagawa.lg.jp/documents/6103/2024list.pdf"
        raw = adapter.extract_animal_details(url)
        assert raw.species == ""

    def test_non_pdf_url_raises_parsing_error(self):
        adapter = SanukiKagawaAdapter(_site())
        with pytest.raises(ParsingError):
            adapter.extract_animal_details("https://www.pref.kagawa.lg.jp/index.html")


# ─────────────────── normalize ───────────────────


class TestSanukiKagawaNormalize:
    def test_normalize_method_is_inherited(self):
        """normalize メソッドが基底から継承されていること

        本 adapter が返す RawAnimalData は shelter_date 等が空のため、
        実際の normalize 呼び出しは pipeline 後段 (PDF 抽出で日付等を
        補完した後) に行われる。ここでは契約 (メソッド存在) のみ検証する。
        """
        adapter = SanukiKagawaAdapter(_site())
        assert callable(getattr(adapter, "normalize", None))


# ─────────────────── Playwright 経路 ───────────────────


class TestSanukiKagawaPlaywrightIntegration:
    """PlaywrightFetchMixin を継承し、_http_get が Playwright 経由で呼ばれる"""

    def test_inherits_playwright_fetch_mixin(self):
        assert issubclass(SanukiKagawaAdapter, PlaywrightFetchMixin)
        assert issubclass(SanukiKagawaAdapter, WordPressListAdapter)

    def test_wait_selector_is_set(self):
        assert SanukiKagawaAdapter.WAIT_SELECTOR is not None
        assert "/documents/6103/" in SanukiKagawaAdapter.WAIT_SELECTOR

    def test_http_get_uses_playwright_fetcher(self):
        """_http_get は基底 RuleBasedAdapter ではなく
        PlaywrightFetchMixin の実装を呼ぶ"""
        adapter = SanukiKagawaAdapter(_site())
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = LIST_HTML

        with patch(
            "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
            return_value=mock_fetcher,
        ) as mock_cls:
            adapter._http_get(_site().list_url)

        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("wait_selector") == SanukiKagawaAdapter.WAIT_SELECTOR
        mock_fetcher.fetch.assert_called_once_with(_site().list_url)


# ─────────────────── registry ───────────────────


class TestSanukiKagawaRegistry:
    def test_site_registered_to_adapter(self):
        cls = SiteAdapterRegistry.get("さぬき動物愛護センター（譲渡犬猫）")
        assert cls is SanukiKagawaAdapter
