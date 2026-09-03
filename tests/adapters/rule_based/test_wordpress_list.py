"""WordPressListAdapter のテスト

list ページから detail URL を抽出 → detail ページから RawAnimalData を作る
共通フローと、selector ベースの宣言的フィールド抽出を検証する。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.wordpress_list import (
    FieldSpec,
    WordPressListAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

LIST_HTML = """
<html><body>
  <div class="card"><a class="more" href="/animals/1">animal1</a></div>
  <div class="card"><a class="more" href="/animals/2">animal2</a></div>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <div class="info">
    <dl>
      <dt>種別</dt><dd>犬</dd>
      <dt>性別</dt><dd>オス</dd>
      <dt>年齢</dt><dd>3歳</dd>
      <dt>毛色</dt><dd>茶白</dd>
      <dt>体格</dt><dd>中型</dd>
      <dt>収容日</dt><dd>2026-04-01</dd>
      <dt>収容場所</dt><dd>高知市</dd>
      <dt>連絡先</dt><dd>088-826-2364</dd>
    </dl>
    <img src="https://example.com/wp-content/uploads/dog1.jpg">
  </div>
</body></html>
"""


def _site() -> SiteConfig:
    return SiteConfig(
        name="サンプル譲渡サイト",
        prefecture="高知県",
        prefecture_code="39",
        list_url="https://example.com/list/",
        list_link_pattern="a.more",
        category="adoption",
    )


class _SampleWPAdapter(WordPressListAdapter):
    LIST_LINK_SELECTOR = "a.more"
    FIELD_SELECTORS = {
        "species": FieldSpec(label="種別"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="体格"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="収容場所"),
        "phone": FieldSpec(label="連絡先"),
    }
    IMAGE_SELECTOR = "div.info img"


class TestWordPressListAdapter:
    def test_fetch_animal_list_extracts_detail_urls(self):
        adapter = _SampleWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        assert len(result) == 2
        urls = [u for u, _cat in result]
        assert "https://example.com/animals/1" in urls
        assert "https://example.com/animals/2" in urls
        # category は site_config.category 由来
        assert all(cat == "adoption" for _u, cat in result)

    def test_extract_animal_details_returns_raw_data(self):
        adapter = _SampleWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML):
            raw = adapter.extract_animal_details("https://example.com/animals/1")
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.age == "3歳"
        assert raw.shelter_date == "2026-04-01"
        assert raw.location == "高知市"
        assert raw.phone == "088-826-2364"
        assert raw.image_urls == ["https://example.com/wp-content/uploads/dog1.jpg"]
        assert raw.source_url == "https://example.com/animals/1"
        assert raw.category == "adoption"

    def test_extract_raises_parsing_error_when_no_dl(self):
        adapter = _SampleWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):  # ParsingError or ValidationError
                adapter.extract_animal_details("https://example.com/animals/1")

    def test_extract_by_label_prefers_exact_over_partial(self):
        """ラベル完全一致を優先し、'色' が '特色' を誤って拾わない

        部分一致のみだと DOM 順で先に来る紛らわしい見出し (特色=特徴) を
        拾い、色の値に説明文が入る誤抽出が起きる。
        """
        from bs4 import BeautifulSoup

        adapter = _SampleWPAdapter(_site())
        html = (
            "<table>"
            "<tr><th>特色</th><td>人なつこい</td></tr>"
            "<tr><th>色</th><td>茶色</td></tr>"
            "</table>"
        )
        soup = BeautifulSoup(html, "html.parser")
        assert adapter._extract_by_label(soup, "色") == "茶色"

        # 完全一致が無ければ部分一致にフォールバック (後方互換: '色'→'毛色')
        soup2 = BeautifulSoup("<dl><dt>毛色</dt><dd>白黒</dd></dl>", "html.parser")
        assert adapter._extract_by_label(soup2, "色") == "白黒"

    def test_fetch_animal_list_returns_empty_when_no_links(self):
        # list ページが取得できても detail link が 1 つも無い (=現在その種別の
        # 収容動物がいない真ゼロ) ケースを error にせず空リストで返す。
        adapter = _SampleWPAdapter(_site())
        empty_html = "<html><body><div class='card'>該当する動物はいません</div></body></html>"
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_normalize_delegates_to_data_normalizer(self):
        adapter = _SampleWPAdapter(_site())
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="3歳",
            color="茶",
            size="中型",
            shelter_date="2026-04-01",
            location="高知市",
            phone="088-826-2364",
            image_urls=["https://example.com/img.jpg"],
            source_url="https://example.com/animals/1",
            category="adoption",
        )
        result = adapter.normalize(raw)
        assert result.species == "犬"

    def test_identity_fields_passthrough_via_field_selectors(self):
        """FIELD_SELECTORS で個体識別キーを宣言すれば RawAnimalData に転写される

        kochi 同型のサイレントドロップ予防の回帰防止テスト。
        基底経路が breed/description/name/management_number の4キーを
        構築子に渡していることを直接検証する。
        """

        class _IdentityWPAdapter(WordPressListAdapter):
            LIST_LINK_SELECTOR = "a.more"
            FIELD_SELECTORS = {
                "species": FieldSpec(label="種別"),
                # 派生は FIELD_SELECTORS にキーを足すだけで開通する
                "name": FieldSpec(label="名前"),
                "breed": FieldSpec(label="品種"),
                "management_number": FieldSpec(label="管理番号"),
                "description": FieldSpec(label="特徴"),
            }

        html = (
            "<html><body><div class='info'><dl>"
            "<dt>種別</dt><dd>犬</dd>"
            "<dt>名前</dt><dd>ポチ</dd>"
            "<dt>品種</dt><dd>柴犬</dd>"
            "<dt>管理番号</dt><dd>2026-001</dd>"
            "<dt>特徴</dt><dd>人懐っこい</dd>"
            "</dl></div></body></html>"
        )
        adapter = _IdentityWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details("https://example.com/animals/1")
        assert raw.name == "ポチ"
        assert raw.breed == "柴犬"
        assert raw.management_number == "2026-001"
        assert raw.description == "人懐っこい"


# ─────────────────── ページ送り (T132) ───────────────────

PAGE1_HTML = """
<html><body>
  <div class="card"><a class="more" href="/animals/1">animal1</a></div>
  <div class="card"><a class="more" href="/animals/2">animal2</a></div>
  <div class="paging">
    <span class="current">1</span>
    <span><a href="/list/page:2">2</a></span>
    <span class="next"><a href="/list/page:2" rel="next">next &gt;</a></span>
  </div>
</body></html>
"""

PAGE2_HTML = """
<html><body>
  <div class="card"><a class="more" href="/animals/3">animal3</a></div>
  <div class="paging">
    <span class="prev"><a href="/list/" rel="prev">&lt; previous</a></span>
    <span class="current">2</span>
  </div>
</body></html>
"""


class _PagedWPAdapter(_SampleWPAdapter):
    """next リンクを辿るサイト (沖縄 aniwel の `<div class="paging">` 構造)"""

    NEXT_PAGE_SELECTOR = ".paging a[rel='next']"


class TestWordPressListAdapterPagination:
    """一覧のページ送り未追随による掲載漏れ (T132)

    `WordPressListAdapter.fetch_animal_list` は list_url の 1 ページ目しか
    読んでいなかった。沖縄県動物愛護管理センターの行方不明犬 (2ページ) と
    行方不明猫 (3ページ) で 2 ページ目以降が丸ごと未収集になり、
    実サイト111件に対し本番 API は86件、URL 集合の差は25件 (全て
    `missing_view`) だった。
    """

    def test_follows_next_link_and_collects_all_pages(self):
        adapter = _PagedWPAdapter(_site())
        pages = {
            "https://example.com/list/": PAGE1_HTML,
            "https://example.com/list/page:2": PAGE2_HTML,
        }
        with patch.object(adapter, "_http_get", side_effect=lambda url: pages[url]):
            result = adapter.fetch_animal_list()

        urls = [u for u, _cat in result]
        assert urls == [
            "https://example.com/animals/1",
            "https://example.com/animals/2",
            "https://example.com/animals/3",
        ]
        assert adapter.list_truncated is False

    def test_without_selector_reads_only_first_page(self):
        """NEXT_PAGE_SELECTOR 未定義の派生クラスは従来どおり 1 ページのみ"""
        adapter = _SampleWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=PAGE1_HTML) as m:
            result = adapter.fetch_animal_list()
        assert len(result) == 2
        assert m.call_count == 1

    def test_dedupes_urls_across_pages(self):
        """ページ間で同じ detail URL が重複しても 1 件に畳む"""
        page2_dup = PAGE2_HTML.replace("/animals/3", "/animals/2")
        adapter = _PagedWPAdapter(_site())
        pages = {
            "https://example.com/list/": PAGE1_HTML,
            "https://example.com/list/page:2": page2_dup,
        }
        with patch.object(adapter, "_http_get", side_effect=lambda url: pages[url]):
            result = adapter.fetch_animal_list()
        assert len(result) == 2

    def test_cycle_detection_sets_list_truncated(self):
        """next が既訪問ページを指したら打ち切り、list_truncated を立てる

        部分集合のまま prune_disappeared が走ると、未取得ページに載っている
        実在個体を誤って公開から消してしまうため (T059)。
        """
        loop_html = PAGE1_HTML.replace('href="/list/page:2" rel="next"', 'href="/list/" rel="next"')
        adapter = _PagedWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=loop_html):
            result = adapter.fetch_animal_list()
        assert len(result) == 2
        assert adapter.list_truncated is True

    def test_page_limit_sets_list_truncated(self):
        """上限ページ数に達したら打ち切り、list_truncated を立てる"""

        class _TinyLimitAdapter(_PagedWPAdapter):
            MAX_LIST_PAGES = 2

        adapter = _TinyLimitAdapter(_site())
        # 各ページが常に「次の」新しいページを指し続ける
        counter = {"n": 0}

        def _fake_get(url: str) -> str:
            counter["n"] += 1
            n = counter["n"]
            return f"""
            <html><body>
              <div class="card"><a class="more" href="/animals/{n}">a{n}</a></div>
              <div class="paging"><span class="next">
                <a href="/list/page:{n + 1}" rel="next">next</a>
              </span></div>
            </body></html>
            """

        with patch.object(adapter, "_http_get", side_effect=_fake_get):
            result = adapter.fetch_animal_list()
        assert len(result) == 2
        assert adapter.list_truncated is True

    def test_empty_first_page_is_true_zero(self):
        """1 ページ目に detail link が無ければ従来どおり真ゼロ扱い"""
        adapter = _PagedWPAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            assert adapter.fetch_animal_list() == []
        assert adapter.list_truncated is False
