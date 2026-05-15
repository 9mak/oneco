"""CityKagoshimaAdapter のテスト

鹿児島市保健所サイト (city.kagoshima.lg.jp/.../joho/{inu,neko}.html) 用
rule-based adapter の動作を検証する。

- 1 ページに `<h2>No.XXX</h2>` + 直後の `<p>` 群が並ぶ single_page 形式
- 2 サイト (保護犬 / 保護猫) すべての登録確認
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_kagoshima import (
    CityKagoshimaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site(
    name: str = "鹿児島市（保護犬）",
    list_url: str = (
        "https://www.city.kagoshima.lg.jp/kenkofukushi/hokenjo/"
        "seiei-jueki/kurashi/dobutsu/kainushi/joho/inu.html"
    ),
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="鹿児島県",
        prefecture_code="46",
        list_url=list_url,
        category="sheltered",
        single_page=True,
    )


def _load_kagoshima_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    リポジトリに保存されている `city_kagoshima.html` は、本来 UTF-8 のバイト列を
    Latin-1 として解釈してから再度 UTF-8 として保存し直された二重エンコーディング
    状態になっているため、実サイト相当のテキストを得るには逆変換が必要。
    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取る。
    """
    raw = fixture_html("city_kagoshima")
    if "鹿児島" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


class TestCityKagoshimaAdapter:
    def test_fetch_animal_list_returns_only_active_animals(self, fixture_html):
        """h2 が「飼い主の元に戻りました」を含むものは除外されている

        フィクスチャは現役 1 件 + 返還済 2 件の計 3 つの h2 を持つ。
        現役 1 件のみが仮想 URL として返ること、各 URL がフラグメント
        付きで base_url を保持していることを確認する。
        """
        html = _load_kagoshima_html(fixture_html)
        adapter = CityKagoshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 1, "現役 1 件のみが対象 (返還済 2 件は除外されるはず)"
        url, cat = result[0]
        assert url.endswith("#row=0")
        assert url.startswith("https://www.city.kagoshima.lg.jp/")
        assert cat == "sheltered"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のブロックから RawAnimalData を構築できる"""
        html = _load_kagoshima_html(fixture_html)
        adapter = CityKagoshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名から犬と推定される
        assert raw.species == "犬"
        # 1 件目 (No.260009): 保護日 令和8年4月30日, 場所 光山二丁目,
        # 性別 雄 → オス, 体格 小, 推定年齢 10歳
        assert "令和8年4月30日" in raw.shelter_date
        assert "光山" in raw.location
        assert raw.sex == "オス"
        assert raw.size == "小"
        assert "10" in raw.age
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.kagoshima.lg.jp/")
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "sheltered"

    def test_returned_animals_are_excluded(self, fixture_html):
        """h2 タイトルに「飼い主の元に戻りました」を含むブロックは除外される

        フィクスチャ内の No.260006 / No.260003 は両方とも返還済み記載があり、
        fetch_animal_list の戻り値件数は現役 (No.260009) の 1 件のみとなる。
        """
        html = _load_kagoshima_html(fixture_html)
        adapter = CityKagoshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            details = [adapter.extract_animal_details(u, category=c) for u, c in urls]

        # 返還済みの場所 (錦江台 / 平川町) は結果に含まれない
        locations = [d.location for d in details]
        assert not any("錦江台" in loc for loc in locations)
        assert not any("平川" in loc for loc in locations)

    def test_species_inference_for_cat_site(self):
        """サイト名 "鹿児島市（保護猫）" のときは species が "猫" になる

        実フィクスチャは犬版なのでミニマルな猫サイト用 HTML を組み立てる。
        """
        cat_html = """
        <html><body><div id="tmp_contents">
          <h1>保護された猫の情報</h1>
          <h2>No.260100</h2>
          <p>
            <img src="/images/cat001.jpg" alt="260100"/>
            保護日：令和8年5月10日（月曜日）
          </p>
          <p>保護場所：城山町</p>
          <p>種類：雑種</p>
          <p>性別：雌</p>
          <p>体格：小</p>
          <p>推定年齢：3歳</p>
        </div></body></html>
        """
        cat_site = _site(
            name="鹿児島市（保護猫）",
            list_url=(
                "https://www.city.kagoshima.lg.jp/kenkofukushi/hokenjo/"
                "seiei-jueki/kurashi/dobutsu/kainushi/joho/neko.html"
            ),
        )
        adapter = CityKagoshimaAdapter(cat_site)

        with patch.object(adapter, "_http_get", return_value=cat_html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="sheltered")

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert "城山" in raw.location
        assert "令和8年5月10日" in raw.shelter_date

    def test_returns_empty_when_no_animal_h2(self):
        """No.XXX を含む h2 が無い (在庫 0 件) ときは空リストを返す

        鹿児島市のサイトは保護動物が居ない期間も平常運用される想定。
        ParsingError ではなく空リスト扱いとする。
        """
        empty_html = """
        <html><body><div id="tmp_contents">
          <h1>保護された犬の情報</h1>
          <p>現在、保護犬はいません。</p>
          <h2>お問い合わせ</h2>
          <p>動物愛護管理センターまで</p>
        </div></body></html>
        """
        adapter = CityKagoshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_all_two_sites_registered(self):
        """2 つの鹿児島市サイト名すべてが Registry に登録されている"""
        expected = [
            "鹿児島市（保護犬）",
            "鹿児島市（保護猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityKagoshimaAdapter)
            assert SiteAdapterRegistry.get(name) is CityKagoshimaAdapter

    def test_extract_caches_html_across_calls(self, fixture_html):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        html = _load_kagoshima_html(fixture_html)
        adapter = CityKagoshimaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1
