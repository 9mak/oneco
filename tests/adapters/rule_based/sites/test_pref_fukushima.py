"""PrefFukushimaAdapter のテスト

福島県動物愛護センター (pref.fukushima.lg.jp) 用 rule-based adapter
の動作を検証する。

- 1 ページに `<table>` (1 動物 = 1 table) が複数並ぶ single_page 形式
- 6 サイト (中通り/会津/相双 × 迷子犬/迷子猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_fukushima import (
    PrefFukushimaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="福島県（中通り 迷子犬）",
        prefecture="福島県",
        prefecture_code="07",
        list_url=("https://www.pref.fukushima.lg.jp/sec/21620a/honshomaigoinu.html"),
        category="lost",
        single_page=True,
    )


def _load_fukushima_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要なら mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `pref_fukushima__maigo.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態のため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("pref_fukushima__maigo")
    if "福島" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestPrefFukushimaAdapter:
    def test_fetch_animal_list_returns_multiple_tables(self, fixture_html):
        """一覧ページから複数の動物 (仮想 URL) が抽出できる

        フィクスチャの main_body には 3 個の table が並ぶ
        (= 3 件の迷子情報)。
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) >= 2, "少なくとも 2 件以上の動物が抽出されるはず"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.fukushima.lg.jp/")
            assert cat == "lost"

    def test_extract_animal_details_first_row(self, fixture_html, assert_raw_animal):
        """1 件目のテーブルから RawAnimalData が構築できる

        フィクスチャ 1 件目:
            保護日 (管理番号): 令和8年4月28日（火曜日）（n080428-1）
            保護場所:           伊達市梁川町広瀬町
            種類／体格:         雑／中
            毛の色／長さ:       茶白／中
            性別:               メス
            推定年月齢:         6歳
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # ラベルベース抽出値の検証
        assert raw.sex == "メス"
        assert "6" in raw.age  # "6歳"
        # "茶白／中" の前半 (毛色) のみ取り出される
        assert raw.color == "茶白"
        # "雑／中" の後半が size に分離される
        assert raw.size == "中"
        # 場所末尾の全角空白等が除去されている
        assert "伊達市" in raw.location
        assert raw.location.strip() == raw.location
        # 保護日には "令和8年" が含まれる
        assert "令和" in raw.shelter_date
        # 画像 URL が絶対 URL に変換されている (1 件目は写真あり)
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_extract_second_row_handles_label_variants(self, fixture_html):
        """2 件目の表記揺れラベルでもフィールドが取り出される

        フィクスチャ 2 件目はラベルが "保護日（管理番号）" "種類/体格"
        "毛の色/長さ" "その他特徴等" のように半角/全角や末尾差異がある。
        正規化により同じフィールドにマップされることを確認する。
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) >= 2
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert raw.species == "犬"
        assert raw.sex == "メス"
        # "田村市都路町..." 等が場所として取れる
        assert "田村市" in raw.location
        # "茶／短" → 毛色は "茶"
        assert raw.color == "茶"
        # "雑／中" → size = "中"
        assert raw.size == "中"
        # 保護日は "令和8年5月" 含む
        assert "令和" in raw.shelter_date

    def test_all_six_sites_registered(self):
        """6 つの福島県サイト名すべてが Registry に登録されている"""
        expected = [
            "福島県（中通り 迷子犬）",
            "福島県（中通り 迷子猫）",
            "福島県（会津 迷子犬）",
            "福島県（会津 迷子猫）",
            "福島県（相双 迷子犬）",
            "福島県（相双 迷子猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, PrefFukushimaAdapter)
            assert SiteAdapterRegistry.get(name) is PrefFukushimaAdapter

    def test_species_inferred_from_site_name_for_cat(self, fixture_html):
        """サイト名に "猫" が含まれる場合 species が "猫" になる"""
        html = _load_fukushima_html(fixture_html)
        cat_site = SiteConfig(
            name="福島県（会津 迷子猫）",
            prefecture="福島県",
            prefecture_code="07",
            list_url=("https://www.pref.fukushima.lg.jp/sec/21620a/aizumaigoneko.html"),
            category="lost",
            single_page=True,
        )
        adapter = PrefFukushimaAdapter(cat_site)
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.species == "猫"

    def test_no_tables_returns_empty_list(self):
        """テーブルが見当たらない HTML は真ゼロとして空リストを返す"""
        adapter = PrefFukushimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_phone_injected_per_branch(self, fixture_html):
        """支所別の代表電話番号が phone に注入される

        サイト名で「中通り(本所)/会津/相双」を識別し、それぞれの支所代表番号を
        各 RawAnimalData に注入する。マッピングに無い名称では phone="" のまま。
        """
        html = _load_fukushima_html(fixture_html)
        expected_phone_by_name = {
            "福島県（中通り 迷子犬）": "024-953-6400",
            "福島県（中通り 迷子猫）": "024-953-6400",
            "福島県（会津 迷子犬）": "0242-29-5517",
            "福島県（会津 迷子猫）": "0242-29-5517",
            "福島県（相双 迷子犬）": "0244-26-1351",
            "福島県（相双 迷子猫）": "0244-26-1351",
        }
        for site_name, expected_phone in expected_phone_by_name.items():
            site = SiteConfig(
                name=site_name,
                prefecture="福島県",
                prefecture_code="07",
                list_url="https://www.pref.fukushima.lg.jp/sec/21620a/dummy.html",
                category="lost",
                single_page=True,
            )
            adapter = PrefFukushimaAdapter(site)
            with patch.object(adapter, "_http_get", return_value=html):
                urls = adapter.fetch_animal_list()
                raw = adapter.extract_animal_details(urls[0][0], category="lost")
            assert raw.phone == expected_phone, (
                f"{site_name}: expected {expected_phone!r}, got {raw.phone!r}"
            )

    def test_phone_empty_for_unknown_site_name(self, fixture_html):
        """サイト名マッピングに無い場合は phone='' で誤った番号を出さない"""
        html = _load_fukushima_html(fixture_html)
        unknown_site = SiteConfig(
            name="福島県（架空の支所 迷子犬）",
            prefecture="福島県",
            prefecture_code="07",
            list_url="https://www.pref.fukushima.lg.jp/sec/21620a/dummy.html",
            category="lost",
            single_page=True,
        )
        adapter = PrefFukushimaAdapter(unknown_site)
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.phone == ""

    def test_empty_placeholder_table_is_skipped(self, fixture_html):
        """値が全て空のプレースホルダー table はスキップする

        フィクスチャ table 2 は管理番号だけ "令和年月日（s-）" のような
        雛形が残り、保護場所/種類/毛色/性別/年齢が全て空のテンプレート行。
        実サイトでも `maigo-dog-miharu.html` の row=0/row=2 や
        `maigo-cat-soso.html` の table 0 等で同型の空プレースホルダーが
        多数並んでおり、これらをそのまま動物データとして取り込むと
        location/sex/age/color/size が全件 None の偽レコードが生成される。
        `fetch_animal_list` の段階で除外し、実データを持つ table のみ
        返すことを保証する。
        """
        html = _load_fukushima_html(fixture_html)
        adapter = PrefFukushimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()

        # 既存フィクスチャ: 実データ table 0/1 + 空プレースホルダー table 2
        # → row=0 と row=1 だけが返り、row=2 は含まれない
        assert len(urls) == 2, f"空プレースホルダー除外後は 2 件のはず: {urls}"
        for url, _ in urls:
            idx = int(url.rsplit("#row=", 1)[1])
            assert idx in (0, 1), f"row=2 はスキップされるべき: {url}"

    def test_empty_placeholder_with_only_separator_values(self):
        """値が区切り文字 (／) のみ・空白のみの table もスキップする

        実サイト (`maigo-dog-miharu.html`) の row=0/row=2 では管理番号枠に
        `n08-1` `s--1` のような雛形だけが残り、種類/体格 の値が "／" の
        ような区切り文字単体になっている。これも空プレースホルダーとして
        除外する。実データ table と混在させて 1 件のみ抽出されることを確認。
        """
        html = (
            "<html><body><div id='main_body'>"
            # table 0: 完全空プレースホルダー
            "<table>"
            "<tr><td>保護日 (管理番号)</td><td>令和年月日（s--1）</td></tr>"
            "<tr><td>保護場所</td><td></td></tr>"
            "<tr><td>種類／体格</td><td>／</td></tr>"
            "<tr><td>毛の色／長さ</td><td>／</td></tr>"
            "<tr><td>性別</td><td></td></tr>"
            "<tr><td>推定年月齢</td><td></td></tr>"
            "</table>"
            # table 1: 実データ
            "<table>"
            "<tr><td>保護日 (管理番号)</td><td>令和8年5月14日（c080514-1）</td></tr>"
            "<tr><td>保護場所</td><td>田村市都路町古道字小滝沢　地内</td></tr>"
            "<tr><td>種類／体格</td><td>雑／中</td></tr>"
            "<tr><td>毛の色／長さ</td><td>茶／短</td></tr>"
            "<tr><td>性別</td><td>メス</td></tr>"
            "<tr><td>推定年月齢</td><td>１０～１３歳</td></tr>"
            "</table>"
            "</div></body></html>"
        )
        adapter = PrefFukushimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()

        assert len(urls) == 1, f"実データ table のみ残るはず: {urls}"
        assert urls[0][0].endswith("#row=0")

    def test_partial_placeholder_with_only_location_is_skipped(self):
        """保護場所だけ "地内" のような断片が残った table もスキップする

        実サイト (`maigo-cat-miharu.html`) の row=1 では保護場所が "地内"
        だけ、種類/毛色/性別/年齢は全て空という中途半端なプレースホルダーが
        確認されている。主要ラベルのうち実値が 1 個しか無い table は
        実データではないと判定し除外する。
        """
        html = (
            "<html><body><div id='main_body'>"
            "<table>"
            "<tr><td>保護日 (管理番号)</td><td>令和7年月日（c-07-1）</td></tr>"
            "<tr><td>保護場所</td><td>地内</td></tr>"
            "<tr><td>種類／体格</td><td>/</td></tr>"
            "<tr><td>毛の色／毛の長さ</td><td>/</td></tr>"
            "<tr><td>性別</td><td></td></tr>"
            "<tr><td>推定年月齢</td><td></td></tr>"
            "</table>"
            "</div></body></html>"
        )
        adapter = PrefFukushimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
        assert urls == [], "実値が 1 個のみの table は空とみなす"

    def test_color_extracted_from_kemonoiro_kenocho_label_variant(self):
        """ラベル "毛の色／毛の長さ" (中通り猫) からも color が取れる

        中通り猫ページ (maigo-cat-miharu.html) は `毛の色/長さ` ではなく
        `毛の色/毛の長さ` というラベル表記が使われており、既存マッピングを
        補強しないと color が常に空になる。
        """
        html = (
            "<html><body><div id='main_body'>"
            "<table>"
            "<tr><td>保護日 (管理番号)</td><td>令和8年5月29日（s080529－1）</td></tr>"
            "<tr><td>保護場所</td><td>西郷村大字鶴生字由井ヶ原 地内</td></tr>"
            "<tr><td>種類／体格</td><td>アメリカンショートヘア／中</td></tr>"
            "<tr><td>毛の色／毛の長さ</td><td>シルバータビー／短</td></tr>"
            "<tr><td>性別</td><td>オス</td></tr>"
            "<tr><td>推定年月齢</td><td>約 ８ 歳</td></tr>"
            "<tr><td>首輪</td><td>なし</td></tr>"
            "</table>"
            "</div></body></html>"
        )
        cat_site = SiteConfig(
            name="福島県（中通り 迷子猫）",
            prefecture="福島県",
            prefecture_code="07",
            list_url="https://www.pref.fukushima.lg.jp/sec/21620a/maigo-cat-miharu.html",
            category="lost",
            single_page=True,
        )
        adapter = PrefFukushimaAdapter(cat_site)
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.color == "シルバータビー"
        assert raw.size == "中"
        assert raw.sex == "オス"
        assert raw.species == "猫"

    def test_table_without_value_cells_is_skipped(self):
        """2 列構成の <tr> が無い table (tds=0 等) はスキップする

        実サイト (`maigo-cat-soso.html`) の table 1-4 はラベルだけ並び
        値セルが一つも無い構造で、これらも空として除外する。
        """
        html = (
            "<html><body><div id='main_body'>"
            "<table>"
            "<tr><th>管理番号</th></tr>"
            "<tr><th>保護日</th></tr>"
            "<tr><th>保護場所</th></tr>"
            "</table>"
            "</div></body></html>"
        )
        adapter = PrefFukushimaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()

        assert urls == [], "値セルを持たない table は空とみなしスキップする"
