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
