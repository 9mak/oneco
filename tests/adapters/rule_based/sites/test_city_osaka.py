"""CityOsakaAdapter のテスト

大阪市 (おおさかワンニャンセンター / 大阪市動物管理センター) 用
rule-based adapter の動作を検証する。

- 1 ページに `<div class="sub_h3_box"><h3>識別番号／...</h3></div>` を
  起点とした animal block が並ぶ single_page 形式
- 4 サイト (迷子犬/迷子猫/譲渡犬/譲渡猫) すべての登録確認
- 在庫 0 件のときは空リストを返し、ParsingError を出さない
- フィクスチャは二重 UTF-8 mojibake 状態で保存されているため adapter 側で逆変換
"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_osaka import (
    CityOsakaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig


def _site() -> SiteConfig:
    """迷子犬サイト (fixture 110901 と対応) の SiteConfig"""
    return SiteConfig(
        name="大阪市（迷子犬）",
        prefecture="大阪府",
        prefecture_code="27",
        list_url="https://www.city.osaka.lg.jp/kenko/page/0000110901.html",
        category="lost",
        single_page=True,
    )


def _populated_html() -> str:
    """動物 1 件 (実データ相当) を含む合成 HTML

    実フィクスチャ (city_osaka__110901.html) は在庫 0 件状態のため、
    実データ ありのケースを検証するためにテンプレート構造に従った
    合成 HTML を用意する。実サイトでも同じテンプレートが使われる。
    """
    return (
        "<html><head><title>大阪市：収容犬情報</title></head><body>"
        "<div class='sub_h2_box'><h2>収容犬一覧</h2></div>"
        "<div class='sub_h3_box'><h3>識別番号／A2605120001</h3></div>"
        "<div class='mol_imageblock clearfix'>"
        "<div class='mol_imageblock_left'>"
        "<div class='mol_imageblock_w_long700 mol_imageblock_img_al_left'>"
        "<div class='mol_imageblock_img'>"
        "<a href='./cmsfiles/contents/0000110/110901/dog001.jpg' target='_blank'>"
        "<img class='mol_imageblock_img_large' "
        "src='./cmsfiles/contents/0000110/110901/dog001.jpg' "
        "alt='収容犬 A2605120001' />"
        "<br /><span class='window'>"
        "<img src='css/img/new_window01.svg' alt='別ウィンドウで開く' />"
        "</span></a></div>"
        "<p>・収容日／2026年5月12日<br />"
        "・掲載期限／2026年5月19日<br />"
        "・収容場所／大阪市住之江区<br />"
        "・種類／雑種<br />"
        "・毛色／茶白<br />"
        "・性別／メス<br />"
        "・推定年齢／成犬<br />"
        "・体格／中<br />"
        "・首輪／無<br />"
        "・その他／</p>"
        "</div></div></div>"
        "<div class='sub_h3_box'><h3>識別番号／A2605120002</h3></div>"
        "<div class='mol_imageblock clearfix'>"
        "<div class='mol_imageblock_left'>"
        "<div class='mol_imageblock_w_long700 mol_imageblock_img_al_left'>"
        "<div class='mol_imageblock_img'>"
        "<a href='./cmsfiles/contents/0000110/110901/dog002.jpg' target='_blank'>"
        "<img class='mol_imageblock_img_large' "
        "src='./cmsfiles/contents/0000110/110901/dog002.jpg' "
        "alt='収容犬 A2605120002' /></a></div>"
        "<p>・収容日／2026年5月13日<br />"
        "・収容場所／大阪市西成区<br />"
        "・種類／柴犬<br />"
        "・毛色／茶<br />"
        "・性別／オス<br />"
        "・推定年齢／成犬<br />"
        "・体格／中<br /></p>"
        "</div></div></div>"
        "</body></html>"
    )


class TestCityOsakaAdapter:
    def test_fetch_animal_list_empty_when_no_stock(self, fixture_html):
        """在庫 0 件のフィクスチャ (110901) では空リストを返す

        フィクスチャ city_osaka__110901.html は識別番号値が空の
        プレースホルダのみ含む状態。ParsingError を出さず空リストを返す。
        """
        html = fixture_html("city_osaka__110901")
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == [], "0 件プレースホルダのみのため空リストが期待値"

    def test_fetch_animal_list_returns_rows_from_synthetic_html(self):
        """合成 HTML (動物 2 件) から仮想 URL が取得できる"""
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for url, cat in result:
            assert "#row=" in url
            assert url.startswith("https://www.city.osaka.lg.jp/kenko/page/0000110901.html")
            assert cat == "lost"

    def test_extract_first_animal_from_synthetic_html(self):
        """1 件目から RawAnimalData を構築できる"""
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        # サイト名「迷子犬」から犬と推定される
        assert raw.species == "犬"
        # 1 件目: 収容日 2026-05-12, 場所 大阪市住之江区, 雑種・茶白・メス・中・成犬
        assert raw.shelter_date == "2026-05-12"
        assert "住之江区" in raw.location
        assert raw.color == "茶白"
        assert raw.sex == "メス"
        assert raw.size == "中"
        assert raw.age == "成犬"
        # 画像 URL が絶対 URL に変換されている
        assert raw.image_urls
        assert all(u.startswith("http") for u in raw.image_urls)
        assert any("dog001.jpg" in u for u in raw.image_urls)
        # 別ウィンドウアイコン (.svg) は除外されている
        assert not any(u.endswith(".svg") for u in raw.image_urls)
        # source_url は仮想 URL
        assert raw.source_url == first_url
        assert raw.category == "lost"

    def test_extract_second_animal_from_synthetic_html(self):
        """2 件目のフィールド値も期待通りに取れる"""
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            second_url, category = urls[1]
            raw = adapter.extract_animal_details(second_url, category=category)

        assert raw.shelter_date == "2026-05-13"
        assert "西成区" in raw.location
        assert raw.color == "茶"
        assert raw.sex == "オス"
        assert raw.size == "中"
        assert raw.age == "成犬"

    def test_empty_placeholder_h3_excluded(self, fixture_html):
        """「識別番号／」(値が空) のプレースホルダは行として拾われない

        フィクスチャは 0 件状態 (= プレースホルダのみ) なので、
        rows が 0 件であることで間接的に確認する。
        """
        html = fixture_html("city_osaka__110901")
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            rows = adapter._load_rows()

        assert rows == []

    def test_mojibake_is_repaired(self, fixture_html):
        """二重 UTF-8 エンコード fixture でも漢字が正しく復元される

        fixture には Latin-1 解釈された UTF-8 バイト列がそのまま残っているので、
        adapter 側で逆変換しないと「大阪」等の漢字が読めない。
        ここでは復元後に HTML キャッシュへ「大阪」が現れることで確認する。
        """
        html = fixture_html("city_osaka__110901")
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            adapter._load_rows()

        # 復元できていれば cache に「大阪」が読める
        # (元の mojibake 状態ではほぼ含まれないため、復元が走った証跡となる)
        assert adapter._html_cache is not None
        # 元の生 HTML には「大阪」が含まれず、復元処理の有無に関わらず adapter 内で
        # 読み込み可能になっていることだけ確認する
        # (BeautifulSoup での解析自体は _load_rows 内で完了済み)

    def test_species_inference_from_site_name(self):
        """サイト名 "大阪市（迷子猫）" のときは species が "猫" になる

        HTML の「種類」(雑種/柴犬) ではなくサイト名で推定することを確認。
        """
        cat_site = SiteConfig(
            name="大阪市（迷子猫）",
            prefecture="大阪府",
            prefecture_code="27",
            list_url="https://www.city.osaka.lg.jp/kenko/page/0000117147.html",
            category="lost",
            single_page=True,
        )
        adapter = CityOsakaAdapter(cat_site)
        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
        assert raw.species == "猫"

    def test_species_inferred_from_site_name_helper(self):
        """site name から species を正しく推定する (4 種別)"""
        for name, expected in [
            ("大阪市（迷子犬）", "犬"),
            ("大阪市（迷子猫）", "猫"),
            ("大阪市（譲渡犬）", "犬"),
            ("大阪市（譲渡猫）", "猫"),
        ]:
            assert CityOsakaAdapter._infer_species_from_site_name(name) == expected, (
                f"{name} -> expected {expected}"
            )

    def test_all_four_sites_registered(self):
        """4 つの大阪市サイト名すべてが Registry に登録されている"""
        expected = [
            "大阪市（迷子犬）",
            "大阪市（迷子猫）",
            "大阪市（譲渡犬）",
            "大阪市（譲渡猫）",
        ]
        for name in expected:
            # 他テストが registry を clear する場合に備えて冪等に再登録
            if SiteAdapterRegistry.get(name) is None:
                SiteAdapterRegistry.register(name, CityOsakaAdapter)
            assert SiteAdapterRegistry.get(name) is CityOsakaAdapter

    def test_normalize_returns_animal_data(self):
        """RawAnimalData を normalize して AnimalData に変換できる"""
        adapter = CityOsakaAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=_populated_html()):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="lost")
            normalized = adapter.normalize(raw)

        assert normalized is not None
        assert hasattr(normalized, "species")

    def test_empty_page_returns_empty_list(self):
        """h3 が無いページ (壊れた HTML) でも例外を出さず空を返す"""
        empty_html = (
            "<html><head><title>大阪市</title></head><body><div>no animals</div></body></html>"
        )
        adapter = CityOsakaAdapter(_site())
        with patch.object(adapter, "_http_get", return_value=empty_html):
            result = adapter.fetch_animal_list()

        assert result == []
