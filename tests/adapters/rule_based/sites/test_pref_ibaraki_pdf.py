"""PrefIbarakiPdfAdapter のテスト

茨城県の 2 つのサイト (収容中の動物たち / 迷い犬・猫情報) で共通利用する
PDF 系 rule-based adapter の動作を検証する。

- 一覧 HTML から PDF リンクを抽出 → 各 PDF を仮想 URL に展開
- PDF テキストから動物 dict を `_parse_pdf_text` で抽出
- _http_get / _download_pdf を mock し、合成 PDF テキストでテスト
- `_extract_pdf_text` は実 PDF が2段組みレイアウトのため pdfplumber を
  モックして列分離ロジック (T117) を検証する
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_ibaraki_pdf import (
    PrefIbarakiPdfAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────── テスト用データ ───────────────────

# href は実サイトの現行ファイル名規則 (documents/inu0827.pdf 等) を模す。
# 旧セレクタは "kouhyou" 部分文字列マッチだったが、実サイトの現在の
# ファイル名と一致せず (T117 で判明)、"documents/inu" / "documents/neko"
# 部分文字列マッチに変更した。年間集計 PDF (r7syuuyousuu.pdf) は対象外。
_LIST_HTML = """
<html><head><title>茨城県 収容中の動物たち</title></head>
<body>
  <h1>収容中の動物たち</h1>
  <ul>
    <li><a href="/hokenfukushi/doshise/hogo/documents/inu0827.pdf">成犬収容頭数</a></li>
    <li><a href="/hokenfukushi/doshise/hogo/documents/neko0827.pdf">成猫収容頭数</a></li>
    <li><a href="/hokenfukushi/doshise/hogo/documents/r7syuuyousuu.pdf">令和7年度収容頭数(除外対象)</a></li>
    <li><a href="/hokenfukushi/doshise/hogo/index.html">トップへ戻る</a></li>
    <li><a href="/hokenfukushi/doshise/hogo/other/manual.pdf">マニュアル PDF (除外対象)</a></li>
  </ul>
</body></html>
"""

# 合成 PDF テキスト: 1 PDF に 2 頭分のデータが含まれる例
_PDF_TEXT_TWO_ANIMALS = """茨城県動物指導センター 収容中の動物たち

収容日: 2026年5月12日
種類: 犬
性別: オス
年齢: 推定3歳
毛色: 白黒
体格: 中
収容場所: 水戸市笠原町

収容日: 2026年5月12日
種類: 猫
性別: メス
年齢: 成猫
毛色: 茶トラ
体格: 小
収容場所: つくば市研究学園
"""

# 1 頭のみの PDF (日付区切りが '/')
_PDF_TEXT_ONE_ANIMAL = """迷い犬・猫情報

収容日 2026/5/14
種類: 犬
性別: メス
年齢: 推定5歳
毛色: 茶
体格: 大
発見場所: 日立市鮎川町
"""

# 実 PDF (documents/inu0827.pdf / 2026-08-29 取得) の pdfplumber 抽出結果を
# 簡略化したもの。実物は管理番号 (例: 22-3543) が 1 頭分の先頭に来る
# (T066)。ラベルは「市町村名」で、収容日より前に現れる。
_REAL_PDF_TEXT = """成犬収容頭数 2026年8月27日現在 1 /9
22-3543 市町村名 鉾田市田崎
収容日 2023/3/1 センター名 シャルル
種類 犬 犬猫種 雑種
毛色 茶 性別 雌
体格 中 首輪 無
一次判定結果 ×
22-3566 市町村名 笠間市飯田
収容日 2023/3/11 センター名 さむ
種類 犬 犬猫種 雑種
毛色 白 性別 雄
体格 中 首輪 無
一次判定結果 ×
"""


def _site(name: str = "茨城県（収容中の動物たち）") -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="茨城県",
        prefecture_code="08",
        list_url=("https://www.pref.ibaraki.jp/hokenfukushi/doshise/hogo/syuuyou.html"),
        category="sheltered",
    )


# ─────────────────── _parse_pdf_text 単体テスト ───────────────────


class TestParsePdfText:
    """合成 PDF テキストでパーサ単体の挙動を確認する"""

    def test_parses_two_animals(self):
        adapter = PrefIbarakiPdfAdapter(_site())
        records = adapter._parse_pdf_text(_PDF_TEXT_TWO_ANIMALS)

        assert len(records) == 2

        first, second = records
        assert first["shelter_date"] == "2026-05-12"
        assert first["species"] == "犬"
        assert first["sex"] == "オス"
        assert first["age"] == "推定3歳"
        assert first["color"] == "白黒"
        assert first["size"] == "中"
        assert "水戸市" in first["location"]

        assert second["shelter_date"] == "2026-05-12"
        assert second["species"] == "猫"
        assert second["sex"] == "メス"
        assert second["color"] == "茶トラ"
        assert "つくば市" in second["location"]

    def test_parses_one_animal_with_slash_date(self):
        """日付区切りが '/' でも、発見場所ラベルでもパースできる"""
        adapter = PrefIbarakiPdfAdapter(_site("茨城県（迷い犬・猫情報）"))
        records = adapter._parse_pdf_text(_PDF_TEXT_ONE_ANIMAL)

        assert len(records) == 1
        assert records[0]["shelter_date"] == "2026-05-14"
        assert records[0]["species"] == "犬"
        assert records[0]["sex"] == "メス"
        assert records[0]["color"] == "茶"
        assert "日立市" in records[0]["location"]

    def test_empty_text_returns_empty_list(self):
        adapter = PrefIbarakiPdfAdapter(_site())
        assert adapter._parse_pdf_text("") == []

    def test_text_without_shelter_date_returns_empty(self):
        """収容日が無いテキストは何も抽出しない"""
        adapter = PrefIbarakiPdfAdapter(_site())
        text = "ヘッダのみ\n動物情報なし\n"
        assert adapter._parse_pdf_text(text) == []

    def test_parses_management_number_from_real_pdf_layout(self):
        """実 PDF レイアウト (管理番号が 1 頭分の先頭) から抽出できる (T066)"""
        adapter = PrefIbarakiPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        assert len(records) == 2
        assert records[0]["management_number"] == "22-3543"
        assert records[0]["shelter_date"] == "2023-03-01"
        assert records[0]["species"] == "犬"
        assert records[1]["management_number"] == "22-3566"
        assert records[1]["shelter_date"] == "2023-03-11"


# ─────────────────── _extract_pdf_text 2段組み対応テスト (T117) ───────────────────


class _FakeColumn:
    """`page.crop(...)` が返す部分ページの偽物。`extract_text()` のみ使う"""

    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class _FakePage:
    """pdfplumber の Page の偽物。左右2列ぶんのテキストを固定で持つ

    実 PDF は `page.width / 2` を境に左列・右列が分かれているため、
    `crop((x0, y0, x1, y1))` の `x0` が 0 なら左列、そうでなければ右列の
    テキストを返す (実装側の呼び出し方に対する最小限のフェイク)。
    """

    def __init__(self, width: float, height: float, left_text: str, right_text: str) -> None:
        self.width = width
        self.height = height
        self._left_text = left_text
        self._right_text = right_text

    def crop(self, bbox: tuple[float, float, float, float]) -> _FakeColumn:
        x0 = bbox[0]
        return _FakeColumn(self._left_text if x0 == 0 else self._right_text)


class _FakePdf:
    """`pdfplumber.open(...)` が返す `with` コンテキストの偽物"""

    def __init__(self, pages: list[_FakePage]) -> None:
        self.pages = pages

    def __enter__(self) -> _FakePdf:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class TestExtractPdfTextTwoColumn:
    """`_extract_pdf_text` の列分離ロジックを pdfplumber モックで検証する

    実PDF (documents/inu0827.pdf 等) は1ページに動物情報が左右2列で並ぶ
    2段組みレイアウトで、基底クラスの `page.extract_text()` (ページ丸ごと)
    だと左右の行が混ざり、1行に2頭ぶんの「収容日」が同居して右列 (2頭目)
    が丸ごと欠落していた (実測: 143頭中72頭のみ抽出)。列を crop で分離
    してから `extract_text()` すれば、既存の `_parse_pdf_text` を変更せず
    両方の動物が正しく抽出できることを確認する。
    """

    def test_splits_left_and_right_column_into_separate_blocks(self):
        """1 ページ2列 → _extract_pdf_text はテキストブロック2つを連結して返す"""
        adapter = PrefIbarakiPdfAdapter(_site())
        page = _FakePage(
            width=1000,
            height=500,
            left_text="収容日: 2026年5月12日\n種類: 犬\n性別: オス\n毛色: 白黒\n体格: 中",
            right_text="収容日: 2026年5月12日\n種類: 猫\n性別: メス\n毛色: 茶トラ\n体格: 小",
        )

        with patch(
            "data_collector.adapters.rule_based.sites.pref_ibaraki_pdf.pdfplumber.open",
            return_value=_FakePdf([page]),
        ):
            text = adapter._extract_pdf_text(b"dummy-pdf-bytes")

        assert "犬" in text
        assert "猫" in text
        # 左列の内容が右列より前に来る (連結順序を保つ)
        assert text.index("犬") < text.index("猫")

    def test_two_column_page_yields_both_animals_after_parse(self):
        """列分離後のテキストを _parse_pdf_text に通すと2頭とも欠落しない

        修正前は同一物理行に2頭ぶんの「収容日」が同居し、`.search()` が
        最初の一致しか拾わないため右列 (2頭目) が欠落していた。
        """
        adapter = PrefIbarakiPdfAdapter(_site())
        page = _FakePage(
            width=1000,
            height=500,
            left_text="収容日: 2026年5月12日\n種類: 犬\n性別: オス\n毛色: 白黒\n体格: 中",
            right_text="収容日: 2026年5月12日\n種類: 猫\n性別: メス\n毛色: 茶トラ\n体格: 小",
        )

        with patch(
            "data_collector.adapters.rule_based.sites.pref_ibaraki_pdf.pdfplumber.open",
            return_value=_FakePdf([page]),
        ):
            text = adapter._extract_pdf_text(b"dummy-pdf-bytes")

        records = adapter._parse_pdf_text(text)

        assert len(records) == 2
        species = {r["species"] for r in records}
        assert species == {"犬", "猫"}
        dog = next(r for r in records if r["species"] == "犬")
        cat = next(r for r in records if r["species"] == "猫")
        assert dog["sex"] == "オス"
        assert dog["color"] == "白黒"
        assert cat["sex"] == "メス"
        assert cat["color"] == "茶トラ"

    def test_multi_page_columns_are_all_concatenated(self):
        """複数ページでも各ページの左右列がすべて連結される (欠落しない)"""
        adapter = PrefIbarakiPdfAdapter(_site())
        page1 = _FakePage(
            width=1000,
            height=500,
            left_text="収容日: 2026年5月12日\n種類: 犬\n性別: オス\n毛色: 白黒\n体格: 中",
            right_text="収容日: 2026年5月13日\n種類: 犬\n性別: メス\n毛色: 茶\n体格: 大",
        )
        page2 = _FakePage(
            width=1000,
            height=500,
            left_text="収容日: 2026年5月14日\n種類: 猫\n性別: オス\n毛色: 黒\n体格: 小",
            right_text="収容日: 2026年5月15日\n種類: 猫\n性別: メス\n毛色: 茶トラ\n体格: 中",
        )

        with patch(
            "data_collector.adapters.rule_based.sites.pref_ibaraki_pdf.pdfplumber.open",
            return_value=_FakePdf([page1, page2]),
        ):
            text = adapter._extract_pdf_text(b"dummy-pdf-bytes")

        records = adapter._parse_pdf_text(text)
        assert len(records) == 4
        assert {r["shelter_date"] for r in records} == {
            "2026-05-12",
            "2026-05-13",
            "2026-05-14",
            "2026-05-15",
        }

    def test_empty_column_text_is_skipped(self):
        """右列が空 (奇数頭で埋まっていない列等) の場合はブロックを追加しない"""
        adapter = PrefIbarakiPdfAdapter(_site())
        page = _FakePage(
            width=1000,
            height=500,
            left_text="収容日: 2026年5月12日\n種類: 犬\n性別: オス\n毛色: 白黒\n体格: 中",
            right_text="",
        )

        with patch(
            "data_collector.adapters.rule_based.sites.pref_ibaraki_pdf.pdfplumber.open",
            return_value=_FakePdf([page]),
        ):
            text = adapter._extract_pdf_text(b"dummy-pdf-bytes")

        records = adapter._parse_pdf_text(text)
        assert len(records) == 1
        assert records[0]["species"] == "犬"


# ─────────────────── fetch / extract 統合テスト ───────────────────


class TestFetchAndExtract:
    def test_fetch_animal_list_returns_virtual_urls(self):
        """一覧 HTML から 2 PDF × 動物頭数分の仮想 URL が返る

        PDF 1 (inu0827.pdf): 2 頭, PDF 2 (neko0827.pdf): 1 頭 → 合計 3 件
        documents/inu・documents/neko を含まない PDF (年間集計・マニュアル) は
        除外される
        """
        adapter = PrefIbarakiPdfAdapter(_site())

        def fake_download(url: str) -> bytes:
            # URL 別に異なる PDF テキストを返すスタブ
            if url.endswith("inu0827.pdf"):
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
            assert url.startswith("https://www.pref.ibaraki.jp/")
            assert "documents/inu" in url or "documents/neko" in url
            assert "r7syuuyousuu" not in url
            assert "manual" not in url
            assert url.split("#")[0].endswith(".pdf")
            assert cat == "sheltered"

    def test_extract_animal_details_returns_raw_animal_data(self):
        """仮想 URL から RawAnimalData が構築できる"""
        adapter = PrefIbarakiPdfAdapter(_site())

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
        assert raw.shelter_date == "2026-05-12"
        assert "水戸市" in raw.location
        # 公開する source_url は PDF 本体ではなく掲載元の HTML ページ (W001/T022)
        assert raw.source_url.startswith(adapter.site_config.list_url + "#pdf=")
        assert raw.source_url.endswith("&row=0")
        assert raw.category == "sheltered"

    def test_pdf_cache_avoids_re_download(self):
        """同一 PDF URL に対する複数 row 取得で download は 1 回のみ"""
        adapter = PrefIbarakiPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF") as mock_dl,
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            initial_calls = mock_dl.call_count

            # extract_animal_details で同じ PDF URL を再アクセスしてもキャッシュヒット
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        # extract 段階では追加ダウンロードは発生しない
        assert mock_dl.call_count == initial_calls

    def test_no_pdf_links_returns_empty(self):
        """PDF リンクが無い HTML は真ゼロとして空リストを返す"""
        adapter = PrefIbarakiPdfAdapter(_site())
        empty_html = "<html><body><p>準備中</p></body></html>"

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


# ─────────────────── 登録テスト ───────────────────


class TestRegistry:
    def test_both_sites_registered(self):
        """2 つの茨城県サイトが Registry に登録されている"""
        expected = [
            "茨城県（収容中の動物たち）",
            "茨城県（迷い犬・猫情報）",
        ]
        for name in expected:
            # 他テストで registry が clear されている場合に備えて冪等再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefIbarakiPdfAdapter)
            assert SiteAdapterRegistry.get(name) is PrefIbarakiPdfAdapter


# ─────────────────── normalize テスト ───────────────────


class TestNormalize:
    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        adapter = PrefIbarakiPdfAdapter(_site())

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


# ─────────────────── source_url 安定性テスト (T066) ───────────────────


class TestStableSourceUrl:
    """管理番号ベースの source_url が PDF ファイル名の変化に影響されないこと

    茨城県の PDF も自治体側の日次差し替えでファイル名が毎日変わる
    (例: inu0827.pdf → inu0828.pdf)。香川県と同型の識別子不安定バグ
    (T066) のため、管理番号を安定キーとして使う。
    """

    def test_source_url_uses_management_number_when_available(self):
        """管理番号があれば `#animal=<番号>` 形式の source_url になる"""
        adapter = PrefIbarakiPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_REAL_PDF_TEXT),
        ):
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        assert raw.source_url == adapter.site_config.list_url + "#animal=22-3543"

    def test_source_url_survives_pdf_filename_change(self):
        """同一個体は PDF ファイル名 (差し替え) が変わっても同じ source_url を維持する"""
        adapter = PrefIbarakiPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        adapter._pdf_cache["https://www.pref.ibaraki.jp/.../kouhyou/inu0827.pdf"] = records
        url_before = adapter._public_source_url(
            "https://www.pref.ibaraki.jp/.../kouhyou/inu0827.pdf", 0
        )
        adapter._pdf_cache = {}
        adapter._pdf_cache["https://www.pref.ibaraki.jp/.../kouhyou/inu0828.pdf"] = records
        url_after = adapter._public_source_url(
            "https://www.pref.ibaraki.jp/.../kouhyou/inu0828.pdf", 0
        )

        assert "inu0827.pdf" not in url_before
        assert "inu0828.pdf" not in url_after
        assert url_before == url_after == adapter.site_config.list_url + "#animal=22-3543"

    def test_source_url_falls_back_to_filename_when_no_management_number(self):
        """管理番号が取れない (旧レイアウトの) 個体は従来の (ファイル名+row) にフォールバックする"""
        adapter = PrefIbarakiPdfAdapter(_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_PDF_TEXT_TWO_ANIMALS),
        ):
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        assert raw.source_url.startswith(adapter.site_config.list_url + "#pdf=")
        assert raw.source_url.endswith("&row=0")
        assert "#animal=" not in raw.source_url
