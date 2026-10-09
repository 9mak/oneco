"""T519 グループ7: 呉市（city_kure-1・-2）。fixture は 2026-10-05 の jouto.html の本文（div.detail_free）。"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str):
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def test_kure_1_takes_22_dogs_with_photo_name_and_number():
    res = _run("city_kure-1", _fixture("t519_kure-1.html"))
    assert len(res.animals) == 22
    assert all(a["image_url"] and a["name"] and a["management_no"] for a in res.animals)
    first, tenth, last = res.animals[0], res.animals[9], res.animals[-1]
    assert _pick(first, "management_no", "name", "sex", "age", "size", "image_url") == {
        "management_no": "1", "name": "かい", "sex": "雄", "age": "2026年7月頃生まれ(推定)", "size": None,
        "image_url": "https://www.city.kure.lg.jp/uploaded/image/69847.jpg"}
    # No.10 は写真と個体情報が別の p
    assert _pick(tenth, "management_no", "name", "sex", "size", "image_url") == {
        "management_no": "10", "name": "レイ", "sex": "雄", "size": "体重約11kg",
        "image_url": "https://www.city.kure.lg.jp/uploaded/image/68377.jpg"}
    assert _pick(last, "management_no", "name", "sex", "size") == {"management_no": "22", "name": "みちる", "sex": "雄", "size": "体重約15kg"}


def test_kure_1_species_is_not_guessed():
    # 犬猫の別はページに書かれていない。猫と書かれた行だけ猫・他は種別なし（犬を既定にしない）
    html = _fixture("t519_kure-1.html").replace("愛称（仮名）：かい", "愛称（仮名）：かい（猫）")
    res = _run("city_kure-1", html)
    assert res.animals[0]["species"] == "cat"
    assert all(a["species"] is None for a in res.animals[1:])


def test_kure_2_is_a_recipe_source_since_t519v():   # 2026-10-07: Wayback で動物の載る作りが分かったので link_only をやめた（registry_blocks.yaml の city_kure-2 とセット）
    s = _source("city_kure-2")
    assert s.mode == "recipe" and s.kind == "stray" and s.recipe == "recipes/city_kure-2.yaml"
