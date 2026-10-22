"""W006 T624 見守り運転: 2026-10-22 に failed だった 0 頭の日（ネットワークなし）。

fixture は 2026-10-22 の実ページ（script・style を落とした body）。
- w006_zero_funabashi_20261022.html: 船橋 収容犬猫。表は見出し行だけで、0 頭の文言が「※現在公示中の動物はいません。」に変わった
- w006_zero_aomori_20261022.html: 青森市 譲渡。載っている 3 頭がすべて「新しい飼い主さんが決まりました」
- w006_zero_sapca_20261022.html: 滋賀県動物保護管理センター 迷い犬猫。同日の昼前は一覧が無く「只今、迷い犬・猫はいません。」だった（本文を目視）。
  保存前に 1 頭載ったので、17 時台のページの一覧（ul.list）をその文言の p に差し替えて再構成した
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _fx(name: str) -> str:
    return (FIX / f"w006_zero_{name}_20261022.html").read_text(encoding="utf-8")


def _run(slug: str, html: str, follow: bool = False):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    if follow:   # 入口から辿る先が 0 本の日: rows を当てる文書は無く、入口は visited にだけ入る
        return build(src, recipe, [], [doc])
    return build(src, recipe, [doc])


def test_funabashi_new_zero_sentence_confirms_zero():
    res = _run("city_funabashi-1", _fx("funabashi"))
    assert res.animals == [] and res.empty_confirmed


def test_funabashi_zero_sentence_gone_is_not_zero():
    res = _run("city_funabashi-1", _fx("funabashi").replace("現在公示中の動物はいません", "お知らせ"))
    assert res.animals == [] and not res.empty_confirmed


def test_aomori_all_animals_adopted_is_zero_by_the_exclusion():
    res = _run("city_aomori-1", _fx("aomori"))
    assert res.animals == [] and res.empty_confirmed
    assert len(res.dropped) == 3


def test_aomori_animal_not_yet_adopted_is_still_read_with_its_fields():
    html = _fx("aomori").replace("R8-49「とんぼ」</span><br/>🐾新しい飼い主さんが決まりました。", "R8-49「とんぼ」</span>", 1)
    res = _run("city_aomori-1", html)
    assert [(a["management_no"], a["name"], a["breed"], a["color"], a["sex"], a["species"]) for a in res.animals] == [
        ("R8-49", "とんぼ", "MIX", "茶", "オス", "dog")]
    assert res.animals[0]["note"] is None


def test_aomori_list_container_gone_is_not_zero():
    res = _run("city_aomori-1", _fx("aomori").replace("img3lows", "imgrows"))
    assert res.animals == [] and not res.empty_confirmed


def test_sapca_no_list_and_the_zero_sentence_confirms_zero():
    res = _run("spec_sapca", _fx("sapca"), follow=True)
    assert res.animals == [] and res.empty_confirmed


def test_sapca_no_list_without_the_sentence_is_not_zero():
    res = _run("spec_sapca", _fx("sapca").replace("迷い犬・猫はいません", "お知らせ"), follow=True)
    assert res.animals == [] and not res.empty_confirmed
