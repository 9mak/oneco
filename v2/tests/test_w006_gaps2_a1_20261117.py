"""W006 T640 掲載漏れ 2 回目 A-1: 福山市・水戸市・尼崎市・那覇市・宇都宮市・東大阪市の譲渡ページ（2026-11-17・ネットワークなし）。

台帳には同じ自治体の迷子・収容のページしか無く、里親募集（譲渡）のページが抜けていた。
- 福山市: 里親募集中の犬（今日 36 頭）・猫（今日 0 頭。「現在、譲渡対象の猫はいません。」は子のいる日にも…は確かめられないので文言を根拠にしない）
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


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 福山市 ---------------------------------------------------------------
FUK_DOG, FUK_CAT = "city_fukuyama-3", "city_fukuyama-4"


def test_fukuyama_registry():
    for slug, species in ((FUK_DOG, "dog"), (FUK_CAT, "cat")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "広島県", slug
        assert s.species == species and s.phone == "084-970-1201" and s.address, slug
        assert s.photo == "ok", slug  # 福山市の規約は無断転載禁止のみ（T630 の規約確認）
        assert s.recipe_path.exists(), slug


def test_fukuyama_dog_today_reads_36():
    c = _run(FUK_DOG, _fx("w006_city_fukuyama-3_20261117.html"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 36 and not c.result.dropped
    first = animals[0]
    assert (first["management_no"], first["name"], first["sex"], first["breed"], first["color"], first["age"]) == (
        "1-25", "かず", "オス", "雑種", "白黒", "3才齢")
    assert first["species"] == "dog" and first["image_url"] and "1匹で保護されました" in first["note"]
    assert len({a["id"] for a in animals}) == 36 and all(a["image_url"] for a in animals)
    assert _hits(FUK_DOG, _fx("w006_city_fukuyama-3_20261117.html")) == []


def test_fukuyama_dog_other_day_in_wayback():
    html = _fx("w006_city_fukuyama-3_child_wb20260602.html")
    c = _run(FUK_DOG, html)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 15 and c.result.animals[0]["management_no"] == "1-12"
    assert _hits(FUK_DOG, html) == []


def test_fukuyama_cat_today_is_zero():
    html = _fx("w006_city_fukuyama-4_20261117.html")
    assert "現在、譲渡対象の猫はいません" in html
    assert _zero(_run(FUK_CAT, html))


def test_fukuyama_cat_zero_day_in_wayback_is_zero_without_the_sentence():
    # 2026-03 の 0 頭の日は「現在、譲渡対象の猫はいません」の文が無く表も無い → 文言でなく表の有無で 0 頭を決める
    html = _fx("w006_city_fukuyama-4_zero_wb20260314.html")
    assert "譲渡対象の猫はいません" not in html
    assert _zero(_run(FUK_CAT, html))


def test_fukuyama_cat_child_days_in_wayback_never_zero():
    for name, n, first in (("w006_city_fukuyama-4_child_wb20251113.html", 4, "フ7-11"),
                           ("w006_city_fukuyama-4_child_wb20251008.html", 9, "フ7-11")):
        html = _fx(name)
        c = _run(FUK_CAT, html)
        assert c.status == "ok", (name, c.error)
        assert len(c.result.animals) == n and c.result.animals[0]["management_no"] == first, name
        assert all(a["species"] == "cat" and a["image_url"] for a in c.result.animals), name
        assert _hits(FUK_CAT, html) == [], name


def test_fukuyama_structure_change_is_not_zero():
    html = _fx("w006_city_fukuyama-4_child_wb20251113.html").replace("里親募集の犬猫の情報", "里親募集の動物")
    assert not _zero(_run(FUK_CAT, html))
    html = _fx("w006_city_fukuyama-3_20261117.html").replace("里親募集の犬猫の情報", "里親募集の動物")
    assert not _zero(_run(FUK_DOG, html))
