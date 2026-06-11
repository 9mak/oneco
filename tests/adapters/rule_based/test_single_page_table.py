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
