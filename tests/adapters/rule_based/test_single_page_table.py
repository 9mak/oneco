"""SinglePageTableAdapter のテスト

1 ページに複数動物がテーブル/カードで並ぶサイト用基底クラスを検証。
detail ページなし（fetch_animal_list が仮想 URL を返す方式）。
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.single_page_table import SinglePageTableAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

LIST_HTML = """
<html><body>
  <table>
    <tr><th>名前</th><th>種別</th><th>性別</th><th>年齢</th><th>場所</th></tr>
    <tr><td>ポチ</td><td>犬</td><td>オス</td><td>3歳</td><td>高松市</td></tr>
    <tr><td>タマ</td><td>猫</td><td>メス</td><td>2歳</td><td>高松市</td></tr>
  </table>
</body></html>
"""


def _site() -> SiteConfig:
    return SiteConfig(
        name="サンプル収容情報",
        prefecture="香川県",
        prefecture_code="37",
        list_url="https://example.com/list/",
        category="lost",
        single_page=True,
    )


class _SamplePageAdapter(SinglePageTableAdapter):
    ROW_SELECTOR = "table tr"
    SKIP_FIRST_ROW = True  # ヘッダ行を除外
    COLUMN_FIELDS = {
        # 0-indexed column position -> field name
        1: "species",
        2: "sex",
        3: "age",
    }
    LOCATION_COLUMN = 4
    SHELTER_DATE_DEFAULT = "2026-04-01"


class TestSinglePageTableAdapter:
    def test_fetch_animal_list_returns_virtual_urls(self):
        adapter = _SamplePageAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        assert len(result) == 2
        for url, cat in result:
            assert url.startswith("https://example.com/list/#row=")
            assert cat == "lost"

    def test_extract_animal_details_uses_cached_html(self):
        adapter = _SamplePageAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML) as mock_get:
            adapter.fetch_animal_list()
            raw1 = adapter.extract_animal_details(
                "https://example.com/list/#row=0", category="lost"
            )
            raw2 = adapter.extract_animal_details(
                "https://example.com/list/#row=1", category="lost"
            )
        # 同一ページから複数取得しても HTTP は 1 回だけ
        assert mock_get.call_count == 1
        assert isinstance(raw1, RawAnimalData)
        assert raw1.species == "犬"
        assert raw1.sex == "オス"
        assert raw1.age == "3歳"
        assert raw1.location == "高松市"
        assert raw1.shelter_date == "2026-04-01"
        assert raw2.species == "猫"
        assert raw2.sex == "メス"

    def test_skip_first_row_excludes_header(self):
        adapter = _SamplePageAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=LIST_HTML):
            result = adapter.fetch_animal_list()
        # ヘッダ行 (名前/種別/性別/...) を除外して 2 件
        assert len(result) == 2

    def test_returns_empty_when_no_rows(self):
        # ROW_SELECTOR にヒットしない場合は「現在その種別の収容動物がいない」
        # 真ゼロとして空リストを返し、ParsingError を投げない。
        adapter = _SamplePageAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_identity_fields_passthrough_via_column_fields(self):
        """COLUMN_FIELDS で個体識別キーを宣言すれば RawAnimalData に転写される

        kochi 同型のサイレントドロップ予防の回帰防止テスト。
        基底経路が breed/description/name/management_number の4キーを
        構築子に渡していることを直接検証する。
        """

        class _IdentityAdapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tr"
            SKIP_FIRST_ROW = True
            # 派生は COLUMN_FIELDS にキーを足すだけで開通する
            COLUMN_FIELDS = {
                0: "name",  # 仮名
                1: "species",
                2: "breed",  # 品種
                3: "management_number",
                4: "description",  # 性格・特徴
            }
            LOCATION_COLUMN = None
            SHELTER_DATE_DEFAULT = "2026-04-01"

        html = (
            "<html><body><table>"
            "<tr><th>名前</th><th>種別</th><th>品種</th><th>管理番号</th><th>特徴</th></tr>"
            "<tr><td>ポチ</td><td>犬</td><td>柴犬</td><td>2026-001</td><td>人懐っこい</td></tr>"
            "</table></body></html>"
        )
        adapter = _IdentityAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.name == "ポチ"
        assert raw.breed == "柴犬"
        assert raw.management_number == "2026-001"
        assert raw.description == "人懐っこい"


class _HeaderFieldsAdapter(SinglePageTableAdapter):
    """HEADER_FIELDS の基本動作を検証するための最小 adapter"""

    ROW_SELECTOR = "table tbody tr"
    HEADER_FIELDS: dict = {
        "種類": "species",
        "毛色": "color",
        ("性別", "性別（推定）"): "sex",  # tuple = OR
        "場所": "location",  # 完全一致は無いので部分一致 (収容場所) にフォールバック
    }
    SHELTER_DATE_DEFAULT = ""


HEADER_TABLE_HTML = """
<html><body>
  <table>
    <thead>
      <tr><th>種類</th><th>毛色</th><th>性別</th><th>収容場所</th></tr>
    </thead>
    <tbody>
      <tr><td>柴犬</td><td>茶</td><td>オス</td><td>高松市</td></tr>
      <tr><td>雑種</td><td>白</td><td>メス</td><td>丸亀市</td></tr>
    </tbody>
  </table>
</body></html>
"""


class TestHeaderFields:
    """HEADER_FIELDS (ヘッダ駆動列マッピング) の解決ロジックを検証する (T402)"""

    def test_resolves_columns_from_thead(self):
        adapter = _HeaderFieldsAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=HEADER_TABLE_HTML):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.species == "柴犬"
        assert raw.color == "茶"
        assert raw.sex == "オス"
        assert raw.location == "高松市"

    def test_tuple_label_is_or_matched(self):
        # ヘッダが「性別（推定）」表記でも tuple の 2 番目のラベルでマッチする
        html = HEADER_TABLE_HTML.replace("<th>性別</th>", "<th>性別（推定）</th>")
        adapter = _HeaderFieldsAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.sex == "オス"

    def test_exact_match_preferred_over_substring(self):
        # 完全一致する「種類」列と、部分一致もしうる別列が並んでいても
        # 完全一致する列が優先して採用される。
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tbody tr"
            HEADER_FIELDS = {"種類": "species"}

        html = (
            "<html><body><table><thead>"
            "<tr><th>動物の種類詳細</th><th>種類</th></tr>"
            "</thead><tbody>"
            "<tr><td>誤爆用テキスト</td><td>猫</td></tr>"
            "</tbody></table></body></html>"
        )
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.species == "猫"

    def test_colspan_expands_header_to_multiple_columns(self):
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tbody tr"
            HEADER_FIELDS = {"種類": "species", "場所": "location"}
            COLUMN_FIELDS = {1: "sex"}  # colspan で場所列は 1,2 列目相当になる

        html = (
            "<html><body><table><thead>"
            "<tr><th>種類</th><th colspan='2'>場所</th></tr>"
            "</thead><tbody>"
            "<tr><td>犬</td><td>高松市</td><td>朝日町</td></tr>"
            "</tbody></table></body></html>"
        )
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.species == "犬"
        # colspan=2 の "場所" ヘッダは列 1 に解決される (最初に見つかった列)
        assert raw.location == "高松市"

    def test_rowspan_carries_header_text_to_next_header_row(self):
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tbody tr"
            HEADER_FIELDS = {"管理番号": "management_number", "種類": "species", "性別": "sex"}

        html = (
            "<html><body><table><thead>"
            "<tr><th rowspan='2'>管理番号</th><th colspan='2'>属性</th></tr>"
            "<tr><th>種類</th><th>性別</th></tr>"
            "</thead><tbody>"
            "<tr><td>2026-001</td><td>猫</td><td>メス</td></tr>"
            "</tbody></table></body></html>"
        )
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.management_number == "2026-001"
        assert raw.species == "猫"
        assert raw.sex == "メス"

    def test_multiple_tables_resolved_independently(self):
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tbody tr"
            HEADER_FIELDS = {"種類": "species", "性別": "sex"}

        html = (
            "<html><body>"
            "<table><thead><tr><th>種類</th><th>性別</th></tr></thead>"
            "<tbody><tr><td>犬</td><td>オス</td></tr></tbody></table>"
            "<table><thead><tr><th>性別</th><th>種類</th></tr></thead>"
            "<tbody><tr><td>メス</td><td>猫</td></tr></tbody></table>"
            "</body></html>"
        )
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw0 = adapter.extract_animal_details(
                "https://example.com/list/#row=0", category="lost"
            )
            raw1 = adapter.extract_animal_details(
                "https://example.com/list/#row=1", category="lost"
            )
        assert raw0.species == "犬"
        assert raw0.sex == "オス"
        # 2 つ目のテーブルは列順が逆でも、それぞれ独立してヘッダから解決される
        assert raw1.species == "猫"
        assert raw1.sex == "メス"

    def test_header_not_found_falls_back_to_column_fields(self):
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tr"
            SKIP_FIRST_ROW = False
            HEADER_FIELDS = {"種類": "species"}
            COLUMN_FIELDS = {0: "species", 1: "sex"}

        # <thead> も <th> も無い (ヘッダ行が存在しない) テーブル
        html = "<html><body><table><tr><td>犬</td><td>オス</td></tr></table></body></html>"
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert len(result) == 1
        assert raw.species == "犬"
        assert raw.sex == "オス"

    def test_header_and_column_fields_both_unresolved_yields_zero_rows(self, caplog):
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tr"
            SKIP_FIRST_ROW = False
            HEADER_FIELDS = {"種類": "species"}
            COLUMN_FIELDS: dict = {}

        html = "<html><body><table><tr><td>犬</td><td>オス</td></tr></table></body></html>"
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            with caplog.at_level("WARNING"):
                result = adapter.fetch_animal_list()
        assert result == []
        assert any("サンプル収容情報" in record.message for record in caplog.records)

    def test_header_text_whitespace_and_fullwidth_normalized(self):
        class _Adapter(SinglePageTableAdapter):
            ROW_SELECTOR = "table tbody tr"
            HEADER_FIELDS = {"種類": "species"}

        html = (
            "<html><body><table><thead>"
            "<tr><th>　種類　</th></tr>"  # 全角スペースで囲まれている
            "</thead><tbody><tr><td>犬</td></tr></tbody></table></body></html>"
        )
        adapter = _Adapter(_site())
        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()
            raw = adapter.extract_animal_details("https://example.com/list/#row=0", category="lost")
        assert raw.species == "犬"

    def test_resolve_header_fields_introspection_without_http(self):
        """監査スクリプトが HTTP なしで列解決を確認できることを検証する"""
        from bs4 import BeautifulSoup

        adapter = _HeaderFieldsAdapter(_site())
        soup = BeautifulSoup(HEADER_TABLE_HTML, "html.parser")
        table = soup.find("table")
        resolved = adapter.resolve_header_fields(table)
        assert resolved == {0: "species", 1: "color", 2: "sex", 3: "location"}

    def test_resolve_header_fields_accepts_soup_container(self):
        """`<table>` そのものでなく soup 全体を渡しても最初のテーブルを解決する"""
        from bs4 import BeautifulSoup

        adapter = _HeaderFieldsAdapter(_site())
        soup = BeautifulSoup(HEADER_TABLE_HTML, "html.parser")
        resolved = adapter.resolve_header_fields(soup)
        assert resolved == {0: "species", 1: "color", 2: "sex", 3: "location"}
