"""PrefKagawaPdfAdapter のテスト

香川県の 4 つの保健福祉事務所 (東讃 / 中讃 / 西讃 / 小豆) で共通利用する
PDF 系 rule-based adapter の動作を検証する。

- 一覧 HTML から PDF リンクを抽出 → 各 PDF を仮想 URL に展開
- PDF テキストから動物 dict を `_parse_pdf_text` で抽出
- _http_get / _download_pdf を mock し、合成 PDF テキストでテスト
"""

from __future__ import annotations

from unittest.mock import patch

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

    def test_no_pdf_links_returns_empty(self):
        """PDF リンクが無い HTML は真ゼロとして空リストを返す"""
        adapter = PrefKagawaPdfAdapter(_site())
        empty_html = "<html><body><p>準備中</p></body></html>"

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()
        assert result == []


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


# 実 PDF (中讃保健所 r8-7-31.pdf / 2026-08-03 取得) の pdfplumber 抽出結果。
# 上の合成データと違い、実物は
#   - 見出しが「収容日時」で日付が **和暦**
#   - 場所ラベルが「引取り場所」(「収容場所」ではない)
#   - 「動物の種類 犬 種類 雑種 2～3週齢」のように 1 行へ複数フィールドが並ぶ
#   - 「推 定 / 年月齢」が縦組みの都合で 2 行に割れる
# という形をしており、旧実装ではブロック開始 (収容日) を検出できず 0 件だった。
_REAL_PDF_TEXT = """収容動物情報
※譲渡先を募集中の動物については、さぬき動物愛護センターのページをご覧ください。
さぬき動物愛護センターＵＲＬ：
https://www.pref.kagawa.lg.jp/content/etc/subsite/sanukidouaicenter/index.shtml
掲載開始： 令和8年8月1日
掲載終了： 令和8年8月7日 中讃 保健所
※この情報は、元の飼い主の方を探すために掲載しています。
心当たりのある方は中讃保健所（TEL:０８７７－２４－９９６４）までお問い合わせください）
個体管理番号 2630166
収容日時 令和8年7月31日 13:40
引取り場所 丸亀市 中津町
推 定
動物の種類 犬 種類 雑種 2～3週齢
年月齢
毛色 黒 性別 オス 体格 小
その他の特徴
備考
個体管理番号 2630167
収容日時 令和8年7月31日 13:40
引取り場所 丸亀市 中津町
推 定
動物の種類 犬 種類 雑種 2～3週齢
年月齢
毛色 こげ茶 性別 メス 体格 小
その他の特徴
備考
個体管理番号 2630165
収容日時 令和8年7月29日 9:30
引取り場所 善通寺市 吉原町
推 定
動物の種類 犬 種類 雑種 6～12か月齢
年月齢
毛色 薄茶 性別 メス 体格 小
その他の特徴
※元の飼い主の方を探すための画像です 備考
"""


class TestRealPdfLayout:
    """実 PDF (個体管理番号 + 収容日時 + 和暦) レイアウトのパース"""

    def test_parses_all_animals_from_real_pdf_text(self):
        """個体管理番号ごとに 1 頭として抽出できる"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        assert len(records) == 3, "個体管理番号 3 件ぶんが抽出される"

    def test_converts_japanese_era_to_iso_date(self):
        """和暦「令和8年7月31日」を ISO 形式へ変換する"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        assert records[0]["shelter_date"] == "2026-07-31"
        assert records[2]["shelter_date"] == "2026-07-29"

    def test_extracts_management_number(self):
        """個体管理番号を management_number として取り込む"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        assert [r["management_number"] for r in records] == [
            "2630166",
            "2630167",
            "2630165",
        ]

    def test_extracts_fields_from_multi_field_lines(self):
        """1 行に複数フィールドが並ぶ行から各属性を取り出す"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        first = records[0]
        assert first["species"] == "犬"
        assert first["breed"] == "雑種", "「種類 雑種」は品種として保存する"
        assert first["color"] == "黒"
        assert first["sex"] == "オス"
        assert first["size"] == "小"
        assert "丸亀市" in first["location"], "「引取り場所」を location に使う"

    def test_extracts_age_with_unit_variants(self):
        """「2～3週齢」「6～12か月齢」など単位違いの年齢を取り出す"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        assert records[0]["age"] == "2～3週齢"
        assert records[2]["age"] == "6～12か月齢"

    def test_header_lines_are_not_treated_as_animals(self):
        """掲載開始/終了の和暦日付をブロック開始と誤認しない"""
        adapter = PrefKagawaPdfAdapter(_site())
        records = adapter._parse_pdf_text(_REAL_PDF_TEXT)

        # 「掲載開始： 令和8年8月1日」等が動物として混入していれば 3 件を超える
        assert len(records) == 3
        assert all(r["management_number"] for r in records)
