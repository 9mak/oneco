"""CityMatsuyamaAdapter のテスト

松山市 はぴまるの丘（松山市動物愛護センター）
(city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html) 用
rule-based adapter の動作を検証する。

- single_page 形式の 1 サイトで犬 (aigo_sec05) と猫 (aigo_sec06) を
  同一 HTML の slick スライダーから抽出する
- リポジトリのフィクスチャは mojibake (UTF-8 を Latin-1 として保存し
  直された二重エンコーディング) なので、テスト側で逆変換する
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_matsuyama import (
    CityMatsuyamaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_LIST_URL = "https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html"


def _site() -> SiteConfig:
    return SiteConfig(
        name="松山市 はぴまるの丘（収容中）",
        prefecture="愛媛県",
        prefecture_code="38",
        list_url=_LIST_URL,
        category="lost",
        single_page=True,
    )


def _load_matsuyama_html(fixture_html) -> str:
    """フィクスチャを読み込み、必要であれば mojibake (二重 UTF-8) を補正する

    実運用 (`_http_get`) では requests が正しい UTF-8 として受け取るため
    補正は不要だが、リポジトリ保存ファイルは Latin-1 → UTF-8 の二重符号化
    状態なのでここで一度だけ巻き戻す。
    """
    raw = fixture_html("city_matsuyama_ehime_jp")
    if "松山" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _build_html_empty() -> str:
    """両セクションともスライダー <li> を持たない 0 件 HTML"""
    return """
    <html><body>
      <div class="aigo_sec05 aigo_wp_over">
        <ul class="slider02" id="slick02"></ul>
      </div>
      <div class="aigo_sec06 aigo_wp_over">
        <ul class="slider03" id="slick03"></ul>
      </div>
    </body></html>
    """


def _build_html_one_dog_one_cat() -> str:
    """犬 1 頭 + 猫 1 頭の最小 HTML"""
    return """
    <html><body>
      <div class="aigo_sec05 aigo_wp_over">
        <ul class="slider02" id="slick02">
          <li>
            <span class="movie_slider_img">
              <img src="index.images/inu.R7No.999.jpg"
                   width="450" height="600" alt="R7No.999">
            </span>
            <span class="movie_slider_text">新しい飼い主募集中</span>
          </li>
        </ul>
      </div>
      <div class="aigo_sec06 aigo_wp_over">
        <ul class="slider03" id="slick03">
          <li>
            <span class="movie_slider_img">
              <img src="index.images/neko.R8No.01.jpg"
                   width="450" height="600" alt="R8.No.01">
            </span>
            <span class="movie_slider_text">マッチング予約不可</span>
          </li>
        </ul>
      </div>
    </body></html>
    """


def _build_html_with_settled_animal() -> str:
    """譲渡確定・仮予約・募集中が並ぶ最小 HTML

    実サイトの状態表示は「新しい飼い主募集中」「マッチング予約不可」
    「マッチング中（仮予約）」「新しい飼い主が決まりました！（本予約）」の4種。
    """
    return """
    <html><body>
      <div class="aigo_sec05 aigo_wp_over">
        <ul class="slider02" id="slick02">
          <li>
            <span class="movie_slider_img"><img src="index.images/a.jpg" alt="R8No.01"></span>
            <span class="movie_slider_text">新しい飼い主募集中</span>
          </li>
          <li>
            <span class="movie_slider_img"><img src="index.images/b.jpg" alt="R8No.02"></span>
            <span class="movie_slider_text">新しい飼い主が決まりました！（本予約）</span>
          </li>
          <li>
            <span class="movie_slider_img"><img src="index.images/c.jpg" alt="R8No.03"></span>
            <span class="movie_slider_text">マッチング中（仮予約）</span>
          </li>
        </ul>
      </div>
    </body></html>
    """


class TestCityMatsuyamaAdapterSettledAnimals:
    """譲渡が決まった子を公開しない (W001/T025)"""

    def test_settled_animal_is_excluded(self):
        """「新しい飼い主が決まりました！（本予約）」の子は収集しない

        問い合わせても会えない子を「収容中」として公開していた
        (本番 id=2020)。サイトから消えた子と同じ扱いにして prune を効かせる。
        """
        adapter = CityMatsuyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_build_html_with_settled_animal()):
            urls = adapter.fetch_animal_list()
            raws = [adapter.extract_animal_details(u, category=c) for (u, c) in urls]

        assert len(urls) == 2
        assert [r.management_number for r in raws] == ["R8No.01", "R8No.03"]

    def test_row_index_is_not_shifted_by_exclusion(self):
        """除外してもカード位置 (#row=N) はズラさない

        詰めると同じ URL が別の子を指すようになり、snapshot 再利用で
        他人のデータが載る。
        """
        adapter = CityMatsuyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_build_html_with_settled_animal()):
            urls = adapter.fetch_animal_list()

        assert [u for u, _ in urls] == [
            "https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html#row=0",
            "https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html#row=2",
        ]

    def test_provisional_reservation_is_kept(self):
        """「マッチング中（仮予約）」はキャンセルの可能性があるので残す"""
        adapter = CityMatsuyamaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=_build_html_with_settled_animal()):
            urls = adapter.fetch_animal_list()
            raws = [adapter.extract_animal_details(u, category=c) for (u, c) in urls]

        assert any("仮予約" in (r.description or "") for r in raws)


class TestCityMatsuyamaAdapterFixture:
    """実フィクスチャ (city_matsuyama_ehime_jp.html) ベースのテスト"""

    def test_fetch_animal_list_returns_dogs_and_cats(self, fixture_html):
        """フィクスチャは犬 5 頭 + 猫 1 頭 = 計 6 件を返す"""
        html = _load_matsuyama_html(fixture_html)
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 6
        # 全エントリの仮想 URL 形式と category を検証
        for i, (url, cat) in enumerate(result):
            assert url == f"{_LIST_URL}#row={i}"
            assert cat == "lost"

    def test_extract_first_dog_from_fixture(self, fixture_html):
        """フィクスチャの 1 件目は犬カード (R7No.310)"""
        html = _load_matsuyama_html(fixture_html)
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            url, category = urls[0]
            raw = adapter.extract_animal_details(url, category=category)

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        # 収容番号(R7No.310)が management_number として保持される(回帰防止)
        assert raw.management_number == "R7No.310"
        # location は所在地 (施設名)。収容番号や状態を入れない (W001/T023)。
        # 「R7No.249-250 新しい飼い主募集中」が所在地として公開されていた。
        assert raw.location == "松山市動物愛護センター（はぴまるの丘）"
        assert "R7No.310" not in raw.location
        assert "新しい飼い主募集中" not in raw.location
        # 状態は description に入る
        assert "新しい飼い主募集中" in raw.description
        # 電話番号は固定値が正規化されて入る
        assert raw.phone == "089-923-9435"
        # 画像は絶対 URL に変換される
        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://www.city.matsuyama.ehime.jp/")
            assert "inu.R7No.310" in u or "inu" in u
        # source_url / category が仮想 URL 経由で保持される
        assert raw.source_url == url
        assert raw.category == "lost"

        # normalize() 経由でも management_number (個体識別フィールド) が
        # 脱落しないこと (実フィクスチャ経由の end-to-end 検証)。
        animal_data = adapter.normalize(raw)
        assert animal_data.management_number == "R7No.310"
        assert animal_data.location == "松山市動物愛護センター（はぴまるの丘）"

    def test_extract_last_entry_is_cat_from_fixture(self, fixture_html):
        """フィクスチャの最終件 (index 5) は猫カード"""
        html = _load_matsuyama_html(fixture_html)
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            last_url, category = urls[-1]
            raw = adapter.extract_animal_details(last_url, category=category)

        assert raw.species == "猫"
        # 猫カードのステータス例
        assert "マッチング予約不可" in raw.description
        assert raw.location == "松山市動物愛護センター（はぴまるの丘）"

    def test_http_get_called_only_once_when_iterating(self, fixture_html):
        """同一ページから複数件取得しても HTTP は 1 回だけ (キャッシュ)"""
        html = _load_matsuyama_html(fixture_html)
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                adapter.extract_animal_details(url, category=cat)

        assert mock_get.call_count == 1


class TestCityMatsuyamaAdapterSynthetic:
    """合成 HTML を使った詳細パターンのテスト"""

    def test_fetch_animal_list_returns_empty_when_no_li(self):
        """両スライダーが空のとき 0 件を返す (例外を投げない)"""
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_build_html_empty()):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_fetch_animal_list_orders_dogs_before_cats(self):
        """ROW_SELECTOR の並び通り、犬 → 猫 の順で返る"""
        html = _build_html_one_dog_one_cat()
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raws = [adapter.extract_animal_details(u, category=c) for (u, c) in urls]

        assert [r.species for r in raws] == ["犬", "猫"]

    def test_extract_synthetic_dog_full_fields(self):
        """合成 HTML から RawAnimalData の各フィールドを検証"""
        html = _build_html_one_dog_one_cat()
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            dog_url, _ = urls[0]
            raw = adapter.extract_animal_details(dog_url, category="lost")

        assert raw.species == "犬"
        assert raw.sex == ""
        assert raw.age == ""
        assert raw.color == ""
        assert raw.size == ""
        assert raw.shelter_date == ""
        assert raw.location == "松山市動物愛護センター（はぴまるの丘）"
        assert raw.management_number == "R7No.999"
        assert "新しい飼い主募集中" in raw.description
        assert raw.phone == "089-923-9435"
        # 画像 URL は list_url を base に絶対化される
        assert raw.image_urls == [
            "https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.images/inu.R7No.999.jpg"
        ]

        # normalize() 経由でも management_number (個体識別フィールド) が
        # 脱落しないこと (T042/T114: raw のみの確認では normalize 段の
        # サイレントドロップを検知できない)。
        animal_data = adapter.normalize(raw)
        assert animal_data.management_number == "R7No.999"
        assert animal_data.description == "新しい飼い主募集中"
        assert animal_data.location == "松山市動物愛護センター（はぴまるの丘）"
        assert animal_data.phone == "089-923-9435"

    def test_extract_synthetic_cat_species_inferred_by_section(self):
        """猫セクション (aigo_sec06) 配下の <li> は species='猫'"""
        html = _build_html_one_dog_one_cat()
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            cat_url, _ = urls[1]
            raw = adapter.extract_animal_details(cat_url, category="lost")

        assert raw.species == "猫"
        assert raw.management_number == "R8.No.01"
        assert "マッチング予約不可" in raw.description
        assert raw.image_urls and raw.image_urls[0].endswith("/index.images/neko.R8No.01.jpg")

    def test_invalid_row_index_raises_parsing_error(self):
        """range 外の row index は ParsingError"""
        from data_collector.adapters.municipality_adapter import ParsingError

        html = _build_html_one_dog_one_cat()
        adapter = CityMatsuyamaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            adapter.fetch_animal_list()  # キャッシュ
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(f"{_LIST_URL}#row=99", category="lost")


class TestCityMatsuyamaAdapterRegistry:
    def test_site_is_registered(self):
        """sites.yaml の name で adapter が引ける"""
        # 他テストが registry を clear する場合に備えて冪等に再登録
        if SiteAdapterRegistry.get("松山市 はぴまるの丘（収容中）") is None:
            SiteAdapterRegistry.register("松山市 はぴまるの丘（収容中）", CityMatsuyamaAdapter)
        assert SiteAdapterRegistry.get("松山市 はぴまるの丘（収容中）") is CityMatsuyamaAdapter
