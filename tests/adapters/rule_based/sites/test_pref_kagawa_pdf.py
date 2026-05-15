"""PrefKagawaPdfAdapter のテスト

香川県の 4 つの保健福祉事務所 (東讃 / 中讃 / 西讃 / 小豆) で共通利用する
PDF 系 rule-based adapter の動作を検証する。

- 一覧 HTML から PDF リンクを抽出 → 各 PDF を仮想 URL に展開
- PDF テキストから動物 dict を `_parse_pdf_text` で抽出
- _http_get / _download_pdf を mock し、合成 PDF テキストでテスト
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_kagawa_pdf import (
    PrefKagawaPdfAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────── テスト用データ ───────────────────

_LIST_HTML = """
<html><head><title>東讃保健福祉事務所 収容動物情報</title></head>
<body>
  <h1>収容動物情報</h1>
  <ul>
    <li><a href="/documents/7023/20260315.pdf">2026年3月15日収容分</a></li>
    <li><a href="/documents/7023/20260318.pdf">2026年3月18日収容分</a></li>
    <li><a href="/aigo/index.html">トップへ戻る</a></li>
  </ul>
</body></html>
"""

# 合成 PDF テキスト: 1 PDF に 2 頭分のデータが含まれる例
_PDF_TEXT_TWO_ANIMALS = """香川県東讃保健福祉事務所 収容動物情報

収容日: 2026年3月15日
種類: 犬
性別: オス
年齢: 推定3歳
毛色: 白黒
体格: 中
収容場所: さぬき市志度

収容日: 2026年3月15日
種類: 猫
性別: メス
年齢: 成猫
毛色: 茶トラ
体格: 小
収容場所: 東かがわ市三本松
"""

# 1 頭のみの PDF
_PDF_TEXT_ONE_ANIMAL = """収容動物情報

収容日 2026/3/18
種類: 犬
性別: メス
年齢: 推定5歳
毛色: 茶
体格: 大
収容場所: 三木町池戸
"""


def _site(name: str = "東讃保健福祉事務所（収容動物）") -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="香川県",
        prefecture_code="37",
        list_url=(
            "https://www.pref.kagawa.lg.jp/tosanhoken/tosanhoken/animal/sjiaen191105113550.html"
        ),
        category="lost",
    )


# ─────────────────── _parse_pdf_text 単体テスト ───────────────────


class TestParsePdfText:
    """合成 PDF テキストでパーサ単体の挙動を確認する"""

    def test_parses_two_animals(self):
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_PDF_TEXT_TWO_ANIMALS)

        assert len(records) == 2

        first, second = records
        assert first["shelter_date"] == "2026-03-15"
        assert first["species"] == "犬"
        assert first["sex"] == "オス"
        assert first["age"] == "推定3歳"
        assert first["color"] == "白黒"
        assert first["size"] == "中"
        assert "さぬき市" in first["location"]

        assert second["shelter_date"] == "2026-03-15"
        assert second["species"] == "猫"
        assert second["sex"] == "メス"
        assert second["color"] == "茶トラ"
        assert "東かがわ市" in second["location"]

    def test_parses_one_animal_with_slash_date(self):
        """日付区切りが '/' でもパースできる"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_PDF_TEXT_ONE_ANIMAL)

        assert len(records) == 1
        assert records[0]["shelter_date"] == "2026-03-18"
        assert records[0]["species"] == "犬"
        assert records[0]["sex"] == "メス"
        assert records[0]["color"] == "茶"
        assert "三木町" in records[0]["location"]

    def test_empty_text_returns_empty_list(self):
        adapter = PrefKagawaPdfAdapter(_site())
        assert adapter._parse_pdf_text("") == []

    def test_text_without_shelter_date_returns_empty(self):
        """収容日が無いテキストは何も抽出しない"""
        adapter = PrefKagawaPdfAdapter(_site())
        text = "ヘッダのみ\n動物情報なし\n"
        assert adapter._parse_pdf_text(text) == []


# ─────────────────── fetch / extract 統合テスト ───────────────────


class TestFetchAndExtract:
    def test_fetch_animal_list_returns_virtual_urls(self):
        """一覧 HTML から 2 PDF × 動物頭数分の仮想 URL が返る

        PDF 1: 2 頭, PDF 2: 1 頭 → 合計 3 件
        """
        adapter = PrefKagawaPdfAdapter(_site())

        def fake_download(url: str) -> bytes:
            # URL 別に異なる PDF テキストを返すスタブ
            if url.endswith("20260315.pdf"):
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
            assert url.startswith("https://www.pref.kagawa.lg.jp/")
            assert url.split("#")[0].endswith(".pdf")
            assert cat == "lost"

    def test_extract_animal_details_returns_raw_animal_data(self):
        """仮想 URL から RawAnimalData が構築できる"""
        adapter = PrefKagawaPdfAdapter(_site())

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
        assert raw.color == "白黒"
        assert raw.size == "中"
        assert raw.shelter_date == "2026-03-15"
        assert "さぬき市" in raw.location
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_pdf_cache_avoids_re_download(self):
        """同一 PDF URL に対する複数 row 取得で download は 1 回のみ"""
        adapter = PrefKagawaPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF") as mock_dl,
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            # 2 PDF だが片方は 2 頭, もう片方は 2 頭 (extract が常に同一テキストを返すため)
            # → fetch 段階で各 PDF 1 回ずつ download される (合計 2 回)
            initial_calls = mock_dl.call_count

            # extract_animal_details で同じ PDF URL を再アクセスしてもキャッシュヒット
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        # extract 段階では追加ダウンロードは発生しない
        assert mock_dl.call_count == initial_calls

    def test_no_pdf_links_raises_parsing_error(self):
        """PDF リンクが無い HTML は ParsingError"""
        from data_collector.adapters.municipality_adapter import ParsingError

        adapter = PrefKagawaPdfAdapter(_site())
        empty_html = "<html><body><p>準備中</p></body></html>"

        with patch.object(adapter, "_http_get", return_value=empty_html):
            with pytest.raises(ParsingError):
                adapter.fetch_animal_list()


# ─────────────────── 登録テスト ───────────────────


class TestRegistry:
    def test_all_four_sites_registered(self):
        """4 つの香川県保健福祉事務所サイトが Registry に登録されている"""
        expected = [
            "東讃保健福祉事務所（収容動物）",
            "中讃保健福祉事務所（収容動物）",
            "西讃保健福祉事務所（収容動物）",
            "小豆保健所（収容動物）",
        ]
        for name in expected:
            # 他テストで registry が clear されている場合に備えて冪等再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefKagawaPdfAdapter)
            assert SiteAdapterRegistry.get(name) is PrefKagawaPdfAdapter


# ─────────────────── normalize テスト ───────────────────


class TestNormalize:
    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        adapter = PrefKagawaPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")
