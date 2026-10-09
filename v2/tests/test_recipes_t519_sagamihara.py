"""T519: 相模原市（譲渡対象猫 city_sagamihara-1・収容犬の公示 city_sagamihara-2）のテスト（ネットワークなし）。

fixture は実ページ（2026-10-09 の取得）。本文「現在、10頭の猫たちの新しい飼い主さんを募集しています。」と h3「譲渡対象猫」10 個が一致。
1 頭ごとに h3 → p.imageright（写真）→ p（仮名・種類・性別・毛色・年齢・備考）→ h4「預かりサポーターさんからのメッセージ」→ p が平らに並ぶ。
0 頭の日の文言は未確認なので empty_text は入れず、h3 が無い日は「読めなかった」にする（0 頭に見せない）。
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SLUG = "city_sagamihara-1"


def _src(slug: str):
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(html: str):
    src = _src(SLUG)
    recipe = Recipe.load(ROOT / "recipes" / f"{SLUG}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fixture() -> str:
    return (FIX / "t519_sagamihara-1_20261009.html").read_text(encoding="utf-8")


def test_registry_entries():
    cat = _src("city_sagamihara-1")
    dog = _src("city_sagamihara-2")
    assert (cat.kind, cat.species, cat.mode, cat.prefecture, cat.phone) == ("adoption", "cat", "recipe", "神奈川県", "042-769-8347")
    assert (dog.kind, dog.species, dog.mode, dog.prefecture) == ("stray", "dog", "link_only", "神奈川県")


def test_ten_cats_match_the_page_text():
    html = _fixture()
    (n,) = re.findall(r"現在、(\d+)頭の猫たち", html)
    res = _run(html)
    assert len(res.animals) == int(n) == 10
    assert res.dropped == []
    names = [a["name"] for a in res.animals]
    assert names[0] == "むぎちゃん" and names[-1] == "のんちゃん" and len(set(names)) == 10
    assert all(a["image_url"].startswith("https://www.city.sagamihara.kanagawa.jp/_res/") for a in res.animals)
    assert all(a["sex"] and a["age"] and a["breed"] and a["color"] for a in res.animals)
    mugi = res.animals[0]
    assert (mugi["breed"], mugi["sex"], mugi["color"], mugi["age"]) == ("チンチラ", "メス(避妊手術済み)", "ゴールデン", "2020年頃生まれ")
    assert mugi["note"].startswith("ウイルス検査済(猫エイズ-・猫白血病-)")


def test_each_cat_keeps_only_its_own_block():
    # row_until で次の h2/h3 の手前まで。隣の子の備考や預かりサポーターの文が混ざらない
    res = _run(_fixture())
    sakura = next(a for a in res.animals if a["name"] == "さくらちゃん")
    assert "圧迫排尿" in sakura["note"] and "失明" not in sakura["note"]


def test_a_day_without_h3_is_failed_not_zero():
    # 0 頭の日の文言が分からないので、h3 が消えた日は 0 頭に見せず「読めなかった」にする
    html = re.sub(r"<h3[^>]*>譲渡対象猫</h3>", "", _fixture())
    res = _run(html)
    assert res.animals == [] and not res.empty_confirmed
