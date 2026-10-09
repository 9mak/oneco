"""T519 グループ7: 下関市（city_shimonoseki-1・-2・-3）。fixture は 2026-10-05 の本文（div#main_body か div.detail_free）。

-2 は一覧（猫 5 頭の個体ページへのリンク）と個体ページ 1 枚、-1・-3 は 0 頭の日のページ。
-1 と -3 の「動物が載った日」は実ページに無く未確認（読み方は猫の個体ページから推した）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str):
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _doc(slug: str, html: str) -> Doc:
    return Doc(url=_source(slug).url, html=html, soup=BeautifulSoup(html, "lxml"))


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_shimonoseki_2_item_page_has_all_fields_and_photo():
    src = _source("city_shimonoseki-2")
    recipe = Recipe.load(ROOT / "recipes" / "city_shimonoseki-2.yaml")
    res = build(src, recipe, [_doc("city_shimonoseki-2", _fixture("t519_shimonoseki-2_item.html"))])
    assert len(res.animals) == 1
    a = res.animals[0]
    assert {k: a.get(k) for k in ("species", "management_no", "name", "sex", "age", "breed", "color", "size", "shelter_date", "image_url")} == {
        "species": "cat", "management_no": "R08-1002", "name": "オセロ", "sex": "オス(去勢)", "age": "不明", "breed": "雑種",
        "color": "白グレー", "size": "成猫", "shelter_date": "令和8年3月4日",
        "image_url": "https://www.city.shimonoseki.lg.jp/uploaded/image/67944.JPG"}
    assert a["note"] == "猫白血病ウイルス・猫エイズウイルス検査:陰性"


def test_shimonoseki_follow_selector_takes_item_links_not_guidance_pages():
    # 一覧の個体ページへのリンクだけ辿る（譲渡手続きの案内 1784・1803 は辿らない）。404 の古いリンクは skip_errors で捨てる
    recipe = Recipe.load(ROOT / "recipes" / "city_shimonoseki-2.yaml")
    sel = recipe.steps[0]["follow_all"].split("@")[0]
    soup = BeautifulSoup(_fixture("t519_shimonoseki-2_list.html"), "lxml")
    hrefs = {a["href"] for a in soup.select(sel)}
    assert {"/soshiki/52/139221.html", "/soshiki/52/139223.html", "/soshiki/52/139222.html",
            "/soshiki/52/159343.html", "/soshiki/52/159346.html"} <= hrefs
    assert not any(h.endswith(("/1784.html", "/1803.html")) for h in hrefs)
    assert len(hrefs) == 9   # 実在 5 + 404 の 4
    assert recipe.steps[0]["skip_errors"] is True


def test_shimonoseki_1_and_3_zero_days_are_zero_not_failed():
    for slug, name in (("city_shimonoseki-1", "t519_shimonoseki-1_empty.html"), ("city_shimonoseki-3", "t519_shimonoseki-3_empty.html")):
        recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
        res = build(_source(slug), recipe, [], [_doc(slug, _fixture(name))])
        assert res.animals == [], slug
        assert res.empty_confirmed, slug


def test_shimonoseki_3_zero_day_is_not_confirmed_when_the_related_list_has_content():
    # 関連情報の見出しの下にリンクが足された日に、リンク先が読めなければ「0 頭」と言い切らない（読めなかった扱いで通知に載る）
    recipe = Recipe.load(ROOT / "recipes" / "city_shimonoseki-3.yaml")
    base = _fixture("t519_shimonoseki-3_empty.html")
    assert "<p>\xa0</p>" in base
    html = base.replace("<p>\xa0</p>", '<p><a href="/soshiki/52/999999.html">迷い犬の情報</a></p>')
    res = build(_source("city_shimonoseki-3"), recipe, [], [_doc("city_shimonoseki-3", html)])
    assert res.animals == [] and not res.empty_confirmed
