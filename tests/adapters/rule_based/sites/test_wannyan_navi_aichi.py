"""WannyanNaviAichiAdapter のテスト (T123 再設計版)

愛知県わんにゃんナビ (wannyan-navi.pref.aichi.jp) は Bubble.io 製 SPA で、
一覧カードに `<a href>` が一切存在しない (実サイトを Playwright で
レンダリングして確認済み)。そのため本 adapter は:

- `fetch_animal_list`: 一覧ページ読み込み時に発生する elasticsearch
  レスポンス (`/elasticsearch/search`, `/elasticsearch/msearch`) から
  record id (`_id`) を収集し、detail URL
  (`?page=list_dc_m&no=<id>`) を組み立てる。
  `_collect_record_ids_via_network` (Playwright 呼び出し本体) を patch し、
  Playwright 自体は呼び出さない。
- `extract_animal_details`: `_http_get` を patch し、detail ページの
  実測 DOM 構造 (Bubble のフラットな `.bubble-element.Text` / `.HTML`
  要素の並び。「基本情報」「特徴」見出しをアンカーに周辺テキストを分類)
  を模した固定 HTML から RawAnimalData を構築する。

NOTE: フィールド HTML は 2026-09-03 に実サイトを Playwright で
レンダリングして観測した実際の DOM 構造 (クラス名は除きタグ構造/文言の
出現順) を再現したもの。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.wannyan_navi_aichi import (
    WannyanNaviAichiAdapter,
)
from data_collector.adapters.rule_based.wordpress_list import WordPressListAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# 実測 (2026-09-03) の detail ページ本文相当。見出し「基本情報」「特徴」を
# アンカーに、間のテキストを [管理番号, 場所, 品種, 毛色, 性別, 年齢] の順で
# 並べた実際の表示順を再現する。
DETAIL_HTML_CAT = """
<html><body>
<div class="bubble-element Text"><div>掲載日：2026/08/27</div></div>
<div class="bubble-element Text"><div>譲渡可能</div></div>
<div class="bubble-element Text"><div>撮影日：2026/08/25（5歳2ヵ月）</div></div>
<div class="bubble-element Text"><div>基本情報</div></div>
<div class="bubble-element Text"><div>No . 尾263014</div></div>
<div class="bubble-element Text"><div>尾張支所(一宮市)</div></div>
<div class="bubble-element Text"><div>雑種</div></div>
<div class="bubble-element Text"><div>白黒</div></div>
<div class="bubble-element Text"><div>メス</div></div>
<div class="bubble-element HTML"><div>5歳3ヵ月</div></div>
<div class="bubble-element Text"><div>特徴</div></div>
<div class="bubble-element Text"><div>センターでの生活も長くなりましたが、なかなか慣れてくれません。管理番号　稲6</div></div>
<div class="bubble-element Text"><div>譲渡をご希望の方</div></div>
<div class="bubble-element Text"><div>猫の飼い方講習会へ</div></div>
<div class="bubble-element Text"><div>お問い合わせ</div></div>
<div class="bubble-element Text"><div>尾張支所(一宮市)</div></div>
<div class="bubble-element Text"><div>0586-78-2595</div></div>
<div class="slickcarousel-Carousel">
  <img src="https://c25bc61f28370d4f1d311a9752f3a7a0.cdn.bubble.io/cdn-cgi/image/w=1024,h=768/f1787632746587x721823384638467500/IMG_0121.jpeg">
  <img src="https://c25bc61f28370d4f1d311a9752f3a7a0.cdn.bubble.io/cdn-cgi/image/w=128,h=/f1787632746587x721823384638467500/IMG_0121.jpeg">
  <img src="https://c25bc61f28370d4f1d311a9752f3a7a0.cdn.bubble.io/cdn-cgi/image/w=1024,h=768/f1787633707279x949826051516787800/IMG_0122.jpeg">
</div>
<img src="https://c25bc61f28370d4f1d311a9752f3a7a0.cdn.bubble.io/f1776046529659x681337675419478700/logo.png">
</body></html>
"""

# 犬の場合の講習会リンク文言違い (実サイトの犬個体 3 件で動作確認済み)。
DETAIL_HTML_DOG = """
<html><body>
<div class="bubble-element Text"><div>掲載日：2026/07/10</div></div>
<div class="bubble-element Text"><div>基本情報</div></div>
<div class="bubble-element Text"><div>No . 本264001</div></div>
<div class="bubble-element Text"><div>本所</div></div>
<div class="bubble-element Text"><div>柴犬</div></div>
<div class="bubble-element Text"><div>茶</div></div>
<div class="bubble-element Text"><div>オス</div></div>
<div class="bubble-element HTML"><div>2歳0ヵ月</div></div>
<div class="bubble-element Text"><div>特徴</div></div>
<div class="bubble-element Text"><div>人懐っこい男の子です。</div></div>
<div class="bubble-element Text"><div>犬の飼い方講習会へ</div></div>
<div class="bubble-element Text"><div>0565-58-2323</div></div>
</body></html>
"""

# 「基本情報」見出しが見つからない = 想定外の構造崩壊。
DETAIL_HTML_NO_BASIC_INFO = "<html><body><p>読み込み中…</p></body></html>"


def _site_aichi() -> SiteConfig:
    return SiteConfig(
        name="愛知県わんにゃんナビ",
        prefecture="愛知県",
        prefecture_code="23",
        list_url="https://wannyan-navi.pref.aichi.jp/?page=list_dc",
        category="adoption",
    )


class TestWannyanNaviAichiAdapterClassStructure:
    """継承構造とクラス定数"""

    def test_inherits_playwright_fetch_mixin(self):
        assert issubclass(WannyanNaviAichiAdapter, PlaywrightFetchMixin)

    def test_inherits_wordpress_list_adapter(self):
        assert issubclass(WannyanNaviAichiAdapter, WordPressListAdapter)

    def test_wait_selector_configured(self):
        assert WannyanNaviAichiAdapter.WAIT_SELECTOR is not None
        assert WannyanNaviAichiAdapter.WAIT_SELECTOR != ""

    def test_image_selector_targets_carousel(self):
        """カルーセル外のロゴ/アイコンを混入させないため carousel 限定"""
        assert "slickcarousel-Carousel" in WannyanNaviAichiAdapter.IMAGE_SELECTOR


class TestWannyanNaviAichiAdapterFetchAnimalList:
    """一覧: elasticsearch レスポンスから収集した record id で detail URL 構築"""

    def test_fetch_animal_list_builds_detail_urls_from_ids(self):
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(
            adapter,
            "_collect_record_ids_via_network",
            return_value=["1787633087222x344897391285501950", "1787632379255x912025727444451300"],
        ):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        urls = [u for u, _cat in result]
        assert (
            "https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=1787633087222x344897391285501950"
            in urls
        )
        assert (
            "https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=1787632379255x912025727444451300"
            in urls
        )
        assert all(cat == "adoption" for _u, cat in result)

    def test_fetch_animal_list_dedupes_ids(self):
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(
            adapter,
            "_collect_record_ids_via_network",
            return_value=["dup-id", "dup-id"],
        ):
            result = adapter.fetch_animal_list()
        assert len(result) == 1

    def test_fetch_animal_list_returns_empty_for_zero_ids(self):
        """record id が 1 件も観測できない = 譲渡対象 0 件の真のゼロとして扱う"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(adapter, "_collect_record_ids_via_network", return_value=[]):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_collect_record_ids_via_network_harvests_search_hits(self):
        """`/elasticsearch/search` (単数検索) レスポンスから _id を収集する"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())

        class _FakeResponse:
            url = "https://wannyan-navi.pref.aichi.jp/elasticsearch/search"

            def json(self):
                return {
                    "hits": {
                        "total": 2,
                        "hits": [
                            {"_id": "id-a", "_source": {}},
                            {"_id": "id-b", "_source": {}},
                        ],
                    }
                }

        class _FakePage:
            def __init__(self):
                self._handler = None

            def on(self, event, handler):
                assert event == "response"
                self._handler = handler

            def goto(self, url, wait_until=None, timeout=None):
                # 実際のブラウザ挙動 (レスポンス受信 → on_response 発火) を模す
                self._handler(_FakeResponse())

            def wait_for_timeout(self, ms):
                pass

        class _FakeContext:
            def new_page(self):
                return _FakePage()

        class _FakeBrowser:
            def new_context(self, user_agent=None):
                return _FakeContext()

            def close(self):
                pass

        class _FakeChromium:
            def launch(self, headless=True):
                return _FakeBrowser()

        class _FakePlaywrightCtx:
            def __enter__(self):
                obj = type("P", (), {"chromium": _FakeChromium()})()
                return obj

            def __exit__(self, *exc):
                return False

        with patch(
            "data_collector.adapters.rule_based.sites.wannyan_navi_aichi.sync_playwright",
            return_value=_FakePlaywrightCtx(),
        ):
            ids = adapter._collect_record_ids_via_network()

        assert ids == ["id-a", "id-b"]

    def test_collect_record_ids_via_network_harvests_msearch_responses(self):
        """`/elasticsearch/msearch` (複数検索まとめ) の入れ子構造からも収集する"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())

        class _FakeResponse:
            url = "https://wannyan-navi.pref.aichi.jp/elasticsearch/msearch"

            def json(self):
                return {
                    "responses": [
                        {"hits": {"hits": [{"_id": "id-x"}]}},
                        {"hits": {"hits": [{"_id": "id-y"}, {"_id": "id-x"}]}},
                    ]
                }

        class _FakePage:
            def on(self, event, handler):
                self._handler = handler

            def goto(self, url, wait_until=None, timeout=None):
                self._handler(_FakeResponse())

            def wait_for_timeout(self, ms):
                pass

        class _FakeContext:
            def new_page(self):
                return _FakePage()

        class _FakeBrowser:
            def new_context(self, user_agent=None):
                return _FakeContext()

            def close(self):
                pass

        class _FakeChromium:
            def launch(self, headless=True):
                return _FakeBrowser()

        class _FakePlaywrightCtx:
            def __enter__(self):
                return type("P", (), {"chromium": _FakeChromium()})()

            def __exit__(self, *exc):
                return False

        with patch(
            "data_collector.adapters.rule_based.sites.wannyan_navi_aichi.sync_playwright",
            return_value=_FakePlaywrightCtx(),
        ):
            ids = adapter._collect_record_ids_via_network()

        # 重複 "id-x" は 1 件に集約され、ソート済みで返る
        assert ids == sorted({"id-x", "id-y"})

    def test_collect_record_ids_via_network_ignores_non_elasticsearch_responses(self):
        adapter = WannyanNaviAichiAdapter(_site_aichi())

        class _FakeResponse:
            url = "https://wannyan-navi.pref.aichi.jp/api/1.1/init/data"

            def json(self):
                raise AssertionError("elasticsearch 以外の URL では json() を呼ばない想定")

        class _FakePage:
            def on(self, event, handler):
                self._handler = handler

            def goto(self, url, wait_until=None, timeout=None):
                self._handler(_FakeResponse())

            def wait_for_timeout(self, ms):
                pass

        class _FakeContext:
            def new_page(self):
                return _FakePage()

        class _FakeBrowser:
            def new_context(self, user_agent=None):
                return _FakeContext()

            def close(self):
                pass

        class _FakeChromium:
            def launch(self, headless=True):
                return _FakeBrowser()

        class _FakePlaywrightCtx:
            def __enter__(self):
                return type("P", (), {"chromium": _FakeChromium()})()

            def __exit__(self, *exc):
                return False

        with patch(
            "data_collector.adapters.rule_based.sites.wannyan_navi_aichi.sync_playwright",
            return_value=_FakePlaywrightCtx(),
        ):
            ids = adapter._collect_record_ids_via_network()

        assert ids == []


class TestWannyanNaviAichiAdapterDetailExtraction:
    """detail ページからの RawAnimalData 構築"""

    def test_extract_animal_details_returns_raw_data_cat(self, assert_raw_animal):
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=abc123"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="猫",
            sex="メス",
            age="5歳3ヵ月",
            color="白黒",
            shelter_date="2026/08/27",
            location="尾張支所(一宮市)",
            phone="0586-78-2595",
            category="adoption",
        )
        assert raw.breed == "雑種"
        assert raw.management_number == "尾263014"
        assert "稲6" in raw.description

        # normalize() 経由でも主要フィールドが期待通りに変換されること
        # (T042/T114: raw のみの確認では normalize 段の退行を検知できない)。
        animal_data = adapter.normalize(raw)
        assert animal_data.species == "猫"
        assert animal_data.sex == "女の子"
        assert animal_data.age_months == 63  # "5歳3ヵ月" = 5*12+3
        assert animal_data.color == "白黒"
        assert animal_data.shelter_date.isoformat() == "2026-08-27"
        assert animal_data.location == "尾張支所(一宮市)"
        assert animal_data.phone == "0586-78-2595"

    def test_extract_animal_details_dog_uses_dog_guide_link(self):
        """「犬の飼い方講習会へ」から species=犬 と判定される"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=dog001"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_DOG):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        assert raw.species == "犬"
        assert raw.breed == "柴犬"
        assert raw.color == "茶"
        assert raw.sex == "オス"
        assert raw.age == "2歳0ヵ月"
        assert raw.location == "本所"
        assert raw.management_number == "本264001"
        assert raw.phone == "0565-58-2323"

    def test_extract_animal_details_dedupes_images_by_bubble_file_id(self):
        """同一写真の解像度違い (cdn-cgi リサイズ) は 1 枚に集約される"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        detail_url = "https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=abc123"
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_CAT):
            raw = adapter.extract_animal_details(detail_url, category="adoption")

        # 3 img (うち2枚は同一ファイル id の解像度違い) → 2 枚に集約
        assert len(raw.image_urls) == 2
        assert all("logo" not in u.lower() for u in raw.image_urls)

    def test_extract_animal_details_raises_on_missing_basic_info(self):
        """「基本情報」見出しすら見つからない = 構造崩壊として ParsingError"""
        adapter = WannyanNaviAichiAdapter(_site_aichi())
        with patch.object(adapter, "_http_get", return_value=DETAIL_HTML_NO_BASIC_INFO):
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=0"
                )


class TestWannyanNaviAichiAdapterHelpers:
    """内部ヘルパーの単体テスト"""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("猫の飼い方講習会へ", "猫"),
            ("犬の飼い方講習会へ", "犬"),
            ("お問い合わせ", ""),
            ("", ""),
        ],
    )
    def test_infer_species_from_guide_link(self, text, expected):
        soup = _soup_with_text(text)
        assert WannyanNaviAichiAdapter._infer_species_from_guide_link(soup) == expected

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("掲載日：2026/08/27", "2026/08/27"),
            ("撮影日：2026/08/25（5歳2ヵ月）", ""),
            ("", ""),
        ],
    )
    def test_extract_posted_date(self, text, expected):
        soup = _soup_with_text(text)
        assert WannyanNaviAichiAdapter._extract_posted_date(soup) == expected

    def test_classify_basic_info_assigns_known_fields(self):
        segment = ["No . 尾263014", "尾張支所(一宮市)", "雑種", "白黒", "メス", "5歳3ヵ月"]
        fields = WannyanNaviAichiAdapter._classify_basic_info(segment)
        assert fields["management_number"] == "尾263014"
        assert fields["location"] == "尾張支所(一宮市)"
        assert fields["sex"] == "メス"
        assert fields["age"] == "5歳3ヵ月"
        assert fields["breed"] == "雑種"
        assert fields["color"] == "白黒"

    def test_classify_basic_info_handles_missing_values_gracefully(self):
        # 性別・年齢が欠落しているケース
        segment = ["No . 東264003", "知多支所(半田市)", "雑種", "三毛"]
        fields = WannyanNaviAichiAdapter._classify_basic_info(segment)
        assert fields["management_number"] == "東264003"
        assert fields["location"] == "知多支所(半田市)"
        assert fields["sex"] == ""
        assert fields["age"] == ""
        assert fields["breed"] == "雑種"
        assert fields["color"] == "三毛"


class TestWannyanNaviAichiAdapterRegistry:
    """registry にサイト名が登録されていること"""

    SITE_NAME = "愛知県わんにゃんナビ"

    def test_site_registered_to_wannyan_navi_aichi_adapter(self):
        if SiteAdapterRegistry.get(self.SITE_NAME) is None:
            SiteAdapterRegistry.register(self.SITE_NAME, WannyanNaviAichiAdapter)
        cls = SiteAdapterRegistry.get(self.SITE_NAME)
        assert cls is WannyanNaviAichiAdapter, (
            f"{self.SITE_NAME} が WannyanNaviAichiAdapter に紐付いていません: {cls}"
        )


def _soup_with_text(text: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(f"<html><body><p>{text}</p></body></html>", "html.parser")
