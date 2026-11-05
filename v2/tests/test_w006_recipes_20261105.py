"""W006 T624 見守り運転: 2026-11-05 の収集で読めなかった掲載元のレシピの直し（ネットワークなし）。

fixture は実ページから script・style を落としたもの。名前は w006_<slug>_<状態>_<日付>.html（zero はその日の 0 頭、last_ok は直前まで正常に読めた日）。
- 千葉市 迷子猫（city_chiba-2）: 0 頭の日の h4 が「現在、迷い猫の情報はありません。」に変わり、empty_text が当たらず failed だった
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str):
    src = SOURCES[slug]
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


# --- 千葉市 迷子猫（city_chiba-2） ----------------------------------------------------------------------------------
# 11/05 の 0 頭の日は div#contents_editable が h4「現在、迷い猫の情報はありません。」と、値の無い雛形の p だけ（迷子犬 city_chiba-1 と同じ書き方）。
# 市は 0 頭の書き方を何度も変えている（Wayback 2023-02「ただいま迷い猫の情報はありません。」、2025-02「現在迷い猫の情報はありません。」）。
CHIBA2 = "city_chiba-2"
CHIBA2_ZERO = ["w006_city_chiba-2_zero_20261105.html", "w006_city_chiba-2_zero_wb20250218.html", "w006_city_chiba-2_zero_wb20230220.html"]
CHIBA2_KIDS = ["w006_city_chiba-2_last_ok_20261104.html", "t518_chiba-2.html", "t518_chiba-2_wb20250911.html", "t518_chiba-2_wb20260417.html"]


@pytest.mark.parametrize("name", CHIBA2_ZERO)
def test_chiba_2_zero_days_in_every_observed_wording_are_zero(name):
    res = _run(CHIBA2, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_text"


def test_chiba_2_today_zero_page_has_the_empty_template_row_that_is_dropped():
    # 値の無い雛形の p が行になるが、写真も管理番号も収容日も無いので動物にならない（0 頭の根拠は文言）
    res = _run(CHIBA2, _fx("w006_city_chiba-2_zero_20261105.html"))
    assert len(res.dropped) == 1


def test_chiba_2_zero_sentence_gone_is_not_zero():
    html = _fx("w006_city_chiba-2_zero_20261105.html")
    changed = html.replace("現在、迷い猫の情報はありません。", "お知らせ")
    assert changed != html
    assert "迷い猫の情報はありません" not in _text(changed)
    res = _run(CHIBA2, changed)
    assert res.animals == [] and not res.empty_confirmed


def test_chiba_2_template_only_page_without_a_sentence_is_not_zero():
    # 2024-11-14 型（文言が無く雛形だけ）は 0 頭と言い切れない: failed のまま
    html = _fx("w006_city_chiba-2_zero_20261105.html")
    changed = html.replace("現在、迷い猫の情報はありません。", "")
    assert changed != html and "迷い猫の情報はありません" not in _text(changed)
    res = _run(CHIBA2, changed)
    assert res.animals == [] and not res.empty_confirmed


def test_chiba_2_last_ok_day_is_read_as_before():
    res = _run(CHIBA2, _fx("w006_city_chiba-2_last_ok_20261104.html"))
    assert len(res.animals) == 1 and not res.empty_confirmed
    assert _pick(
        res.animals[0], "management_no", "image_url", "species", "shelter_date", "location", "breed", "color", "sex", "size"
    ) == {
        "management_no": "26102701",
        "image_url": None,
        "species": "cat",
        "shelter_date": "令和8年10月27日(火)",
        "location": "稲毛区宮野木町",
        "breed": "雑種",
        "color": "グレー",
        "sex": "オス",
        "size": "小",
    }


@pytest.mark.parametrize(("name", "count"), [
    ("w006_city_chiba-2_last_ok_20261104.html", 1),
    ("t518_chiba-2.html", 2),
    ("t518_chiba-2_wb20250911.html", 2),
    ("t518_chiba-2_wb20260417.html", 4),
])
def test_chiba_2_days_with_cats_keep_their_count_and_never_show_a_zero_sentence(name, count):
    # 子のいる日に 0 頭の文言が出ないこと（出ると、子がいるのに行の読み方が崩れた日が 0 頭に見える）
    html = _fx(name)
    recipe = Recipe.load(ROOT / "recipes" / f"{CHIBA2}.yaml")
    text = _text(html)
    assert recipe.empty_text and all(t not in text for t in recipe.empty_text)
    res = _run(CHIBA2, html)
    assert len(res.animals) == count and not res.empty_confirmed
