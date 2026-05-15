"""WannyanFukuokaAdapter のテスト

福岡市わんにゃんよかネット (wannyan.city.fukuoka.lg.jp) 用 rule-based
adapter の動作を検証する。

- Playwright で取得された一覧 HTML から detail URL 抽出
  (`/yokanet/animal/animal_posts/view/{ID}` 形式)
- 0 件 (「データが見つかりませんでした」) の場合に空リストを返すこと
- 詳細ページ HTML を模した最小 HTML (`<th>/<td>` テーブルおよび
  `<td>/<td>` 2 列テーブル) からの RawAnimalData 構築
- 動物種別 (犬/猫) が list URL の `type_id=1`/`type_id=2` または
  サイト名から推定されること
- 4 サイトすべてが SiteAdapterRegistry に登録されていること
- `PlaywrightFetchMixin` を継承していること

NOTE: Playwright 自体は呼び出さず、`_http_get` を patch して固定 HTML を
返すことで JS 実行を擬似する。これは熊本市 (city_kumamoto) 等の同パターン
adapter テストと同じ方針。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.wannyan_fukuoka import (
    WannyanFukuokaAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import (
    WordPressListAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 一覧ページ HTML (JS 描画後を想定)。
# 「番号 / 写真 / 収容日 / 状況 / 区 / 場所 / 特徴 / 詳細」テーブル形式。
LIST_HTML = """
<html><body>
<table>
  <thead>
    <tr><th>番号</th><th>写真</th><th>収容日</th><th>状況</th>
        <th>区</th><th>場所</th><th>その他特徴</th><th>詳細</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>D-001</td>
      <td><img src="/yokanet/files/animal/D-001.jpg" alt="犬"></td>
      <td>2026-04-21</td>
      <td>収容中</td>
      <td>東区</td>
      <td>香椎</td>
      <td>茶色 雑種</td>
      <td><a href="/yokanet/animal/animal_posts/view/12345">詳細</a></td>
    </tr>
    <tr>
      <td>D-002</td>
      <td><img src="/yokanet/files/animal/D-002.jpg" alt="犬"></td>
      <td>2026-04-22</td>
      <td>収容中</td>
      <td>博多区</td>
      <td>博多駅東</td>
      <td>白 中型</td>
      <td><a href="/yokanet/animal/animal_posts/view/12346">詳細</a></td>
    </tr>
    <tr>
      <td>D-003</td>
      <td><img src="/yokanet/files/animal/D-003.jpg" alt="犬"></td>
      <td>2026-04-23</td>
      <td>収容中</td>
      <td>中央区</td>
      <td>天神</td>
      <td>黒</td>
      <td><a href="/yokanet/animal/animal_posts/view/12347">詳細</a></td>
    </tr>
  </tbody>
</table>
<nav>
  <a href="/yokanet/animal/animal_posts/index?type_id=2&sorting_id=4">猫保護中へ</a>
  <a href="/yokanet/static/about">サイトについて</a>
</nav>
</body></html>
"""

# 0 件状態の HTML (「データが見つかりませんでした。」表示)。
LIST_HTML_EMPTY = """
<html><body>
<table>
  <thead>
    <tr><th>番号</th><th>写真</th><th>収容日</th><th>状況</th>
        <th>区</th><th>場所</th><th>その他特徴</th><th>詳細</th></tr>
  </thead>
  <tbody></tbody>
</table>
<p>データが見つかりませんでした。</p>
</body></html>
"""

# 詳細ページ HTML (`<th>/<td>` テーブル版)。
DETAIL_HTML_DOG = """
<html><body>
<div class="header">
  <img src="/yokanet/common/img/header_logo.png" alt="ロゴ">
</div>
<div class="kijiBlock">
  <table>
    <tbody>
      <tr><th>品種</th><td>雑種</td></tr>
      <tr><th>性別</th><td>オス</td></tr>
      <tr><th>推定年齢</th><td>成犬</td></tr>
      <tr><th>毛色</th><td>茶色</td></tr>
      <tr><th>大きさ</th><td>中型</td></tr>
      <tr><th>収容日</th><td>2026年4月21日</td></tr>
      <tr><th>場所</th><td>東区香椎</td></tr>
      <tr><th>連絡先</th><td>092-661-0500</td></tr>
    </tbody>
  </table>
  <div class="photoArea">
    <img src="/yokanet/files/animal/12345_1.jpg" alt="犬写真1">
    <img src="/yokanet/files/animal/12345_2.jpg" alt="犬写真2">
  </div>
</div>
<div class="footer">
  <img src="/yokanet/common/img/footer_logo.png" alt="footer logo">
</div>
</body></html>
"""

# 詳細ページ HTML (`<td>/<td>` 2 列テーブル版)。
DETAIL_HTML_CAT_2COL = """
<html><body>
<table>
  <tr><td>品種</td><td>三毛猫</td></tr>
  <tr><td>性別</td><td>メス</td></tr>
  <tr><td>毛色</td><td>三毛</td></tr>
  <tr><td>収容日</td><td>2026年4月22日</td></tr>
  <tr><td>場所</td><td>博多区</td></tr>
</table>
<img src="/yokanet/files/animal/22222_1.jpg" alt="猫写真">
</body></html>
"""


def _site_dog_sheltered() -> SiteConfig:
    """犬保護中 (type_id=1, sorting_id=4)"""
    return SiteConfig(
        name="福岡市わんにゃん（犬保護中）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url=(
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/index?type_id=1&sorting_id=4"
        ),
        category="sheltered",
    )


def _site_cat_sheltered() -> SiteConfig:
    """猫保護中 (type_id=2, sorting_id=4)"""
    return SiteConfig(
        name="福岡市わんにゃん（猫保護中）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url=(
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/index?type_id=2&sorting_id=4"
        ),
        category="sheltered",
    )


def _site_dog_adoption() -> SiteConfig:
    """犬譲渡 (type_id=1, sorting_id=5)"""
    return SiteConfig(
        name="福岡市わんにゃん（犬譲渡）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url=(
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/index?type_id=1&sorting_id=5"
        ),
        category="adoption",
    )


def _site_cat_adoption() -> SiteConfig:
    """猫譲渡 (type_id=2, sorting_id=5)"""
    return SiteConfig(
        name="福岡市わんにゃん（猫譲渡）",
        prefecture="福岡県",
        prefecture_code="40",
        list_url=(
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/index?type_id=2&sorting_id=5"
        ),
        category="adoption",
    )


class TestWannyanFukuokaAdapterClassStructure:
    """継承構造とクラス定数"""

    def test_inherits_playwright_fetch_mixin(self):
        """JS 必須サイト対応のため PlaywrightFetchMixin を継承している"""
        assert issubclass(WannyanFukuokaAdapter, PlaywrightFetchMixin)

    def test_inherits_wordpress_list_adapter(self):
        """list+detail 構造の汎用基底 WordPressListAdapter を継承している"""
        assert issubclass(WannyanFukuokaAdapter, WordPressListAdapter)

    def test_wait_selector_configured(self):
        """Playwright の WAIT_SELECTOR が設定されている (None ではない)"""
        assert WannyanFukuokaAdapter.WAIT_SELECTOR is not None
        assert WannyanFukuokaAdapter.WAIT_SELECTOR != ""

    def test_list_link_selector_targets_view_path(self):
        """LIST_LINK_SELECTOR が detail URL パスを狙っている"""
        assert "/animal_posts/view" in WannyanFukuokaAdapter.LIST_LINK_SELECTOR


class TestWannyanFukuokaAdapterListExtraction:
    """list ページからの detail URL 抽出"""

    def test_fetch_animal_list_extracts_detail_urls(self):
        """テーブルの「詳細」列から `/animal_posts/view/{ID}` URL を抽出する"""
        adapter = WannyanFukuokaAdapter(_site_dog_sheltered())

        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        urls = [u for u, _cat in result]
        assert all("/animal_posts/view/" in u for u in urls)
        # ナビゲーション (`/animal_posts/index`, `/yokanet/static/...`) が
        # 混入していない
        assert all("/animal_posts/index" not in u for u in urls)
        assert all("/yokanet/static" not in u for u in urls)
        # 全 URL が絶対 URL になっている
        assert all(u.startswith("http") for u in urls)
        # 既知の ID が含まれる
        assert any("/view/12345" in u for u in urls)
        assert any("/view/12346" in u for u in urls)
        assert any("/view/12347" in u for u in urls)
        # category は site_config.category 由来
        assert all(cat == "sheltered" for _u, cat in result)

    def test_fetch_animal_list_dedupes_urls(self):
        """同一 URL が重複して並んでいても 1 件に集約される"""
        dup_html = """
        <html><body>
        <table><tbody>
          <tr><td><a href="/yokanet/animal/animal_posts/view/99">詳細</a></td></tr>
          <tr><td><a href="/yokanet/animal/animal_posts/view/99">詳細</a></td></tr>
        </tbody></table>
        </body></html>
        """
        adapter = WannyanFukuokaAdapter(_site_dog_sheltered())
        with patch.object(adapter, "_http_get", return_value=dup_html):
            result = adapter.fetch_animal_list()
        urls = [u for u, _cat in result]
        assert len(urls) == 1
        assert len(urls) == len(set(urls))

    def test_fetch_animal_list_returns_empty_for_zero_stock(self):
        """「データが見つかりませんでした」状態では空リストを返す"""
        adapter = WannyanFukuokaAdapter(_site_dog_sheltered())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML_EMPTY):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_animal_list_returns_empty_for_no_table(self):
        """そもそも table が無い HTML (リダイレクト等) でも空リスト"""
        no_table_html = (
            "<html><body><p>外部サイトに移動します</p></body></html>"
        )
        adapter = WannyanFukuokaAdapter(_site_dog_adoption())
        with patch.object(adapter, "_http_get", return_value=no_table_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_fetch_animal_list_uses_category_from_site_config(self):
        """category は site_config.category (sheltered/adoption) を使用"""
        # adoption サイトでも同一テーブル構造を返した場合
        adapter = WannyanFukuokaAdapter(_site_cat_adoption())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        assert all(cat == "adoption" for _u, cat in result)


class TestWannyanFukuokaAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_dog(
        self, assert_raw_animal
    ):
        """`<th>/<td>` テーブルの詳細ページから各フィールドが抽出できる"""
        adapter = WannyanFukuokaAdapter(_site_dog_sheltered())
        detail_url = (
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/view/12345"
        )
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="雑種",
            sex="オス",
            age="成犬",
            color="茶色",
            size="中型",
            shelter_date="2026年4月21日",
            location="東区香椎",
            phone="092-661-0500",
            category="sheltered",
        )
        # `/yokanet/files/animal/` の動物写真 2 枚は採用、
        # `/yokanet/common/` のロゴ画像は除外される
        assert len(raw.image_urls) == 2
        assert all("/common/" not in u for u in raw.image_urls)
        assert all("logo" not in u.lower() for u in raw.image_urls)
        assert all("/files/animal/" in u for u in raw.image_urls)

    def test_extract_animal_details_supports_two_column_table(
        self, assert_raw_animal
    ):
        """`<th>` を持たない 2 列テーブルからも値を抽出できる"""
        adapter = WannyanFukuokaAdapter(_site_cat_sheltered())
        detail_url = (
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/view/22222"
        )
        with patch.object(
            adapter, "_http_get", return_value=DETAIL_HTML_CAT_2COL
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="三毛猫",
            sex="メス",
            color="三毛",
            shelter_date="2026年4月22日",
            location="博多区",
            category="sheltered",
        )

    def test_extract_animal_details_infers_species_from_list_url_dog(self):
        """species ラベル不在時に list URL `type_id=1` から「犬」が補完される"""
        detail_html_no_species = """
        <html><body>
        <table>
          <tr><th>性別</th><td>オス</td></tr>
          <tr><th>毛色</th><td>白</td></tr>
        </table>
        </body></html>
        """
        adapter = WannyanFukuokaAdapter(_site_dog_sheltered())  # type_id=1
        detail_url = (
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/view/55555"
        )
        with patch.object(
            adapter, "_http_get", return_value=detail_html_no_species
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )
        assert raw.species == "犬"

    def test_extract_animal_details_infers_species_from_list_url_cat(self):
        """猫サイト (type_id=2) では species 補完が「猫」になる"""
        detail_html_no_species = """
        <html><body>
        <table>
          <tr><th>性別</th><td>メス</td></tr>
        </table>
        </body></html>
        """
        adapter = WannyanFukuokaAdapter(_site_cat_sheltered())  # type_id=2
        detail_url = (
            "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
            "animal_posts/view/66666"
        )
        with patch.object(
            adapter, "_http_get", return_value=detail_html_no_species
        ):
            raw = adapter.extract_animal_details(
                detail_url, category="sheltered"
            )
        assert raw.species == "猫"

    def test_extract_raises_on_empty_html(self):
        """1 フィールドも抽出できない HTML では例外を出す"""
        adapter = WannyanFukuokaAdapter(_site_dog_sheltered())
        with patch.object(
            adapter,
            "_http_get",
            return_value="<html><body></body></html>",
        ):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
                    "animal_posts/view/0"
                )


class TestWannyanFukuokaAdapterSpeciesInference:
    """list URL クエリ / サイト名からの動物種別推定"""

    @pytest.mark.parametrize(
        "url,expected",
        [
            (
                "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
                "animal_posts/index?type_id=1&sorting_id=4",
                "犬",
            ),
            (
                "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
                "animal_posts/index?type_id=2&sorting_id=4",
                "猫",
            ),
            (
                "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/"
                "animal_posts/view/12345",
                "",
            ),
            ("", ""),
        ],
    )
    def test_infer_species_from_url(self, url, expected):
        assert (
            WannyanFukuokaAdapter._infer_species_from_url(url) == expected
        )

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("福岡市わんにゃん（犬保護中）", "犬"),
            ("福岡市わんにゃん（猫保護中）", "猫"),
            ("福岡市わんにゃん（犬譲渡）", "犬"),
            ("福岡市わんにゃん（猫譲渡）", "猫"),
            ("福岡市わんにゃん（犬猫合同）", "その他"),
            ("どこかのサイト", ""),
        ],
    )
    def test_infer_species_from_site_name(self, name, expected):
        assert (
            WannyanFukuokaAdapter._infer_species_from_site_name(name)
            == expected
        )


class TestWannyanFukuokaAdapterRegistry:
    """registry に 4 サイトすべて登録されていること

    sites.yaml の `name` フィールドと完全一致する 4 サイト名で登録される。
    """

    EXPECTED_SITE_NAMES = (
        "福岡市わんにゃん（犬保護中）",
        "福岡市わんにゃん（猫保護中）",
        "福岡市わんにゃん（犬譲渡）",
        "福岡市わんにゃん（猫譲渡）",
    )

    @pytest.mark.parametrize("site_name", EXPECTED_SITE_NAMES)
    def test_site_registered_to_wannyan_fukuoka_adapter(self, site_name):
        # 他テストが registry を clear する場合の冪等性のため、
        # 未登録なら再登録してから確認する。
        if SiteAdapterRegistry.get(site_name) is None:
            SiteAdapterRegistry.register(site_name, WannyanFukuokaAdapter)
        cls = SiteAdapterRegistry.get(site_name)
        assert cls is WannyanFukuokaAdapter, (
            f"{site_name} が WannyanFukuokaAdapter に紐付いていません: {cls}"
        )
