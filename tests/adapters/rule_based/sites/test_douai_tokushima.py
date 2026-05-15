"""DouaiTokushimaAdapter (douai-tokushima.com) アダプターのテスト

徳島県動物愛護管理センターの 3 サイト (収容中 / 譲渡犬 / 譲渡猫) を
共通アダプターでカバーする構造を検証。

特徴:
- 実データはラッパページ (`/stray/` 等) ではなく iframe URL
  (`/animalinfo/list1/` 等) に存在 → adapter が iframe URL に
  差し替えて fetch する。
- 各動物は `<ul class="news"> <li> <table> ... </table> </li> </ul>`
  形式で表現され、データセルは `aria-label` で意味づけされている。
- 個別 detail ページが無いため SinglePageTableAdapter ベースで
  仮想 URL (`#row=N`) を発行。
- requires_js のため PlaywrightFetchMixin と多重継承する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.single_page_table import (
    SinglePageTableAdapter,
)
from data_collector.adapters.rule_based.sites.douai_tokushima import (
    DouaiTokushimaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


# ─────────────────── SiteConfig helpers ───────────────────


def _stray_site() -> SiteConfig:
    """収容中サイト (sites.yaml と同じ list_url)"""
    return SiteConfig(
        name="徳島県動物愛護管理センター（収容中）",
        prefecture="徳島県",
        prefecture_code="36",
        list_url="https://douai-tokushima.com/stray/",
        category="lost",
        requires_js=True,
    )


def _dog_site() -> SiteConfig:
    return SiteConfig(
        name="徳島県動物愛護管理センター（譲渡犬）",
        prefecture="徳島県",
        prefecture_code="36",
        list_url="https://douai-tokushima.com/transfer/doglist",
        category="adoption",
        requires_js=True,
    )


def _cat_site() -> SiteConfig:
    return SiteConfig(
        name="徳島県動物愛護管理センター（譲渡猫）",
        prefecture="徳島県",
        prefecture_code="36",
        list_url="https://douai-tokushima.com/transfer/catlist",
        category="adoption",
        requires_js=True,
    )


# ─────────────────── 想定 HTML フィクスチャ ───────────────────
# 実 iframe ページ (`/animalinfo/list1/` 等) の縮小版。
# 実際のサイトは EUC-JP だが、Playwright (page.content) は Unicode 文字列を
# 返すため、テスト側は最初から UTF-8 文字列で扱う。

# 収容中: 1 ページに 2 件 (犬と猫を 1 件ずつ)
STRAY_HTML = """
<html><body>
  <ul class="news">
    <li>
      <table class="f_a">
        <tr>
          <td class="photo" rowspan="10">
            <a href="../list1_1/photo/photo2-17788280710.JPG" rel="colorbox">
              <img src="../list1_1/photo/photo2-17788280710.JPG" alt="">
            </a>
          </td>
          <th colspan="2">発見日</th>
        </tr>
        <tr><td colspan="2" aria-label="発見日">2026/5/15</td></tr>
        <tr><th colspan="2">内容情報</th></tr>
        <tr>
          <td colspan="2" aria-label="内容情報">
            徳島市南町道路上で保護<br>
          </td>
        </tr>
        <tr><th>種類</th><th>性別</th></tr>
        <tr>
          <td aria-label="種類">犬</td>
          <td aria-label="性別">メス</td>
        </tr>
        <tr><th>推定年齢</th><th>体格</th></tr>
        <tr>
          <td aria-label="推定年齢">成犬</td>
          <td aria-label="体格">中型</td>
        </tr>
        <tr><th>毛色</th><th>その他特徴</th></tr>
        <tr>
          <td aria-label="毛色">茶</td>
          <td aria-label="その他特徴">--</td>
        </tr>
      </table>
    </li>
    <li>
      <table class="f_a">
        <tr>
          <td class="photo" rowspan="10">
            <img src="../list1_1/photo/photo2-17788280720.JPG" alt="">
          </td>
          <th colspan="2">発見日</th>
        </tr>
        <tr><td colspan="2" aria-label="発見日">2026/5/14</td></tr>
        <tr><th colspan="2">内容情報</th></tr>
        <tr><td colspan="2" aria-label="内容情報">徳島市内で保護</td></tr>
        <tr><th>種類</th><th>性別</th></tr>
        <tr>
          <td aria-label="種類">猫</td>
          <td aria-label="性別">オス</td>
        </tr>
        <tr><th>推定年齢</th><th>体格</th></tr>
        <tr>
          <td aria-label="推定年齢">幼猫</td>
          <td aria-label="体格">小型</td>
        </tr>
        <tr><th>毛色</th><th>その他特徴</th></tr>
        <tr>
          <td aria-label="毛色">キジ白</td>
          <td aria-label="その他特徴">--</td>
        </tr>
      </table>
    </li>
  </ul>
</body></html>
"""

# 譲渡犬: 1 件のみ (`<table class="f_a3">` フォーマット)
DOG_TRANSFER_HTML = """
<html><body>
  <ul class="news">
    <li>
      <table class="f_a3">
        <tr>
          <td rowspan="6" class="photo">
            <a href="photo/photo2-17781453580.JPG" rel="colorbox" class="photo1">
              <img src="photo/photo2-17781453580.JPG" alt="">
            </a>
          </td>
          <th>番号</th>
        </tr>
        <tr>
          <td aria-label="番号">No. Ｄ２５０４２０（愛称：音愛）</td>
        </tr>
        <tr><th>譲渡状況</th></tr>
        <tr>
          <td aria-label="譲渡状況">譲渡可能(体調によっては変更あり)</td>
        </tr>
        <tr><th>譲渡可能日</th></tr>
        <tr>
          <td aria-label="譲渡可能日">２０２５年５月１０日 以降</td>
        </tr>
        <tr><th>推定生年月日</th><th>性別</th></tr>
        <tr>
          <td aria-label="推定生年月日">２０２５年８月８日</td>
          <td aria-label="性別">メス(避妊手術済)</td>
        </tr>
        <tr><th>愛嬌</th><th>やんちゃさ</th></tr>
        <tr>
          <td aria-label="愛嬌">★★☆</td>
          <td aria-label="やんちゃさ">★☆☆</td>
        </tr>
        <tr><th colspan="2">その他の情報</th></tr>
        <tr>
          <td colspan="2" aria-label="その他の情報">怖がりな白い子です。</td>
        </tr>
      </table>
    </li>
  </ul>
</body></html>
"""

# 譲渡猫: 1 件のみ
CAT_TRANSFER_HTML = """
<html><body>
  <ul class="news">
    <li>
      <table class="f_a3">
        <tr>
          <td rowspan="6" class="photo">
            <img src="photo/photo2-17780384860.JPG" alt="">
          </td>
          <th>番号</th>
        </tr>
        <tr><td aria-label="番号">No. Ｃ２６００１（愛称：たま）</td></tr>
        <tr><th>譲渡状況</th></tr>
        <tr><td aria-label="譲渡状況">譲渡可能</td></tr>
        <tr><th>推定生年月日</th><th>性別</th></tr>
        <tr>
          <td aria-label="推定生年月日">２０２５年４月１日</td>
          <td aria-label="性別">オス</td>
        </tr>
      </table>
    </li>
  </ul>
</body></html>
"""

# 在庫 0 件 (iframe は読み込めるが ul.news 配下に <li> が無い)
EMPTY_HTML = '<html><body><ul class="news"></ul></body></html>'


# ─────────────────── iframe URL マッピング ───────────────────


class TestIframeUrlMapping:
    """ラッパ list_url → iframe URL の差し替えが正しく行われること"""

    def test_stray_uses_list1_iframe(self):
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(
            adapter, "_http_get", return_value=STRAY_HTML
        ) as mock_get:
            adapter.fetch_animal_list()
        # ラッパ /stray/ ではなく iframe URL を fetch する
        assert mock_get.called
        called_url = mock_get.call_args.args[0]
        assert called_url == "https://douai-tokushima.com/animalinfo/list1/"

    def test_dog_transfer_uses_list4_1_iframe(self):
        adapter = DouaiTokushimaAdapter(_dog_site())
        with patch.object(
            adapter, "_http_get", return_value=DOG_TRANSFER_HTML
        ) as mock_get:
            adapter.fetch_animal_list()
        called_url = mock_get.call_args.args[0]
        assert called_url == "https://douai-tokushima.com/animalinfo/list4_1"

    def test_cat_transfer_uses_list4_2_iframe(self):
        adapter = DouaiTokushimaAdapter(_cat_site())
        with patch.object(
            adapter, "_http_get", return_value=CAT_TRANSFER_HTML
        ) as mock_get:
            adapter.fetch_animal_list()
        called_url = mock_get.call_args.args[0]
        assert called_url == "https://douai-tokushima.com/animalinfo/list4_2"


# ─────────────────── list 抽出 ───────────────────


class TestDouaiTokushimaListExtraction:
    """fetch_animal_list が `<ul.news > li>` 単位で行を返すこと"""

    def test_stray_fetch_returns_two_rows(self):
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(adapter, "_http_get", return_value=STRAY_HTML):
            result = adapter.fetch_animal_list()
        assert len(result) == 2
        # 仮想 URL は iframe URL を base にする
        urls = [u for u, _ in result]
        assert urls[0] == "https://douai-tokushima.com/animalinfo/list1/#row=0"
        assert urls[1] == "https://douai-tokushima.com/animalinfo/list1/#row=1"
        # category は site_config.category 由来
        assert all(c == "lost" for _, c in result)

    def test_dog_fetch_returns_one_row_with_adoption_category(self):
        adapter = DouaiTokushimaAdapter(_dog_site())
        with patch.object(adapter, "_http_get", return_value=DOG_TRANSFER_HTML):
            result = adapter.fetch_animal_list()
        assert len(result) == 1
        url, cat = result[0]
        assert url == "https://douai-tokushima.com/animalinfo/list4_1#row=0"
        assert cat == "adoption"

    def test_empty_inventory_returns_empty_list_without_error(self):
        """在庫 0 件でも ParsingError を出さず空リストを返す"""
        adapter = DouaiTokushimaAdapter(_dog_site())
        with patch.object(adapter, "_http_get", return_value=EMPTY_HTML):
            result = adapter.fetch_animal_list()
        assert result == []


# ─────────────────── detail (aria-label 抽出) ───────────────────


class TestDouaiTokushimaDetailExtraction:
    """各 <li> 行から RawAnimalData を構築できる"""

    def test_stray_extract_first_row_dog(self, assert_raw_animal):
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(adapter, "_http_get", return_value=STRAY_HTML):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            sex="メス",
            age="成犬",
            color="茶",
            size="中型",
            shelter_date="2026/5/15",
            category="lost",
            source_url=url,
        )
        # location は固定でセンター名
        assert raw.location == "徳島県動物愛護管理センター"

    def test_stray_extract_second_row_cat(self, assert_raw_animal):
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(adapter, "_http_get", return_value=STRAY_HTML):
            urls = adapter.fetch_animal_list()
            url, category = urls[1]
            raw = adapter.extract_animal_details(url, category=category)
        assert_raw_animal(
            raw,
            species="猫",
            sex="オス",
            age="幼猫",
            color="キジ白",
            size="小型",
            shelter_date="2026/5/14",
        )

    def test_dog_transfer_uses_species_hint_when_table_lacks_kind(
        self, assert_raw_animal
    ):
        """譲渡犬テーブルには `<td aria-label="種類">` が無いが、
        サイト名から species を「犬」に補完できる"""
        adapter = DouaiTokushimaAdapter(_dog_site())
        with patch.object(adapter, "_http_get", return_value=DOG_TRANSFER_HTML):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)
        assert_raw_animal(
            raw,
            species="犬",
            sex="メス(避妊手術済)",
            age="２０２５年８月８日",
            category="adoption",
        )

    def test_cat_transfer_uses_species_hint(self, assert_raw_animal):
        adapter = DouaiTokushimaAdapter(_cat_site())
        with patch.object(adapter, "_http_get", return_value=CAT_TRANSFER_HTML):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)
        assert_raw_animal(
            raw,
            species="猫",
            sex="オス",
            age="２０２５年４月１日",
            category="adoption",
        )

    def test_extract_collects_row_images(self):
        """行内の <img> URL を絶対化して image_urls に格納"""
        adapter = DouaiTokushimaAdapter(_dog_site())
        with patch.object(adapter, "_http_get", return_value=DOG_TRANSFER_HTML):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0])
        assert raw.image_urls
        # photo/... 相対パスが iframe URL 起点で絶対化される
        assert any("photo/photo2-17781453580.JPG" in u for u in raw.image_urls)
        assert all(u.startswith("https://douai-tokushima.com/") for u in raw.image_urls)

    def test_http_get_cached_across_list_and_detail(self):
        """fetch + N件 extract で _http_get は 1 回しか呼ばれない"""
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(
            adapter, "_http_get", return_value=STRAY_HTML
        ) as mock_get:
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                adapter.extract_animal_details(url, category=cat)
        assert mock_get.call_count == 1


# ─────────────────── normalize ───────────────────


class TestDouaiTokushimaNormalize:
    def test_normalize_returns_animal_data(self):
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(adapter, "_http_get", return_value=STRAY_HTML):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)
            normalized = adapter.normalize(raw)
        assert normalized is not None
        assert hasattr(normalized, "species")


# ─────────────────── Playwright 経路 ───────────────────


class TestDouaiTokushimaPlaywrightIntegration:
    """PlaywrightFetchMixin を継承しており、_http_get が
    PlaywrightFetcher 経由で呼ばれることを確認"""

    def test_inherits_playwright_fetch_mixin(self):
        assert issubclass(DouaiTokushimaAdapter, PlaywrightFetchMixin)
        assert issubclass(DouaiTokushimaAdapter, SinglePageTableAdapter)

    def test_wait_selector_is_set(self):
        assert DouaiTokushimaAdapter.WAIT_SELECTOR == "ul.news"

    def test_http_get_uses_playwright_fetcher(self):
        """_http_get は基底 RuleBasedAdapter ではなく
        PlaywrightFetchMixin の実装を呼ぶ"""
        adapter = DouaiTokushimaAdapter(_stray_site())
        mock_fetcher = MagicMock()
        mock_fetcher.fetch.return_value = STRAY_HTML

        with patch(
            "data_collector.adapters.rule_based.playwright.PlaywrightFetcher",
            return_value=mock_fetcher,
        ) as mock_cls:
            adapter._http_get(
                "https://douai-tokushima.com/animalinfo/list1/"
            )

        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        assert kwargs.get("wait_selector") == "ul.news"
        mock_fetcher.fetch.assert_called_once_with(
            "https://douai-tokushima.com/animalinfo/list1/"
        )


# ─────────────────── registry ───────────────────


class TestDouaiTokushimaRegistry:
    """3 サイトすべてが registry に登録されていること"""

    EXPECTED_SITE_NAMES = (
        "徳島県動物愛護管理センター（収容中）",
        "徳島県動物愛護管理センター（譲渡犬）",
        "徳島県動物愛護管理センター（譲渡猫）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_adapter(self, site_name):
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is DouaiTokushimaAdapter, (
            f"{site_name} が DouaiTokushimaAdapter に紐付いていません: {cls}"
        )


# ─────────────────── エラーハンドリング ───────────────────


class TestDouaiTokushimaErrorHandling:
    def test_unknown_list_url_raises_parsing_error(self):
        """マッピングに無い list_url を持つ SiteConfig は明示的に失敗"""
        site = SiteConfig(
            name="徳島県動物愛護管理センター（収容中）",
            prefecture="徳島県",
            prefecture_code="36",
            list_url="https://douai-tokushima.com/unknown/",
            category="lost",
            requires_js=True,
        )
        adapter = DouaiTokushimaAdapter(site)
        with pytest.raises(ParsingError):
            adapter.fetch_animal_list()

    def test_out_of_range_row_index_raises(self):
        adapter = DouaiTokushimaAdapter(_stray_site())
        with patch.object(adapter, "_http_get", return_value=STRAY_HTML):
            adapter.fetch_animal_list()
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    "https://douai-tokushima.com/animalinfo/list1/#row=99"
                )
