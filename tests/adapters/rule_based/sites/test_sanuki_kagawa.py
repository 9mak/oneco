"""SanukiKagawaAdapter のテスト

さぬき動物愛護センター（譲渡犬猫）の PDF 表を 1 頭ずつに展開する
rule-based adapter を検証する。

2026-08-06 に仕様を変更した。それまでは「PDF 1 本 = 1 頭」として登録して
おり、実際には犬40頭・猫26頭が載っている PDF が犬1件・猫1件に潰れ、しかも
中身は species と施設情報以外すべて空だった。加えて動物ではない案内チラシ
(`micro.pdf`) まで1頭として公開していた。表を行単位で読み、管理番号を持つ
行だけを 1 頭として扱う方式に改める。

- 一覧 HTML から PDF リンクを抽出 → 表の行数ぶんの仮想 URL に展開
- `source_url` は PDF 本体ではなく一覧ページ + fragment（日次差し替えで
  PDF 本体が 404 になるため。W001/T022 と同じ方針）
- 重ね書きで列が混線した値は採用せず空にする
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.playwright import PlaywrightFetchMixin
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.sanuki_kagawa import SanukiKagawaAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_LIST_URL = (
    "https://www.pref.kagawa.lg.jp/s-doubutuaigo/sanukidouaicenter/jyouto/s04u6e190311095146.html"
)


def _site() -> SiteConfig:
    """sites.yaml と同じ list_url を持つ SiteConfig"""
    return SiteConfig(
        name="さぬき動物愛護センター（譲渡犬猫）",
        prefecture="香川県",
        prefecture_code="37",
        list_url=_LIST_URL,
        category="adoption",
    )


_LIST_HTML = """
<html><body>
  <ul>
    <li><a href="/documents/6103/0805dog.pdf">譲渡候補犬</a></li>
    <li><a href="/documents/6103/0805cat.pdf">譲渡候補猫</a></li>
    <li><a href="/documents/6103/micro.pdf">マイクロチップについて</a></li>
    <li><a href="/documents/9999/other.pdf">別部署の資料</a></li>
    <li><a href="/s-doubutuaigo/index.html">トップへ戻る</a></li>
  </ul>
</body></html>
"""

# `_extract_pdf_text` が返す形（表の 1 セル = タブ区切り、1 行 = 改行区切り）。
# 実 PDF を pdfplumber の extract_tables() で読んだ構造をそのまま模している。
_DOG_PDF_TEXT = "\n".join(
    [
        "掲載日：\t2026年8月5日\t～掲載されている犬について～ ※健康状態を確認の上\t\t\t\t\t\t\t",
        "センター 管理番号\t\t推定 生年月日\t品種\t\t毛色\t性別\t大きさ\tフィラリア 検査\t特徴",
        "NEW 8中‐D0155\t\tH31.4.1\t雑種\t\t薄茶\tオス\t約12ｋｇ\t陽性\t・人懐っこい性格の子です♪",
        "5中-D0524\t\tR5.11.30\t雑種\t\tうす茶白\tオス 去勢済\t約16kg\t陰性\t・心を開いた人には尻尾ふりふり",
    ]
)

# 猫 PDF は「譲渡希望者と交渉中です。」が重ね書きされ、pdfplumber が
# x 座標順に並べると 1 文字ずつ交互に混ざる（実 PDF で確認済み）。
_CAT_PDF_TEXT = "\n".join(
    [
        "掲載日：\t2026年8月5日\t～掲載されている猫について～ ※FeLV/FIV 検査を行っています\t\t\t\t\t\t\t\t\t",
        "センター 管理番号\t\t推定 生年月日\t\t品種\t\t\t\t毛色\t性別\tFeLV FIV\t特徴",
        "8高-C0017\t\tR8.4.1\t\t譲雑渡種希\t\t\t\t\t中でオすス。\t検査 未実施\t・スタッフに懐いています",
        "8東-C0028\t\tR8.4.1\t\t雑種\t\t\t\tキジトラ\tオス\t検査 未実施\t・人懐っこい男の子です",
    ]
)

# 動物の表を持たない案内チラシ（実在の micro.pdf 相当）
_LEAFLET_PDF_TEXT = "犬や猫のマイクロチップを、既存の民間登録団体に登録している飼い主の方へ"

# 実 PDF はページごとに列数が変わる（0805dog.pdf は 10 / 9 / 11 / 10 列）。
# 1 ページ目のヘッダを全ページに使い回すと 2 ページ目以降の値がずれる。
_DOG_PDF_TEXT_MULTIPAGE = "\n".join(
    [
        "掲載日：\t2026年8月5日\t～掲載されている犬について～\t\t\t\t\t\t\t",
        "センター 管理番号\t\t推定 生年月日\t品種\t\t毛色\t性別\t大きさ\tフィラリア 検査\t特徴",
        "NEW 8中‐D0155\t\tH31.4.1\t雑種\t\t薄茶\tオス\t約12ｋｇ\t陽性\t・人懐っこい性格の子です♪",
        # ここから 2 ページ目。空列が 1 つ減って列位置が 1 つずつ手前にずれる
        "センター 管理番号\t\t推定 生年月日\t品種\t毛色\t性別\t大きさ\tフィラリア 検査\t特徴",
        "7西ーD0091\t\tR7.3.1\t雑種\t茶\tオス 去勢済\t約1６㎏\t陰性\t【トライアル可能（去勢手術済み）】",
    ]
)


def _adapter_with_pdf(pdf_texts: dict[str, str]) -> SanukiKagawaAdapter:
    """`_extract_pdf_text` を差し替えた adapter を返す

    キーは PDF ファイル名。`_download_pdf` はファイル名だけ通す stub にする。
    """
    adapter = SanukiKagawaAdapter(_site())

    def _fake_download(url: str) -> bytes:
        return url.rsplit("/", 1)[-1].encode()

    def _fake_extract(pdf_bytes: bytes) -> str:
        return pdf_texts.get(pdf_bytes.decode(), "")

    adapter._download_pdf = _fake_download  # type: ignore[method-assign]
    adapter._extract_pdf_text = _fake_extract  # type: ignore[method-assign]
    return adapter


class TestSanukiKagawaListExtraction:
    """一覧ページ → 仮想 URL 展開"""

    def test_expands_each_pdf_row_into_its_own_url(self):
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT, "0805cat.pdf": _CAT_PDF_TEXT})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            result = adapter.fetch_animal_list()

        # 犬2頭 + 猫2頭。PDF 本数(2)ではなく掲載頭数(4)になる
        assert len(result) == 4

    def test_leaflet_pdf_yields_no_animal(self):
        """動物の表を持たない案内チラシは 1 頭も生まない"""
        adapter = _adapter_with_pdf({"micro.pdf": _LEAFLET_PDF_TEXT})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            result = adapter.fetch_animal_list()

        assert all("micro.pdf" not in url for url, _ in result)

    def test_ignores_pdfs_outside_documents_6103(self):
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            result = adapter.fetch_animal_list()

        assert all("/documents/9999/" not in url for url, _ in result)

    def test_virtual_urls_are_unique(self):
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT, "0805cat.pdf": _CAT_PDF_TEXT})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            urls = [u for u, _ in adapter.fetch_animal_list()]

        assert len(urls) == len(set(urls))

    def test_returns_empty_when_no_pdf_link(self):
        adapter = _adapter_with_pdf({})
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            assert adapter.fetch_animal_list() == []

    def test_category_is_adoption(self):
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            result = adapter.fetch_animal_list()

        assert all(c == "adoption" for _, c in result)


class TestSanukiKagawaDetailExtraction:
    """PDF 表の 1 行 → RawAnimalData"""

    def test_dog_row_fills_fields(self, assert_raw_animal):
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=0"
        )

        assert isinstance(raw, RawAnimalData)
        assert_raw_animal(
            raw,
            species="犬",
            sex="オス",
            color="薄茶",
            breed="雑種",
            size="約12ｋｇ",
            management_number="8中‐D0155",
        )
        assert raw.location == "さぬき動物愛護センター"
        assert raw.phone == "087-815-2255"

    def test_dog_row_keeps_sex_when_suffixed(self, assert_raw_animal):
        """「オス 去勢済」のような接尾がついても性別を取り出す"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=1"
        )

        assert_raw_animal(raw, sex="オス", management_number="5中-D0524")

    def test_cat_row_infers_species_cat(self, assert_raw_animal):
        adapter = _adapter_with_pdf({"0805cat.pdf": _CAT_PDF_TEXT})
        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805cat.pdf#row=1"
        )

        assert_raw_animal(raw, species="猫", sex="オス", color="キジトラ", breed="雑種")

    def test_overlapped_cells_are_dropped_not_stored(self, assert_raw_animal):
        """重ね書きで混線した値は採用しない（誤情報を公開しないため）"""
        adapter = _adapter_with_pdf({"0805cat.pdf": _CAT_PDF_TEXT})
        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805cat.pdf#row=0"
        )

        # 「譲雑渡種希」「中でオすス。」は品種でも性別でもない
        assert_raw_animal(raw, species="猫", sex="", color="", breed="")
        # 壊れていない情報は残す
        assert raw.management_number == "8高-C0017"
        assert "スタッフに懐いています" in raw.description

    def test_source_url_points_to_list_page_not_pdf(self):
        """PDF 本体は日次差し替えで 404 になるため一覧ページを指す"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=0"
        )

        assert raw.source_url.startswith(_LIST_URL)
        assert not raw.source_url.split("#")[0].endswith(".pdf")
        assert "#pdf=0805dog.pdf&row=0" in raw.source_url

    def test_shelter_date_uses_publication_date(self, assert_raw_animal):
        """PDF に明記された掲載日を使う（収集日で埋めない）"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=0"
        )

        assert_raw_animal(raw, shelter_date="2026-08-05")

    def test_column_layout_is_resolved_per_page(self, assert_raw_animal):
        """ページごとに列数が変わっても値がずれない"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT_MULTIPAGE})

        first = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=0"
        )
        assert_raw_animal(first, sex="オス", color="薄茶", size="約12ｋｇ")

        second = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=1"
        )
        assert_raw_animal(
            second,
            sex="オス",
            color="茶",
            size="約1６㎏",
            management_number="7西ーD0091",
        )

    def test_header_row_is_not_counted_as_animal(self):
        """2 ページ目以降のヘッダ行を 1 頭として数えない"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT_MULTIPAGE})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            result = adapter.fetch_animal_list()

        assert len(result) == 2

    def test_row_out_of_range_raises(self):
        from data_collector.adapters.municipality_adapter import ParsingError

        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})
        with pytest.raises(ParsingError):
            adapter.extract_animal_details(
                "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=99"
            )


class TestSanukiKagawaRegistration:
    def test_registered_for_site_name(self):
        assert SiteAdapterRegistry.get("さぬき動物愛護センター（譲渡犬猫）") is SanukiKagawaAdapter

    def test_uses_playwright_for_js_list_page(self):
        assert issubclass(SanukiKagawaAdapter, PlaywrightFetchMixin)

    def test_normalize_is_available(self):
        adapter = SanukiKagawaAdapter(_site())
        assert callable(getattr(adapter, "normalize", None))
