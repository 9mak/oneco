"""T519: 奈良県 中和保健所動物愛護センター -1（収容犬）・-2（譲渡候補犬）・-3（譲渡候補猫）のレシピ（ネットワークなし）。

fixture は 2026-10-05 の保存 HTML から本文（div#tmp_contents）だけを抜いたもの。
奈良県のサイトは 2026-10 に www.pref.nara.jp（証明書が失効したまま 301 で飛ばすだけ）から www.pref.nara.lg.jp/n070/ に移った。
T519 G5（2026-10-05）は証明書の失効で link_only にしていたが、新ドメインは証明書が有効で収集器が読める（2026-10-07・08 に確認）ので、
台帳の URL を新ドメインにして recipe に戻した（T519v G5）。
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


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_nara_sources_are_recipe_on_the_new_domain():
    for slug, path in (("pref_nara-1", "8439"), ("pref_nara-2", "4132"), ("pref_nara-3", "4133")):
        s = _source(slug)
        assert s.mode == "recipe" and s.prefecture == "奈良県"
        assert s.url == f"https://www.pref.nara.lg.jp/n070/{path}.html"
    assert (_source("pref_nara-1").kind, _source("pref_nara-1").species) == ("stray", "dog")
    assert (_source("pref_nara-2").kind, _source("pref_nara-2").species) == ("adoption", "dog")
    assert (_source("pref_nara-3").kind, _source("pref_nara-3").species) == ("adoption", "cat")


def test_nara_1_zero_dogs_is_empty_not_a_dog():
    # 0 頭の日は値が空の表の雛形（見出しだけ）が残る。動物にならず、「現在、収容中の犬はいません」で empty
    res = _run("pref_nara-1", _fixture("t519_pref_nara-1_empty.html"))
    assert res.animals == []
    assert res.empty_confirmed is True


def test_nara_2_reads_three_adoption_dogs_and_not_the_matching_one():
    res = _run("pref_nara-2", _fixture("t519_pref_nara-2.html"))
    # 2026-10-05 の版は 4 頭。「マッチング中」バナーの下のラッタッタ（相性確認が進んでいて新たな申し込みは受けない）は載せない（猫の -3 と同じ）
    assert [a["name"] for a in res.animals] == ["ジュノ", "ドラ美", "ズーマー"]
    a = res.animals[0]
    assert a["species"] == "dog"
    assert a["image_url"] == "https://www.pref.nara.lg.jp/images/2794/20260924135024.jpg"   # 募集中バナー（jibosyu）でなく犬の写真
    assert (a["breed"], a["color"], a["sex"], a["size"]) == ("雑種", "茶白", "メス", "約11kg")
    assert a["age"] == "2017年8月25日(推定)"
    assert res.dropped == []


def test_nara_3_takes_only_cats_in_1st_and_2nd_recruitment():
    res = _run("pref_nara-3", _fixture("t519_pref_nara-3.html"))
    # 1次募集中 2 頭 + 2次募集中 2 頭。マッチング中（ピノコ・モンステラ）と決まった猫（オーシャン等 17 頭）は載せない
    assert [a["name"] for a in res.animals] == ["クコ", "ミルタス", "レオ", "クレ"]
    assert all(a["species"] == "cat" and a["image_url"] for a in res.animals)
    assert res.dropped == []
