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

from datetime import date
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

    def test_fetch_animal_list_empty_state_preprocessed_html(self, fixture_html):
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
            raws = [adapter.extract_animal_details(u, category=c) for u, c in urls]

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
        # 動物管理センター代表電話を全件共通で割り当てる (2026-06 観測)
        assert first.phone == "048-969-8511"

        # 2 件目: 雑種 メス 白黒 小, 場所 東町, 収容日 5/10
        second = raws[1]
        assert second.sex == "メス"
        assert "白黒" in second.color
        assert second.size == "小"
        assert "東町" in second.location
        assert second.phone == "048-969-8511"

    def test_phone_uses_center_default_for_cat_site(self):
        """保護猫サイトでも動物管理センター代表電話が共通注入される

        越谷市の動物データテーブルは犬・猫共通テンプレートで電話番号列を
        持たない。問い合わせ先はページ末尾の「電話：048-969-8511」固定。
        snapshot で全 5 件 phone=None だったため、サイト共通の固定値として
        全行に注入する。
        """
        html = """
        <html><body>
        <div id="tmp_honbun">
        <table>
          <tbody>
            <tr><td>収容場所</td><td>収容日</td><td>収容期限</td></tr>
            <tr><td>越谷市中島３丁目</td><td>令和8年5月29日</td><td>令和8年6月8日</td></tr>
          </tbody>
        </table>
        <table>
          <tbody>
            <tr><td>種類</td><td>性別</td><td>年齢</td><td>毛色</td><td>体格</td><td>備考</td></tr>
            <tr><td>雑種</td><td>めす</td><td>推定6週齢</td><td>サビ</td><td>小型</td><td>短毛</td></tr>
          </tbody>
        </table>
        </div></body></html>
        """
        adapter = CityKoshigayaAdapter(_site(name="越谷市（保護猫）"))
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        assert raw.phone == "048-969-8511"

    def test_cat_multi_pair_location_and_date_not_corrupted(self):
        """場所テーブルの tbody 内ヘッダ行 (収容場所/収容日/収容期限) を確実に
        除去し、location/shelter_date がヘッダ文字列で汚染されないことを検証する。

        2026-06-15: "収容期限" が header_labels に無く、場所テーブルのヘッダ行が
        データ行として残って動物テーブルと件数がずれ、location='収容場所'・
        shelter_date='収容日'(→ 解析失敗で今日にサイレントフォールバック) の
        汚染レコードが生成されていた。実在は複数頭で件数自体は正しいため、
        normalize() 戻り値の location/shelter_date で検証する
        (CLAUDE.md サイレントドロップ規約: 戻り値 AnimalData をアサート)。
        """
        html = """
        <html><body>
        <div id="tmp_honbun">
        <h1>保護・収容した猫の情報（情報：2頭）</h1>
        <h3>R8-26</h3>
        <table><tbody>
          <tr><td>収容場所</td><td>収容日</td><td>収容期限</td></tr>
          <tr><td>越谷市中島３丁目地内</td><td>令和８年５月２９日</td><td>令和８年６月８日</td></tr>
        </tbody></table>
        <table><tbody>
          <tr><td>種類</td><td>性別</td><td>年齢</td><td>毛色</td><td>体格</td><td>備考</td></tr>
          <tr><td>雑種</td><td>めす</td><td>推定６週齢</td><td>サビ</td><td>小型</td><td>短毛</td></tr>
        </tbody></table>
        <h3>R8-25</h3>
        <table><tbody>
          <tr><td>収容場所</td><td>収容日</td><td>収容期限</td></tr>
          <tr><td>越谷市東町２丁目地内</td><td>令和８年５月３０日</td><td>令和８年６月９日</td></tr>
        </tbody></table>
        <table><tbody>
          <tr><td>種類</td><td>性別</td><td>年齢</td><td>毛色</td><td>体格</td><td>備考</td></tr>
          <tr><td>雑種</td><td>めす</td><td>推定６週齢</td><td>三毛</td><td>小型</td><td>短毛</td></tr>
        </tbody></table>
        </div></body></html>
        """
        adapter = CityKoshigayaAdapter(_site(name="越谷市（保護猫）"))
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raws = [adapter.extract_animal_details(u, category=c) for u, c in urls]
        animals = [adapter.normalize(r) for r in raws]

        assert len(animals) == 2
        # ヘッダ文字列がデータとして混入していないこと
        assert all(a.location != "収容場所" for a in animals)
        # 収容日 が解析できずに今日へフォールバックしていないこと (実日付に整列)
        assert animals[0].location == "越谷市中島３丁目地内"
        assert animals[0].shelter_date == date(2026, 5, 29)
        assert animals[1].location == "越谷市東町２丁目地内"
        assert animals[1].shelter_date == date(2026, 5, 30)
        assert all(a.species == "猫" for a in animals)

    def test_species_inference_from_site_name(self, fixture_html):
        """サイト名で species が決まる (保護犬→犬 / 保護猫→猫 / 犬猫→その他)"""
        # 保護犬
        adapter_dog = CityKoshigayaAdapter(_site(name="越谷市（保護犬）"))
        assert adapter_dog._infer_species_from_site_name("越谷市（保護犬）") == "犬"
        # 保護猫
        assert CityKoshigayaAdapter._infer_species_from_site_name("越谷市（保護猫）") == "猫"
        # 個人保護犬猫 (犬猫いずれもありうるため "その他")
        assert (
            CityKoshigayaAdapter._infer_species_from_site_name("越谷市（個人保護犬猫）") == "その他"
        )

    def test_dog_and_cat_sites_registered(self):
        """保護犬・保護猫の 2 サイトが CityKoshigayaAdapter に登録されている

        個人保護犬猫 (hogo_kojin.html) は HTML 構造が全く異なるため
        専用 adapter (CityKoshigayaKojinAdapter) に分離されている
        (test_city_koshigaya_kojin.py で検証)。
        """
        expected = [
            "越谷市（保護犬）",
            "越谷市（保護猫）",
        ]
        for name in expected:
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityKoshigayaAdapter)
            assert SiteAdapterRegistry.get(name) is CityKoshigayaAdapter

    def test_raises_parsing_error_when_no_animal_table(self):
        """動物テーブルも告知文も無い HTML では ParsingError 系例外を出す"""
        adapter = CityKoshigayaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value="<html><body></body></html>"):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_td_only_header_row_is_excluded_from_data(self):
        """`<th>` 不在で `<td>` だけのヘッダ行をデータとして取り込まない

        越谷市 CMS は 2026-05 頃から見出しを `<th>` ではなく背景色付き
        `<td>` で記述するように変更。ヘッダ行（全セルが既知ラベル）は
        データ行から除外し、ヘッダ文言「品種」もテーブル検出キーワード
        として認識する必要がある。
        """
        html = """
        <html><body>
        <div id="tmp_honbun">
        <table>
          <tbody>
            <tr><td>収容場所</td><td>収容期日</td><td>収容期限</td></tr>
            <tr><td>越谷市某所</td><td>2026年5月10日</td><td>2026年5月17日</td></tr>
          </tbody>
        </table>
        <table>
          <tbody>
            <tr><td>品種</td><td>性別</td><td>年齢</td><td>毛色</td><td>体格</td><td>備考</td></tr>
            <tr><td>雑種</td><td>オス</td><td>成犬</td><td>茶白</td><td>中</td><td>大人しい</td></tr>
          </tbody>
        </table>
        </div>
        </body></html>
        """
        adapter = CityKoshigayaAdapter(_site(name="越谷市（保護猫）"))
        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1, f"ヘッダ行を除いた 1 件のみ抽出されるはず: {urls!r}"
            raw = adapter.extract_animal_details(urls[0][0], category=urls[0][1])

        assert raw.sex == "オス"
        assert "茶白" in raw.color
        assert raw.size == "中"
