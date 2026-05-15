"""PrefTottoriAdapter のテスト

鳥取県（迷子動物情報）サイト (pref.tottori.lg.jp) 用 rule-based adapter
の動作を検証する。

- 1 ページに「中部総合事務所収容動物」「西部総合事務所収容動物」の
  2 ブロックが並ぶ single_page 形式
- 個別 detail ページは存在せず仮想 URL (`<list_url>#row=N`) を返す
- 在庫 0 件 (空セル行のみ) のページでも例外を出さず空リストを返す
- 直前の `<h2 class="Title"> <span>...</span></h2>` から所管保健所と
  電話番号を抽出して location/phone に反映する
- ヘッダー行 (中部表は th, 西部表は td) はいずれも除外する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.pref_tottori import (
    PrefTottoriAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    return SiteConfig(
        name="鳥取県（迷子動物情報）",
        prefecture="鳥取県",
        prefecture_code="31",
        list_url="https://www.pref.tottori.lg.jp/221001.htm",
        category="lost",
        single_page=True,
    )


def _build_html_with_animals(
    *,
    chubu_rows: list[list[str]] | None = None,
    seibu_rows: list[list[str]] | None = None,
) -> str:
    """中部・西部の収容動物テーブル雛形に動物行を流し込んだ HTML を生成

    各行は CELLS = [収容日時, 収容場所, 種類, 品種, 毛色, 性別,
                   推定年齢, 体格その他特徴, 詳細情報, 備考]。
    備考列に画像 `<img>` が含まれる場合は文字列として与えればよい。
    """
    chubu_rows = chubu_rows or []
    seibu_rows = seibu_rows or []

    def _render_table(rows: list[list[str]], use_th_header: bool) -> str:
        if use_th_header:
            header = (
                "<tr>"
                "<th>収容日時</th><th>収容場所</th><th>種類</th><th>品種</th>"
                "<th>毛色</th><th>性別</th><th>推定年齢</th>"
                "<th>体格、その他特徴</th><th>詳細情報</th><th>備考</th>"
                "</tr>"
            )
        else:
            header = (
                "<tr>"
                "<td>収容日時</td><td>収容場所</td><td>種類</td><td>品種</td>"
                "<td>毛色</td><td>性別</td><td>推定年齢</td>"
                "<td>体格、その他特徴</td><td>詳細情報</td><td>備考</td>"
                "</tr>"
            )
        body_rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
        return f"<table><tbody>{header}{body_rows}</tbody></table>"

    chubu_table = _render_table(chubu_rows, use_th_header=True)
    seibu_table = _render_table(seibu_rows, use_th_header=False)

    return (
        "<html><head><title>迷い犬猫収容情報/とりネット/鳥取県公式サイト</title>"
        "</head><body>"
        # お問い合わせ先表 (収容動物表ではない: 除外対象)
        "<h2>お問い合わせ先（保健所）</h2>"
        "<table><tbody>"
        "<tr><td>鳥取市保健所生活安全課</td><td>電話(0857)30-8551</td></tr>"
        "</tbody></table>"
        # 中部総合事務所収容動物
        '<div class="h2frame"><h2 class="Title">'
        "<span>中部総合事務所収容動物　電話 (0858)23-3149  FAX (0858)23-4803</span>"
        "</h2></div>"
        f'<div class="Contents">{chubu_table}</div>'
        # 西部総合事務所収容動物
        '<div class="h2frame"><h2 class="Title">'
        "<span>西部総合事務所収容動物　電話(0859)31-9320  FAX (0859)31-9647</span>"
        "</h2></div>"
        f'<div class="Contents">{seibu_table}</div>'
        # 末尾の別 table (案内, 除外対象)
        "<h2>県民の方がペットを「捜しています」「保護しています」</h2>"
        "<table><tbody><tr><td>案内</td></tr></tbody></table>"
        "</body></html>"
    )


class TestPrefTottoriAdapter:
    def test_fixture_in_stock_zero_returns_empty(self, fixture_html):
        """リポジトリ同梱フィクスチャは在庫 0 件のため空リストを返す

        中部・西部表とも「全セル空白の 1 行」がプレースホルダとして
        存在するが、これは動物行として扱わず除外される。
        ヘッダー行 (収容日時 ...) も除外されるため結果は 0 件になる。
        """
        html = fixture_html("pref_tottori_lg_jp")
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_extracts_animals_from_both_offices(self):
        """中部・西部の両方から動物行が抽出される (合計 = 中部 + 西部)"""
        html = _build_html_with_animals(
            chubu_rows=[
                [
                    "5月10日",
                    "倉吉市",
                    "犬",
                    "雑種",
                    "茶白",
                    "オス",
                    "成犬",
                    "中型",
                    "",
                    "<img src='/uploaded/c1.jpg' />",
                ],
            ],
            seibu_rows=[
                [
                    "5月12日",
                    "米子市",
                    "猫",
                    "雑種",
                    "黒",
                    "メス",
                    "成猫",
                    "小型",
                    "",
                    "",
                ],
                [
                    "5月13日",
                    "境港市",
                    "犬",
                    "ラブラドール",
                    "黄",
                    "オス",
                    "成犬",
                    "大型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3, "中部 1 + 西部 2 = 3 件"
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.pref.tottori.lg.jp/221001.htm")
            assert cat == "lost"

    def test_extract_first_animal_from_chubu(self):
        """中部表の 1 件目から RawAnimalData を構築できる

        - 種別「犬」が species にそのまま入る
        - 場所はテーブル内の「倉吉市」
        - 電話番号は見出し span から「0858-23-3149」として抽出
        - 画像は備考列の <img> から絶対 URL に変換される
        - shelter_date は生文字列「5月10日」(年情報が無い single_page 形式)
        """
        html = _build_html_with_animals(
            chubu_rows=[
                [
                    "5月10日",
                    "倉吉市",
                    "犬",
                    "雑種",
                    "茶白",
                    "オス",
                    "成犬",
                    "中型",
                    "",
                    "<img src='/uploaded/c1.jpg' />",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.location == "倉吉市"
        assert raw.color == "茶白"
        assert raw.sex == "オス"
        assert raw.age == "成犬"
        assert raw.size == "中型"
        assert raw.shelter_date == "5月10日"
        assert raw.phone == "0858-23-3149"
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert raw.image_urls[0].endswith("/uploaded/c1.jpg")
        assert raw.source_url == url
        assert raw.category == "lost"

    def test_extract_animal_from_seibu_uses_seibu_phone(self):
        """西部表の動物には西部総合事務所の電話番号が紐づく

        西部表はヘッダー行も `<td>` (背景色付き) で書かれているが、
        最初のセルが「収容日時」ならヘッダーとして除外される。
        """
        html = _build_html_with_animals(
            seibu_rows=[
                [
                    "5月12日",
                    "米子市",
                    "猫",
                    "雑種",
                    "黒",
                    "メス",
                    "成猫",
                    "小型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.species == "猫"
        assert raw.location == "米子市"
        assert raw.sex == "メス"
        assert raw.color == "黒"
        # 電話番号は西部 (0859-31-9320)
        assert raw.phone == "0859-31-9320"

    def test_other_tables_are_excluded(self):
        """お問い合わせ先表や案内 table は動物として抽出されない

        `_build_html_with_animals` には、収容動物表とは別に
        「お問い合わせ先（保健所）」表と末尾の案内 table が含まれている。
        これらは「収容動物」見出し配下ではないため除外される。
        """
        html = _build_html_with_animals(
            chubu_rows=[
                [
                    "5月10日",
                    "倉吉市",
                    "犬",
                    "雑種",
                    "茶白",
                    "オス",
                    "成犬",
                    "中型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # 動物として扱われるのは中部の 1 件のみ
        assert len(result) == 1

    def test_blank_placeholder_rows_excluded(self):
        """全セル空白のプレースホルダ行 (在庫 0 件状態) は除外される"""
        # 1 行目: ダミーの空セル (実フィクスチャと同様)
        # 2 行目: 実データ
        html = _build_html_with_animals(
            chubu_rows=[
                ["", "", "", "", "", "", "", "", "", ""],
                [
                    "5月10日",
                    "倉吉市",
                    "犬",
                    "雑種",
                    "茶白",
                    "オス",
                    "成犬",
                    "中型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert len(urls) == 1
        assert raw.location == "倉吉市"

    def test_species_normalization_for_unknown_kind(self):
        """『種類』が犬/猫以外の場合は species = 'その他' に正規化される"""
        html = _build_html_with_animals(
            chubu_rows=[
                [
                    "5月10日",
                    "倉吉市",
                    "うさぎ",
                    "ネザーランドドワーフ",
                    "白",
                    "不明",
                    "成体",
                    "小型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        assert raw.species == "その他"

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる

        normalizer は ISO 形式や「YYYY年M月D日」を受け付けるが、
        「M月D日」単独は受け付けないため、normalize テストでは
        年付き表記 (実サイトで 1月跨ぎ等のため記載されることがある形式)
        を使う。
        """
        html = _build_html_with_animals(
            chubu_rows=[
                [
                    "2026年5月10日",
                    "倉吉市",
                    "犬",
                    "雑種",
                    "茶白",
                    "オス",
                    "成犬",
                    "中型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")

    def test_site_registered(self):
        """鳥取県サイト名が Registry に登録されている"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get("鳥取県（迷子動物情報）") is None:
            SiteAdapterRegistry.register("鳥取県（迷子動物情報）", PrefTottoriAdapter)
        assert SiteAdapterRegistry.get("鳥取県（迷子動物情報）") is PrefTottoriAdapter

    def test_raises_parsing_error_on_bad_virtual_url(self):
        """無効な virtual URL では ParsingError を出す"""
        html = _build_html_with_animals(
            chubu_rows=[
                [
                    "5月10日",
                    "倉吉市",
                    "犬",
                    "雑種",
                    "茶白",
                    "オス",
                    "成犬",
                    "中型",
                    "",
                    "",
                ],
            ],
        )
        adapter = PrefTottoriAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            with pytest.raises(Exception):
                adapter.extract_animal_details(
                    "https://www.pref.tottori.lg.jp/221001.htm#row=999",
                    category="lost",
                )
