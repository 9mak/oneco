"""W006 T624・T631: 2026-11-07 に落ちた おおいた動物愛護センター（oita_aigo-1）・広島市 迷子猫（city_hiroshima-2）の 0 頭の日（ネットワークなし）。

oita_aigo-1: 0 頭の日は一覧の器 div.information_block が空（コメントと空白だけ）になり、文言は出ない。子のいる日は器に information_box が入る。
city_hiroshima-2: 0 頭の日は dd が全部 &nbsp; だけの雛形 dl が 2 つ残る。子のいる日は 1 つの dl の dd に値が入る。
どちらも「子のいる日には成立しない」根拠（器が空・全 dd が空）で 0 頭にする。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

OITA_ZERO = "w006_oita_aigo-1_zero_20261107.html"
OITA_CHILD = "w006_oita_aigo-1_child_20261106.html"
OITA_CHILD_WB = "w006_oita_aigo-1_wb20260712.html"
HIRO_ZERO = "w006_city_hiroshima-2_zero_20261107.html"
HIRO_CHILD = "w006_city_hiroshima-2_child_20261106.html"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_oita_zero_day_is_empty():
    assert _zero(_single("oita_aigo-1", _fx(OITA_ZERO)))


def test_oita_child_days_still_read_and_never_zero():
    for name in (OITA_CHILD, OITA_CHILD_WB):
        c = _single("oita_aigo-1", _fx(name))
        assert c.status == "ok", (name, c.error)
        assert c.result is not None and len(c.result.animals) == 1
        assert _hits("oita_aigo-1", _fx(name)) == []


def test_oita_structure_change_is_not_zero():
    # 器の名前が変わった（器が無い）日は 0 頭にしない
    html = _fx(OITA_ZERO).replace("information_block", "information_wrap")
    assert not _zero(_single("oita_aigo-1", html))


def test_hiroshima_zero_day_is_empty():
    assert _zero(_single("city_hiroshima-2", _fx(HIRO_ZERO)))


def test_hiroshima_child_day_still_read_and_never_zero():
    c = _single("city_hiroshima-2", _fx(HIRO_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None
    assert [a["management_no"] for a in c.result.animals] == ["8-10-10"]
    assert _hits("city_hiroshima-2", _fx(HIRO_CHILD)) == []


def test_hiroshima_structure_change_is_not_zero():
    # dd が無くなった（作りが変わった）日は 0 頭にしない
    html = _fx(HIRO_ZERO).replace("<dd", "<span").replace("</dd>", "</span>")
    assert not _zero(_single("city_hiroshima-2", html))
