"""W006 岐阜県（迷い犬情報）spec_pref_gifu: 項目名の字間に空白が入る保健所のページ（2026-11-24・ネットワークなし）。

岐阜保健所（page/6304）は項目名を「管 理 番 号」「収  容  日」「大  き  さ」のように字間に空白（半角と &nbsp; の混在）を
入れて書いていて、レシピの label（管理番号・収容日・大きさ・毛色）に当たらず、管理番号・収容日・毛色・大きさが空で載っていた。
fixture は 2026-11-24 の実ページの本文（見出し・写真・表）だけを抜いたもの。ほかの保健所の読み方が変わらないことは w006c の 2 ページの保存と、今日の実ページ（前後の頭数と項目）で確かめる。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _build(pages: list[tuple[str, str]]):
    recipe = Recipe.load(ROOT / "recipes" / "spec_pref_gifu.yaml")
    docs = [Doc(url=u, html=h, soup=BeautifulSoup(h, "lxml")) for u, h in pages]
    return build(SOURCES["spec_pref_gifu"], recipe, docs, docs)


def test_gifu_label_with_spaces_between_characters_is_read():
    (a,) = _build([("https://www.pref.gifu.lg.jp/page/6304.html", _fx("w006_gifu_6304_20261124.html"))]).animals
    assert a["management_no"] == "11-0003"
    assert a["shelter_date"] == "令和8年11月17日(火曜日)"
    assert a["color"] == "茶"
    assert a["size"] == "中型"
    # もとから読めていた項目は変わらない
    assert (a["breed"], a["sex"], a["age"], a["location"]) == ("柴犬", "おす", "成犬", "(羽島郡)岐南町下印食")


def test_gifu_other_health_centers_are_read_as_before():
    res = _build([
        ("https://www.pref.gifu.lg.jp/page/5229.html", _fx("w006c_gifu_5229_20261107.html")),
        ("https://www.pref.gifu.lg.jp/page/13689.html", _fx("w006c_gifu_13689_20261107.html")),
    ])
    by_loc = {a["location"]: a for a in res.animals}
    assert by_loc["美濃加茂市三和町地内"]["management_no"] == "67-29"
    assert by_loc["美濃加茂市三和町地内"]["color"] == "茶黒白"
    assert by_loc["高山市清見町"]["color"] == "こげ茶"
    assert len(res.animals) == 2
