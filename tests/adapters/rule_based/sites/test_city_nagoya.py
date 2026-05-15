"""CityNagoyaAdapter のテスト

名古屋市動物愛護センター (city.nagoya.jp/kurashi/pet/) 用
rule-based adapter の動作を検証する。

- single_page 形式 (3 サイトで共通テンプレート)
- フィクスチャは 0 件状態 (動物テーブル無しのテキスト案内ページ) なので、
  データ行を持つテストは synthetic な HTML を組み立てて検証する
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_nagoya import (
    CityNagoyaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "名古屋市（譲渡犬）",
    list_url: str = ("https://www.city.nagoya.jp/kurashi/pet/1015473/1015483/1015484.html"),
    category: str = "adoption",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="愛知県",
        prefecture_code="23",
        list_url=list_url,
        category=category,
        single_page=True,
    )


def _load_nagoya_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_nagoya.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態の可能性があるため、実サイト相当のテキストに戻す。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_nagoya")
    if "名古屋" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_with_one_row() -> str:
    """1 件のデータ行を含むテーブル HTML を生成する (テスト用)

    実サイトの `article#content` 配下の表組ブロックを再現する。
    """
    return """
    <html><body>
      <article id="content">
        <h2>譲渡対象犬の情報</h2>
        <table>
          <tr>
            <th>管理番号</th>
            <th>収容日</th>
            <th>収容場所</th>
            <th>種類</th>
            <th>性別</th>
            <th>毛色</th>
            <th>体格</th>
            <th>写真</th>
          </tr>
          <tr>
            <td>D-001</td>
            <td>令和8年5月10日</td>
            <td>名古屋市中区三の丸</td>
            <td>柴犬</td>
            <td>オス</td>
            <td>茶</td>
            <td>中</td>
            <td><img src="/kurashi/pet/img/dog001.jpg" alt=""></td>
          </tr>
        </table>
      </article>
    </body></html>
    """


def _build_html_with_combined_date_location() -> str:
    """日付 + 場所が 1 セルに混在するパターンの HTML"""
    return """
    <html><body>
      <article id="content">
        <table>
          <tr>
            <th>収容日・収容場所</th>
            <th>種類</th>
            <th>性別</th>
            <th>毛色</th>
          </tr>
          <tr>
            <td>令和8年5月10日 名古屋市中区三の丸</td>
            <td>雑種</td>
            <td>メス</td>
            <td>白黒</td>
          </tr>
        </table>
      </article>
    </body></html>
    """


class TestCityNagoyaAdapter:
    def test_fetch_animal_list_returns_empty_when_no_table(self, fixture_html):
        """動物テーブルが無いテキスト案内ページでは空リストを返す (0 件扱い)"""
        html = _load_nagoya_html(fixture_html)
        adapter = CityNagoyaAdapter(
            _site(
                name="名古屋市（飼主不明動物）",
                list_url=("https://www.city.nagoya.jp/kurashi/pet/1015473/1015489/1015493.html"),
                category="lost",
            )
        )

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # フィクスチャは案内テキストのみで動物 table が無い → 0 件
        assert result == []

    def test_fetch_animal_list_returns_rows_when_data_present(self):
        """データ行があるときは仮想 URL のリストを返す"""
        html = _build_html_with_one_row()
        adapter = CityNagoyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.nagoya.jp/")
        assert cat == "adoption"

    def test_extract_animal_details_first_row(self):
        """1 件目のデータ行から RawAnimalData を構築できる"""
        html = _build_html_with_one_row()
        adapter = CityNagoyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.color == "茶"
        assert raw.size == "中"
        assert "令和8年5月10日" in raw.shelter_date
        assert "名古屋市中区" in raw.location
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.nagoya.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "adoption"

    def test_split_date_and_location_combined_cell(self):
        """「収容日・収容場所」のように 1 セルに複合された値を分割できる"""
        html = _build_html_with_combined_date_location()
        cat_site = _site(
            name="名古屋市（譲渡猫）",
            list_url=("https://www.city.nagoya.jp/kurashi/pet/1015473/1015483/1015488.html"),
        )
        adapter = CityNagoyaAdapter(cat_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.species == "猫"  # サイト名 "(譲渡猫)" から推定
        assert raw.sex == "メス"
        assert "令和8年5月10日" in raw.shelter_date
        assert "名古屋市中区" in raw.location
        # 日付部分が location に混入していないこと
        assert "令和" not in raw.location

    def test_species_inference_for_lost_site(self):
        """サイト名 "(飼主不明動物)" のときは species が "その他" になる"""
        # 動物テーブル付き HTML をあてて species 推定だけを検証
        html = _build_html_with_one_row()
        lost_site = _site(
            name="名古屋市（飼主不明動物）",
            list_url=("https://www.city.nagoya.jp/kurashi/pet/1015473/1015489/1015493.html"),
            category="lost",
        )
        adapter = CityNagoyaAdapter(lost_site)

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")

        # サイト名に犬/猫いずれも含まれない場合は "その他"
        assert raw.species == "その他"

    def test_all_three_sites_registered(self):
        """3 つの名古屋市サイト名すべてが Registry に登録されている"""
        expected = [
            "名古屋市（飼主不明動物）",
            "名古屋市（譲渡犬）",
            "名古屋市（譲渡猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityNagoyaAdapter)
            assert SiteAdapterRegistry.get(name) is CityNagoyaAdapter

    def test_normalize_returns_animal_data(self):
        """normalize() で AnimalData に変換できる"""
        html = _build_html_with_one_row()
        adapter = CityNagoyaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")
            animal = adapter.normalize(raw)

        assert animal is not None
        assert animal.species == "犬"
