"""CityOkazakiPdfAdapter のテスト

岡崎市保護動物 PDF 用 rule-based adapter を検証する。
- 一覧 HTML から PDF リンクを抽出 → 各 PDF を仮想 URL に展開
- PDF テキストから動物 dict を `_parse_pdf_text` で抽出
- _http_get / _download_pdf / _extract_pdf_text を mock して検証
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_okazaki_pdf import (
    CityOkazakiPdfAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────── テスト用データ ───────────────────

_LIST_HTML = """
<html><head><title>岡崎市 保護動物情報</title></head>
<body>
  <h1>保護動物情報</h1>
  <ul>
    <li><a href="/material/files/group/45/hogo_20260508.pdf">2026年5月8日保護分</a></li>
    <li><a href="/material/files/group/45/hogo_20260514.pdf">2026年5月14日保護分</a></li>
    <li><a href="/1100/1107/1149/index.html">トップへ戻る</a></li>
  </ul>
</body></html>
"""

_PDF_TEXT_TWO_ANIMALS = """岡崎市 保護動物情報

保護日: 2026年5月8日
種類: 犬
性別: オス
年齢: 推定3歳
毛色: 黒白
体格: 中
保護場所: 岡崎市康生通

保護日: 2026年5月8日
種類: 猫
性別: メス
年齢: 成猫
毛色: 三毛
体格: 小
保護場所: 岡崎市六供町
"""

_PDF_TEXT_ONE_ANIMAL = """保護動物情報

保護日 2026/5/14
種類: 犬
性別: メス
年齢: 推定6歳
毛色: 茶
体格: 大
保護場所: 岡崎市美合町
"""


def _site(name: str = "岡崎市（保護動物）") -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="愛知県",
        prefecture_code="23",
        list_url="https://www.city.okazaki.lg.jp/1100/1107/1149/p008181.html",
        category="sheltered",
    )


# ─────────────────── _parse_pdf_text 単体テスト ───────────────────


class TestParsePdfText:
    def test_parses_two_animals(self):
        adapter = CityOkazakiPdfAdapter(_site())
        records = adapter._parse_pdf_text(_PDF_TEXT_TWO_ANIMALS)

        assert len(records) == 2

        first, second = records
        assert first["shelter_date"] == "2026-05-08"
        assert first["species"] == "犬"
        assert first["sex"] == "オス"
        assert first["age"] == "推定3歳"
        assert first["color"] == "黒白"
        assert first["size"] == "中"
        assert "岡崎市" in first["location"]

        assert second["shelter_date"] == "2026-05-08"
        assert second["species"] == "猫"
        assert second["sex"] == "メス"
        assert second["color"] == "三毛"
        assert "岡崎市" in second["location"]

    def test_parses_one_animal_with_slash_date(self):
        adapter = CityOkazakiPdfAdapter(_site())
        records = adapter._parse_pdf_text(_PDF_TEXT_ONE_ANIMAL)

        assert len(records) == 1
        assert records[0]["shelter_date"] == "2026-05-14"
        assert records[0]["species"] == "犬"
        assert records[0]["sex"] == "メス"
        assert records[0]["color"] == "茶"
        assert "岡崎市" in records[0]["location"]

    def test_empty_text_returns_empty_list(self):
        adapter = CityOkazakiPdfAdapter(_site())
        assert adapter._parse_pdf_text("") == []

    def test_text_without_shelter_date_returns_empty(self):
        adapter = CityOkazakiPdfAdapter(_site())
        text = "ヘッダのみ\n動物情報なし\n"
        assert adapter._parse_pdf_text(text) == []


# ─────────────────── fetch / extract 統合テスト ───────────────────


class TestFetchAndExtract:
    def test_fetch_animal_list_returns_virtual_urls(self):
        """PDF 1: 2 頭, PDF 2: 1 頭 → 合計 3 件"""
        adapter = CityOkazakiPdfAdapter(_site())

        def fake_download(url: str) -> bytes:
            if url.endswith("hogo_20260508.pdf"):
                return b"PDF1"
            return b"PDF2"

        def fake_extract(pdf_bytes: bytes) -> str:
            if pdf_bytes == b"PDF1":
                return _PDF_TEXT_TWO_ANIMALS
            return _PDF_TEXT_ONE_ANIMAL

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", side_effect=fake_download),
            patch.object(adapter, "_extract_pdf_text", side_effect=fake_extract),
        ):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.city.okazaki.lg.jp/")
            assert url.split("#")[0].endswith(".pdf")
            assert cat == "sheltered"

    def test_extract_animal_details_returns_raw_animal_data(self):
        adapter = CityOkazakiPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.age == "推定3歳"
        assert raw.color == "黒白"
        assert raw.size == "中"
        assert raw.shelter_date == "2026-05-08"
        assert "岡崎市" in raw.location
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_pdf_cache_avoids_re_download(self):
        adapter = CityOkazakiPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF") as mock_dl,
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            initial_calls = mock_dl.call_count

            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_dl.call_count == initial_calls

    def test_no_pdf_links_returns_empty(self):
        adapter = CityOkazakiPdfAdapter(_site())
        empty_html = "<html><body><p>準備中</p></body></html>"

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


# ─────────────────── 登録テスト ───────────────────


class TestRegistry:
    def test_site_registered(self):
        name = "岡崎市（保護動物）"
        if SiteAdapterRegistry.get(name) is None:
            SiteAdapterRegistry.register(name, CityOkazakiPdfAdapter)
        assert SiteAdapterRegistry.get(name) is CityOkazakiPdfAdapter


# ─────────────────── normalize テスト ───────────────────


class TestNormalize:
    def test_normalize_returns_animal_data(self):
        adapter = CityOkazakiPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")


# 実 PDF (岡崎市 hogo.pdf / 2026-08-03 取得) の pdfplumber 抽出結果。
# 上の合成データと違い、実物はラベル付きの縦並びではなく **表** で、
#   1 行目: 見出し「保護動物情報 犬 2026年4月5日 現在」(species と年はここだけ)
#   2 行目: 表ヘッダ「管理番号/写真/保護場所/保護月日/種類/毛色/性別/体格/首輪/その他特徴」
#   3 行目以降: 1 頭 = 1 行。「保護月日」は年を持たない (4月3日)
# という形をしている。extract_text だと毛色が前後行へ割れる (猫 PDF の
# 「白黒 / （はちわれ）」) ため、表として読む必要がある。
_REAL_PAGE_TEXT_DOG = "保護動物情報 犬 2026年4月5日 現在"
_REAL_TABLE_DOG = [
    [
        "管理番号",
        "写真",
        "保護場所",
        "保護月日",
        "種類",
        "毛色",
        "性別",
        "体格",
        "首輪",
        "その他特徴",
    ],
    ["1055-1", "", "大代町", "4月3日", "推定ピットブル", "茶", "♀", "大型", "無", ""],
]
_REAL_PAGE_TEXT_CAT = "保護動物情報 猫 2025年5月12日 現在"
_REAL_TABLE_CAT = [
    [
        "管理番号",
        "写真",
        "保護場所",
        "保護月日",
        "種類",
        "毛色",
        "性別",
        "体格",
        "首輪",
        "その他特徴",
    ],
    ["1060-1", "", "鴨田町", "5月9日", "雑種", "白黒\n（はちわれ）", "♀", "中", "無", "削痩、衰弱"],
]


class TestRealPdfTableLayout:
    """実 PDF (表形式) を構造化テキストへ変換してからパースする"""

    def _records(self, tables, page_text):
        adapter = CityOkazakiPdfAdapter(_site())
        text = adapter._tables_to_labeled_text(tables, page_text)
        return adapter._parse_pdf_text(text)

    def test_dog_table_yields_one_animal(self):
        records = self._records([_REAL_TABLE_DOG], _REAL_PAGE_TEXT_DOG)
        assert len(records) == 1

    def test_species_comes_from_heading_not_breed_column(self):
        """species は見出しの「犬」。表の「種類」列は品種として保存する"""
        records = self._records([_REAL_TABLE_DOG], _REAL_PAGE_TEXT_DOG)
        assert records[0]["species"] == "犬"
        assert records[0]["breed"] == "推定ピットブル"

    def test_shelter_date_combines_heading_year_with_month_day(self):
        """年を持たない「保護月日 4月3日」に見出しの年 (2026) を補う"""
        records = self._records([_REAL_TABLE_DOG], _REAL_PAGE_TEXT_DOG)
        assert records[0]["shelter_date"] == "2026-04-03"

    def test_extracts_remaining_columns(self):
        records = self._records([_REAL_TABLE_DOG], _REAL_PAGE_TEXT_DOG)
        r = records[0]
        assert r["color"] == "茶"
        assert r["sex"] == "♀"
        assert r["size"] == "大型"
        assert r["location"] == "大代町"
        assert r["management_number"] == "1055-1"

    def test_multiline_cell_is_flattened(self):
        """セル内改行 (「白黒\\n（はちわれ）」) を 1 つの値として扱う"""
        records = self._records([_REAL_TABLE_CAT], _REAL_PAGE_TEXT_CAT)
        assert len(records) == 1
        assert records[0]["color"] == "白黒（はちわれ）"
        assert records[0]["species"] == "猫"
        assert records[0]["shelter_date"] == "2025-05-09"

    def test_header_only_table_yields_nothing(self):
        """データ行が無い表 (収容ゼロ) では 0 件"""
        records = self._records([[_REAL_TABLE_DOG[0]]], _REAL_PAGE_TEXT_DOG)
        assert records == []
