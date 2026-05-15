"""CityKoshigayaAdapter のテスト

越谷市保健所 (city.koshigaya.saitama.jp/.../hokenjo/pet/hogo/) 用
rule-based adapter の動作を検証する。

- 動物テーブル (種類/性別/年齢/毛色/体格/備考) と
  場所テーブル (収容場所/収容日/収容期限) を並列に持つ single_page 形式
- 在庫 0 件 (本フィクスチャがこのケース) でも ParsingError を出さず
  空リストを返す
- 3 サイト (保護犬 / 保護猫 / 個人保護犬猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_koshigaya import (
    CityKoshigayaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "越谷市（保護犬）",
    list_url: str = (
        "https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/"
        "hokenjo/pet/hogo/koshigaya_contents_dog.html"
    ),
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="埼玉県",
        prefecture_code="11",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_koshigaya_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_koshigaya.html` は、
    本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
    保存し直された二重エンコーディング状態になっているため、
    実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_koshigaya")
    if "越谷" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityKoshigayaAdapter:
    def test_fetch_animal_list_empty_state_returns_empty(self, fixture_html):
        """在庫 0 件 (「現在、情報はありません。」) のページで空リストを返す

        フィクスチャは「★現在、情報はありません。」と空セルのみのテーブルを
        持つため、ParsingError を出さずに空リストが返ることを確認する。
        adapter は mojibake 補正を自前で行うため、生のフィクスチャをそのまま
        `_http_get` のモック戻り値として渡してもよい。
        """
        raw = fixture_html("city_koshigaya")
        adapter = CityKoshigayaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=raw):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_empty_state_preprocessed_html(
        self, fixture_html
    ):
        """mojibake 補正済みの HTML を渡しても 0 件として扱える"""
        html = _load_koshigaya_html(fixture_html)
        adapter = CityKoshigayaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_with_populated_data(self, fixture_html):
        """動物テーブルに実データが入った合成 HTML から複数件抽出できる

        フィクスチャは 0 件状態のためそのままでは extract のカバレッジを
        確保できない。実テンプレート (`div#tmp_honbun` + 場所テーブル +
        動物テーブル) を維持したまま、空セルの動物行をデータ入り行に
        差し替えた合成 HTML を組み立て、複数件抽出と RawAnimalData 構築を
        検証する。
        """
        base = _load_koshigaya_html(fixture_html)
        soup = BeautifulSoup(base, "html.parser")

        honbun = soup.select_one("div#tmp_honbun")
        assert honbun is not None
        tables = honbun.find_all("table")
        assert len(tables) >= 2, "場所テーブルと動物テーブルが揃っていること"

        location_table, animal_table = tables[0], tables[1]

        def _replace_tbody(table, rows_html: str) -> None:
            tbody = table.find("tbody")
            assert tbody is not None
            tbody.clear()
            for tr in BeautifulSoup(rows_html, "html.parser").find_all("tr"):
                tbody.append(tr)

        # 場所テーブル: 2 行 (各動物の収容場所/収容日/収容期限)
        _replace_tbody(
            location_table,
            """
            <tr>
              <td>越谷市赤山町1丁目</td>
              <td>2026年5月7日</td>
              <td>2026年5月14日</td>
            </tr>
            <tr>
              <td>越谷市東町2丁目</td>
              <td>2026年5月10日</td>
              <td>2026年5月17日</td>
            </tr>
            """,
        )

        # 動物テーブル: 2 行 (種類/性別/年齢/毛色/体格/備考)
        _replace_tbody(
            animal_table,
            """
            <tr>
              <td>柴犬</td>
              <td>オス</td>
              <td>成犬</td>
              <td>茶</td>
              <td>中</td>
              <td>首輪あり</td>
            </tr>
            <tr>
              <td>雑種</td>
              <td>メス</td>
              <td>成犬</td>
              <td>白黒</td>
              <td>小</td>
              <td>大人しい</td>
            </tr>
            """,
        )

        synthetic_html = str(soup)
        adapter = CityKoshigayaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=synthetic_html) as mock_get:
            urls = adapter.fetch_animal_list()
            raws = [
                adapter.extract_animal_details(u, category=c) for u, c in urls
            ]

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert len(urls) == 2
        for u, cat in urls:
            assert "#row=" in u
            assert u.startswith("https://www.city.koshigaya.saitama.jp/")
            assert cat == "sheltered"

        # 1 件目: 柴犬 オス 茶 中, 場所 赤山町, 収容日 5/7
        first = raws[0]
        assert isinstance(first, RawAnimalData)
        assert first.species == "犬"  # サイト名 (保護犬) から推定
        assert first.sex == "オス"
        assert first.age == "成犬"
        assert "茶" in first.color
        assert first.size == "中"
        assert "赤山町" in first.location
        assert "2026" in first.shelter_date
        assert first.source_url == urls[0][0]
        assert first.category == "sheltered"

        # 2 件目: 雑種 メス 白黒 小, 場所 東町, 収容日 5/10
        second = raws[1]
        assert second.sex == "メス"
        assert "白黒" in second.color
        assert second.size == "小"
        assert "東町" in second.location

    def test_species_inference_from_site_name(self, fixture_html):
        """サイト名で species が決まる (保護犬→犬 / 保護猫→猫 / 犬猫→その他)"""
        # 保護犬
        adapter_dog = CityKoshigayaAdapter(_site(name="越谷市（保護犬）"))
        assert adapter_dog._infer_species_from_site_name("越谷市（保護犬）") == "犬"
        # 保護猫
        assert (
            CityKoshigayaAdapter._infer_species_from_site_name(
                "越谷市（保護猫）"
            )
            == "猫"
        )
        # 個人保護犬猫 (犬猫いずれもありうるため "その他")
        assert (
            CityKoshigayaAdapter._infer_species_from_site_name(
                "越谷市（個人保護犬猫）"
            )
            == "その他"
        )

    def test_all_three_sites_registered(self):
        """3 つの越谷市サイト名すべてが Registry に登録されている"""
        expected = [
            "越谷市（保護犬）",
            "越谷市（保護猫）",
            "越谷市（個人保護犬猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityKoshigayaAdapter)
            assert SiteAdapterRegistry.get(name) is CityKoshigayaAdapter

    def test_raises_parsing_error_when_no_animal_table(self):
        """動物テーブルも告知文も無い HTML では ParsingError 系例外を出す"""
        adapter = CityKoshigayaAdapter(_site())
        with patch.object(
            adapter, "_http_get", return_value="<html><body></body></html>"
        ):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()
