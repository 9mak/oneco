"""W006 T620 の後始末: 公開中の誤り・読めているのに抜けている子（2026-11-07。ネットワークなし）。

長野 nagano_hello_animal-1: 0 頭の日の雛形（h3「現在、飼い主募集中の犬はいません」）を 1 頭の犬として載せていた。
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


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 長野 nagano_hello_animal-1 ---------------------------------------------------------------

NAGANO_ZERO = "w006_nagano_hello_animal-1_zero_20261107.html"
NAGANO_CHILD = "w006_nagano_hello_animal-1_child_rearranged.html"


def test_nagano_dog_zero_day_is_empty_not_a_fake_dog():
    c = _single("nagano_hello_animal-1", _fx(NAGANO_ZERO))
    assert _zero(c), (c.status, c.result and c.result.animals)


def test_nagano_dog_child_day_still_read_and_never_zero():
    c = _single("nagano_hello_animal-1", _fx(NAGANO_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["name"], a["breed"], a["color"]) == ("やまと", "ミックス", "薄茶")
    assert a["image_url"].endswith("/images/yamato.jpg")
    assert _hits("nagano_hello_animal-1", _fx(NAGANO_CHILD)) == []


def test_nagano_dog_structure_change_is_not_zero():
    # 雛形の文が変わった（根拠が無い）日は、偽の犬にも 0 頭にもせず「読めなかった」にする
    html = _fx(NAGANO_ZERO).replace("飼い主募集中の犬はいません", "里親募集中の犬は現在おりません")
    assert not _zero(_single("nagano_hello_animal-1", html))
    c = _single("nagano_hello_animal-1", html)
    assert c.status != "ok"


# --- 長野 nagano_hello_animal-2（猫）: 犬ページと同じ雛形が 0 頭の日に出ると推定して同じ型を防ぐ ------------

NAGANO_CAT_CHILD = "w006_nagano_hello_animal-2_child_20261107.html"
NAGANO_CAT_ZERO = "w006_nagano_hello_animal-2_zero_rearranged.html"


def test_nagano_cat_child_day_reads_four_cats():
    c = _single("nagano_hello_animal-2", _fx(NAGANO_CAT_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 4
    assert _hits("nagano_hello_animal-2", _fx(NAGANO_CAT_CHILD)) == []


def test_nagano_cat_placeholder_day_is_empty_not_a_fake_cat():
    c = _single("nagano_hello_animal-2", _fx(NAGANO_CAT_ZERO))
    assert _zero(c), (c.status, c.result and c.result.animals)
