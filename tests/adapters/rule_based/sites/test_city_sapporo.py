"""札幌市迷子動物 adapter テスト"""

from __future__ import annotations

from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.city_sapporo import CitySapporoAdapter
from data_collector.llm.config import SiteConfig


def _site(species: str = "犬", category: str = "lost") -> SiteConfig:
    return SiteConfig(
        name=f"札幌市（迷子{species}）",
        prefecture="北海道",
        prefecture_code="01",
        list_url=f"https://www.city.sapporo.jp/inuneko/syuuyou_doubutsu/maigo{'inu' if species == '犬' else 'neko2'}.html",
        category=category,
        single_page=True,
    )


SAMPLE_HTML = """
<html><body>
<table><tr><td>
収容年月日：2026-04-15
保護場所：札幌市中央区
種類：雑種
毛色：茶
性別：オス
体格：中
</td></tr></table>
<table><tr><td>
収容年月日：2026-04-20
保護場所：札幌市西区
種類：柴犬
毛色：白
性別：メス
体格：中
</td></tr></table>
</body></html>
"""

EMPTY_HTML = """
<html><body>
<p>現在、迷子動物の収容情報はありません。</p>
<table><tr><td>
収容年月日：保護場所：種類：毛色：性別：体格：
</td></tr></table>
</body></html>
"""


def test_fetch_returns_empty_for_empty_state():
    adapter = CitySapporoAdapter(_site("犬"))
    with patch.object(adapter, "_http_get", return_value=EMPTY_HTML):
        result = adapter.fetch_animal_list()
    assert result == []


def test_fetch_returns_two_animals():
    adapter = CitySapporoAdapter(_site("犬"))
    with patch.object(adapter, "_http_get", return_value=SAMPLE_HTML):
        result = adapter.fetch_animal_list()
    assert len(result) == 2
    for url, _ in result:
        assert url.startswith("https://www.city.sapporo.jp/")
        assert "#row=" in url


def test_extract_returns_raw_data():
    adapter = CitySapporoAdapter(_site("犬"))
    with patch.object(adapter, "_http_get", return_value=SAMPLE_HTML):
        adapter.fetch_animal_list()
        raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#row=0")
    assert raw.species == "雑種"
    assert raw.sex == "オス"
    assert raw.color == "茶"
    assert raw.location == "札幌市中央区"
    assert raw.shelter_date == "2026-04-15"


def test_species_fallback_from_site_name():
    """record に種別が無い時はサイト名 (犬/猫) で補完"""
    no_species_html = SAMPLE_HTML.replace("種類：雑種", "")
    adapter = CitySapporoAdapter(_site("猫"))
    with patch.object(adapter, "_http_get", return_value=no_species_html):
        adapter.fetch_animal_list()
        raw = adapter.extract_animal_details(f"{adapter.site_config.list_url}#row=0")
    assert raw.species == "猫"


def test_two_sites_registered():
    assert SiteAdapterRegistry.get("札幌市（迷子犬）") is CitySapporoAdapter
    assert SiteAdapterRegistry.get("札幌市（迷子猫）") is CitySapporoAdapter


def test_real_fixture_does_not_crash(fixture_html):
    """実 fixture (在庫 0 件状態) でも例外なし"""
    html = fixture_html("city_sapporo")
    adapter = CitySapporoAdapter(_site("犬"))
    with patch.object(adapter, "_http_get", return_value=html):
        result = adapter.fetch_animal_list()
    assert isinstance(result, list)
