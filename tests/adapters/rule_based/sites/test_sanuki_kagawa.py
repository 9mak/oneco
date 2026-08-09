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

# ヘッダのセル分割で「管理番号」が連結しても一致しなくなるケース。
# 2026-08-07 の本番収集では犬42件のうち size が入ったのは row=0 と row=36〜41
# の7件だけで、1ページ目の列位置が正解となる行に偏っていた。同じ PDF を同じ
# adapter・同じ pdfplumber(0.11.10)/pdfminer.six(20260107) でローカル実行すると
# 42/42 取得できるため本番固有の要因が残っているが、いずれにせよヘッダを
# 見失った時点で列位置に依存する値が落ちる構造自体は塞いでおく。
_DOG_PDF_TEXT_HEADER_NOT_DETECTED = "\n".join(
    [
        "掲載日：\t2026年8月5日\t～掲載されている犬について～\t\t\t\t\t\t\t",
        "センター 管理番号\t\t推定 生年月日\t品種\t\t毛色\t性別\t大きさ\tフィラリア 検査\t特徴",
        "NEW 8中‐D0155\t\tH31.4.1\t雑種\t\t薄茶\tオス\t約12ｋｇ\t陽性\t・人懐っこい性格の子です♪",
        # 2 ページ目のヘッダは「管理」「番号」がセル分割され、連結しても
        # 「管理番号」に一致しない → ヘッダとして検出されず前ページの列位置が残る
        "センター\t管理 番号\t推定 生年月日\t品種\t毛色\t性別\t大きさ\tフィラリア 検査\t特徴",
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
            size="中型",
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
        assert_raw_animal(first, sex="オス", color="薄茶", size="中型")

        second = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=1"
        )
        assert_raw_animal(
            second,
            sex="オス",
            color="茶",
            size="大型",
            management_number="7西ーD0091",
        )

    def test_size_falls_back_to_row_scan_when_header_is_lost(self, assert_raw_animal):
        """ヘッダを見失って列位置がずれても size は行全体から復元する

        「約N kg」は体重にしか現れない形なので、列を特定できなくても行から
        拾い直せる。sex / color / breed は他の列の値と紛れうるため対象にしない。
        """
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT_HEADER_NOT_DETECTED})

        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=1"
        )

        assert_raw_animal(raw, size="大型", management_number="7西ーD0091")

    def test_size_prefers_column_value_over_row_scan(self, assert_raw_animal):
        """列から取れているときは行スキャンで上書きしない"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT})

        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=0"
        )

        assert_raw_animal(raw, size="中型")

    def test_size_stays_empty_when_row_has_no_weight(self, assert_raw_animal):
        """行のどこにも体重表記が無ければ空のままにする（猫 PDF に大きさ列は無い）"""
        adapter = _adapter_with_pdf({"0805cat.pdf": _CAT_PDF_TEXT})

        raw = adapter.extract_animal_details(
            "https://www.pref.kagawa.lg.jp/documents/6103/0805cat.pdf#row=1"
        )

        assert_raw_animal(raw, species="猫", size="")

    def test_header_row_is_not_counted_as_animal(self):
        """2 ページ目以降のヘッダ行を 1 頭として数えない"""
        adapter = _adapter_with_pdf({"0805dog.pdf": _DOG_PDF_TEXT_MULTIPAGE})
        with patch.object(adapter, "_http_get", return_value=_LIST_HTML):
            result = adapter.fetch_animal_list()

        assert len(result) == 2


class TestSanukiKagawaNormalizedSize:
    """`normalize()` を通した AnimalData で size を検証する

    2026-08-08 の検証で判明した事故の再発防止。PR #269 では
    `extract_animal_details` の戻り値 (RawAnimalData) だけをアサートしており、
    adapter 段で 42/42 取れていることを「本番でのみ落ちる原因不明の問題」と
    誤って結論づけた。実際は `DataNormalizer._cap_size` が「体格語が無く体重
    情報のみなら size ではない」として捨てており、DB 段では 7/42 だった。
    CLAUDE.md「新規 adapter テストは adapter.normalize(raw) の戻り値
    AnimalData でアサーションする」に反していたのが原因。
    """

    def _normalized(self, pdf_texts: dict[str, str], url: str):
        adapter = _adapter_with_pdf(pdf_texts)
        return adapter.normalize(adapter.extract_animal_details(url))

    def test_weight_survives_normalize_as_size_class(self):
        """体重は体格語に変換され、normalize を通しても残る

        生の「約12ｋｇ」のままだと `_cap_size` に捨てられて None になる。
        """
        animal = self._normalized(
            {"0805dog.pdf": _DOG_PDF_TEXT},
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=0",
        )

        assert animal.size == "中型"

    def test_half_width_kg_also_survives_normalize(self):
        """半角 kg 表記も体格語になる（生値だと `_cap_size` に捨てられていた）"""
        animal = self._normalized(
            {"0805dog.pdf": _DOG_PDF_TEXT},
            "https://www.pref.kagawa.lg.jp/documents/6103/0805dog.pdf#row=1",
        )

        # 「約16kg」→ 15kg 以上なので大型
        assert animal.size == "大型"

    def test_cat_without_size_column_is_none_after_normalize(self):
        """猫 PDF は「大きさ」列を持たないので normalize 後も None"""
        animal = self._normalized(
            {"0805cat.pdf": _CAT_PDF_TEXT},
            "https://www.pref.kagawa.lg.jp/documents/6103/0805cat.pdf#row=1",
        )

        assert animal.size is None

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
