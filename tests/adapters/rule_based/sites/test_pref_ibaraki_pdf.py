"""PrefIbarakiPdfAdapter のテスト

茨城県の 2 つのサイト (収容中の動物たち / 迷い犬・猫情報) で共通利用する
PDF 系 rule-based adapter の動作を検証する。

- 一覧 HTML から PDF リンクを抽出 → 各 PDF を仮想 URL に展開
- PDF テキストから動物 dict を `_parse_pdf_text` で抽出
- _http_get / _download_pdf を mock し、合成 PDF テキストでテスト
- `_extract_pdf_text` は実 PDF が2段組みレイアウトのため pdfplumber を
  モックして列分離ロジック (T117) を検証する

T119 (2026-08-31): 「迷い犬・猫情報」は旧 list_url (mayoiinuneko.html) が
ハブページ化し PDF リンク0件になっていたため kouji.html (documents/
kouhyou*.pdf) へ変更した。実 PDF を確認した結果、「収容中の動物たち」とは
「種類」「犬猫種」ラベルの意味が入れ替わっている (前者は種類=品種・
犬猫種=動物種別、後者は種類=動物種別・犬猫種=品種) ことが判明したため、
それを踏まえた `_REAL_LOST_PDF_TEXT` 系フィクスチャを追加している
(実際に `documents/kouhyou0828.pdf` 等をダウンロードして pdfplumber で
抽出したテキストを基にしている)。
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

# 実 PDF (documents/kouhyou0828.pdf / 2026-08-31 取得) の pdfplumber 抽出
# 結果そのもの (T119)。「収容中の動物たち」とはラベルの意味が逆転しており、
# 「種類」が品種 (柴犬・雑種)、「犬猫種」が動物種別 (犬・猫)。ラベルは
# 「市町村地区名」(「収容中の動物たち」の「市町村名」より2文字長い)。
_REAL_LOST_PDF_TEXT = """令和8年(2026年)8月28日 (金)
お問い合わせ 茨城県動物指
26-0572 市町村地区名 笠間市大田町
収容日 2026/8/28 公表期限 2026/9/8
種類 柴犬 犬猫種 犬
毛色 茶 性別 オス
体格 中 首輪 茶色
備考
26-0573 市町村地区名 行方市荒宿
収容日 2026/8/28 公表期限 2026/9/8
種類 雑種 犬猫種 猫
毛色 黒 性別 メス
体格 中 首輪 無
負傷
備考
"""

# 実 PDF (documents/kouhyou0820.pdf / 2026-08-31 取得) より、26-0548 の
# セルに「おうちに帰れたワン！」(飼い主の元へ戻ったことを示す告知バナー) の
# テキストが重なって混入した実例 (T119)。「犬猫種」というラベル文字列自体が
# 「犬ワ猫種ン！」のように分断され、ラベルベースの抽出では species を
# 拾えなくなる。行末アンカーの `_SPECIES_LINE_END_RE` はこのケースでも
# 行末の「犬」を正しく拾えることを確認する。
_REAL_LOST_PDF_TEXT_WITH_BANNER_CORRUPTION = """26-0548 市町村地区名 牛久市奥原町
おうちに
収容日 2026/8/20 公表期限 2026/8/31
種類 シーズー帰れた犬ワ猫種ン！ 犬
毛色 白黒 性別 オス
体格 小 首輪 無
備考
"""

_SHELTERED_LIST_URL = "https://www.pref.ibaraki.jp/hokenfukushi/doshise/hogo/syuuyou.html"
# T119: 旧 list_url (mayoiinuneko.html) はハブページ化していたため、
# 実サイトで「動物指導センター公表情報」リンク先として確認した kouji.html
# へ変更した (documents/kouhyou*.pdf を6件確認済み)。
_LOST_LIST_URL = "https://www.pref.ibaraki.jp/hokenfukushi/doshise/hogo/kouji.html"

# href は実サイト (kouji.html) の現行ファイル名規則を模す。
# `kouhyou0824-1.pdf` のような枝番付きファイル名も対象に含む。
_LOST_LIST_HTML = """
<html><head><title>茨城県 動物指導センター公表情報</title></head>
<body>
  <h1>動物指導センター公表情報</h1>
  <p><a href="/hokenfukushi/doshise/hogo/documents/kouhyou0827.pdf">8月27日公表（PDF）</a></p>
  <p><a href="/hokenfukushi/doshise/hogo/documents/kouhyou0828.pdf">8月28日公表（PDF）</a></p>
  <p><a href="/hokenfukushi/doshise/hogo/index.html">トップへ戻る</a></p>
</body></html>
"""


def _site(
    name: str = "茨城県（収容中の動物たち）",
    category: str = "sheltered",
    list_url: str = _SHELTERED_LIST_URL,
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="茨城県",
        prefecture_code="08",
        list_url=list_url,
        category=category,
    )


def _lost_site(name: str = "茨城県（迷い犬・猫情報）") -> SiteConfig:
    """「迷い犬・猫情報」(category="lost") 用の SiteConfig (T119)"""
    return _site(name, category="lost", list_url=_LOST_LIST_URL)


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
        adapter = PrefIbarakiPdfAdapter(_lost_site())
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

    def test_parses_real_lost_pdf_with_swapped_species_breed_labels(self):
        """「迷い犬・猫情報」実PDFは「種類」「犬猫種」の意味が逆転している (T119)

        「収容中の動物たち」は 種類=動物種別・犬猫種=品種 だが、
        「迷い犬・猫情報」は 種類=品種 (柴犬・雑種)・犬猫種=動物種別 (犬・猫)。
        「種類」ラベル値をそのまま species とすると、品種が犬/猫の文字を
        含まない場合 (例: 「雑種」) に DataNormalizer で「その他」に
        誤分類される (T118 と同型)。行末アンカーで正しく動物種別側を
        拾えることを確認する。
        """
        adapter = PrefIbarakiPdfAdapter(_lost_site())
        records = adapter._parse_pdf_text(_REAL_LOST_PDF_TEXT)

        assert len(records) == 2
        first, second = records

        assert first["management_number"] == "26-0572"
        assert first["shelter_date"] == "2026-08-28"
        assert first["species"] == "犬"  # 「種類」は柴犬 (品種) だが正しく犬
        assert first["sex"] == "オス"
        assert first["color"] == "茶"
        assert first["location"] == "笠間市大田町"

        assert second["management_number"] == "26-0573"
        assert second["shelter_date"] == "2026-08-28"
        # 「種類」は「雑種」(犬/猫の文字を含まない品種名) だが、行末の
        # 「犬猫種 猫」から正しく猫と判定できる (誤分類なら「その他」になる)
        assert second["species"] == "猫"
        assert second["sex"] == "メス"
        assert second["color"] == "黒"
        assert second["location"] == "行方市荒宿"

    def test_parses_species_despite_banner_text_corruption(self):
        """告知バナーの文字混入で「犬猫種」ラベルが分断されても species を拾える (T119)

        実 PDF (documents/kouhyou0820.pdf) では「おうちに帰れたワン！」という
        告知バナーが該当セルに重なり、「種類 シーズー帰れた犬ワ猫種ン！ 犬」
        のように「犬猫種」という文字列自体が分断されている。ラベル文字列に
        依存しない行末アンカーであれば、この壊れたテキストでも正しく
        species="犬" を拾えることを確認する。
        """
        adapter = PrefIbarakiPdfAdapter(_lost_site())
        records = adapter._parse_pdf_text(_REAL_LOST_PDF_TEXT_WITH_BANNER_CORRUPTION)

        assert len(records) == 1
        assert records[0]["management_number"] == "26-0548"
        assert records[0]["species"] == "犬"
        assert records[0]["location"] == "牛久市奥原町"


# ─────────────────── _pdf_link_selector category 分岐テスト (T119) ───────────────────


class TestPdfLinkSelector:
    """category に応じて PDF リンクセレクタが切り替わることを確認する"""

    def test_sheltered_category_uses_inu_neko_selector(self):
        adapter = PrefIbarakiPdfAdapter(_site())
        selector = adapter._pdf_link_selector()
        assert "documents/inu" in selector
        assert "documents/neko" in selector
        assert "kouhyou" not in selector

    def test_lost_category_uses_kouhyou_selector(self):
        adapter = PrefIbarakiPdfAdapter(_lost_site())
        selector = adapter._pdf_link_selector()
        assert "documents/kouhyou" in selector
        assert "documents/inu" not in selector
        assert "documents/neko" not in selector


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

    def test_lost_category_fetches_from_kouji_html_with_kouhyou_selector(self):
        """「迷い犬・猫情報」は kouji.html 一覧から documents/kouhyou*.pdf を拾う (T119)

        旧 list_url (mayoiinuneko.html) はハブページ化し PDF への直接リンクを
        持たなくなっていたため kouji.html に変更した。ファイル名規則も
        documents/inu・documents/neko とは異なる documents/kouhyou のため、
        category="lost" 側のセレクタで正しく2 PDF ぶんのリンクを拾えることを
        確認する。
        """
        adapter = PrefIbarakiPdfAdapter(_lost_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LOST_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_REAL_LOST_PDF_TEXT),
        ):
            result = adapter.fetch_animal_list()

        # kouhyou0827.pdf・kouhyou0828.pdf それぞれ2頭ぶん (_REAL_LOST_PDF_TEXT) → 合計4件
        assert len(result) == 4
        for url, cat in result:
            assert "documents/kouhyou" in url
            assert cat == "lost"

    def test_lost_category_extract_and_normalize_yields_correct_species(self):
        """「迷い犬・猫情報」を実PDF形式で抽出 → normalize() まで通し species が正しい (T119)

        CLAUDE.md 最重要ルール: adapter テストは `adapter.normalize(raw)` を
        実行した実際の値でアサートする。「種類」ラベル (品種) をそのまま
        species にすると「雑種」のような犬/猫の文字を含まない品種名が
        normalize 段で「その他」に誤分類される (T118 と同型)。ここでは
        26-0573 (種類=雑種・犬猫種=猫) が正しく "猫" に normalize されることを
        実際に確認する。
        """
        adapter = PrefIbarakiPdfAdapter(_lost_site())

        with (
            patch.object(adapter, "_http_get", return_value=_LOST_LIST_HTML),
            patch.object(adapter, "_download_pdf", return_value=b"PDF"),
            patch.object(adapter, "_extract_pdf_text", return_value=_REAL_LOST_PDF_TEXT),
        ):
            urls = adapter.fetch_animal_list()
            # 2 頭目 (26-0573: 種類=雑種・犬猫種=猫) を狙って取得する
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)
            normalized = adapter.normalize(raw)

        assert raw.species == "猫"
        assert raw.management_number == "26-0573"
        assert raw.category == "lost"
        assert normalized.species == "猫"  # 誤分類なら "その他" になる
        assert normalized.category == "lost"


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
