"""T519 G4: 藤沢市（収容犬）のレシピ（ネットワークなし）。

fixture は実ページ（2026-10-06 の取得）の本文 div#tmp_contents。0 頭の日（赤字「【現在、収容犬はありません】」）の実物。
動物が載った日の読み方（表でなく「<strong>収容犬1</strong>収容日：…<br>…」の裸の文字）は Wayback の 2020 年の保存ページで確かめた
（tests/test_recipes_t519v_g4b.py）。ここの最後のテストは、動物が載った日の作りが外れたら 0 頭に見せず「読めなかった」にすることを確かめる。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SLUG = "city_fujisawa-1"


def _run(html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == SLUG)
    recipe = Recipe.load(ROOT / "recipes" / f"{SLUG}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fixture() -> str:
    return (FIX / "t519_fujisawa-1_20261006.html").read_text(encoding="utf-8")


ZERO = "<p><span class=\"txt_big\"><strong><span class=\"txt_red\">【現在、収容犬はありません】</span></strong></span></p>"


def test_registry_entry():
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == SLUG)
    assert (src.kind, src.species, src.mode, src.prefecture, src.phone) == ("sheltered", "dog", "recipe", "神奈川県", "0466-50-3594")


def test_zero_day_is_zero_not_failed():
    res = _run(_fixture())
    assert res.animals == [] and res.empty_confirmed


def test_an_animal_day_in_an_unexpected_shape_is_failed_not_zero():
    # 「収容日：」の p でも表でもない書き方（読み方が外れた日）は 0 頭に見せない = 「読めなかった」通知。
    # （「収容日：…」の p は読める = tests/test_recipes_t519v_g4b.py の藤沢市の保存ページ 6 通り）
    html = _fixture().replace(ZERO, "<div>収容日 令和8年10月6日 収容場所 鵠沼海岸 犬種 柴</div>")
    res = _run(html)
    assert res.animals == [] and not res.empty_confirmed
