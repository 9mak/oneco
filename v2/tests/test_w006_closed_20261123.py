"""W006 募集を止めた子・決まった子を載せない（POLICY.md 方針 22・21 のうち掲載元ごとのレシピで済むもの。2026-11-23・ネットワークなし）。

fixture は 2026-11-23 の実ページから必要な行だけ残したもの。
- w006_pref_kagoshima-2_20261123.html: 鹿児島県の譲渡犬の結果ページ（本番の保存ページから 3 頭）。26D0244 は備考の頭が「※一時譲渡を取り下げています※」、
  26D0217 は「トライアル（お試し）実施中」（載せる）、26D0239 は普通の行
- w006_city_naha-1_20261123.html: 那覇市の譲渡犬猫（犬 2・猫 2）。「まこ」は写真の枠が「譲渡されました」の画像で、文は「譲渡交渉中」のまま
- 青森市は t519v_g1g6_aomori1_20260205.html（R07-62「ツナ」が「※体調不良のため、譲渡お見合い中止」）と、
  w006_zero_aomori_20261022.html（載っている 3 頭がすべて決まった日の 0 頭）を使う
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
HOST = "http://dogcat.pref.kagoshima.jp"
JOUTO_INDEX = f"{HOST}/Search/Jouto_index"
JOUTO_ACTION = f"{HOST}/Search/Search_jouto"
KAGOSHIMA_JOUTO = ["pref_kagoshima-2", "pref_kagoshima-8", "pref_kagoshima-9", "pref_kagoshima-10", "pref_kagoshima-11", "pref_kagoshima-12"]


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _build(slug: str, html: str):
    src = SOURCES[slug]
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


# --- 鹿児島県 譲渡犬猫: 「一時譲渡を取り下げています」の子は載せない ------------------------------------------
def _kagoshima(slug: str, html: str) -> Collected:
    pages = {JOUTO_INDEX: _fx("w006_pref_kagoshima_jouto_index_20261107.html"), f"{JOUTO_ACTION}#post1": html}
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _nos(c: Collected) -> list[str]:
    assert c.status == "ok", c.error
    assert c.result is not None
    return [a["management_no"] for a in c.result.animals]


def test_kagoshima_2_drops_only_the_withdrawn_dog() -> None:
    # 26D0244 だけが消え、トライアル中の 26D0217 は今までどおり載る（トライアル中の扱いは変えない）
    assert _nos(_kagoshima("pref_kagoshima-2", _fx("w006_pref_kagoshima-2_20261123.html"))) == ["26D0239", "26D0217"]


@pytest.mark.parametrize("slug", KAGOSHIMA_JOUTO)
def test_kagoshima_same_template_recipes_have_the_word(slug: str) -> None:
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    assert recipe.row_filter is not None
    assert recipe.row_filter["field_lacks"] == {"closed": ["譲渡を取り下げ"]}


def test_kagoshima_all_withdrawn_day_is_confirmed_zero_not_failed() -> None:
    rows = _fx("w006_pref_kagoshima-2_20261123.html").split("<hr />")
    only = "<hr />".join([rows[0], rows[-1]])   # 26D0244 の行と、ページの後ろだけ
    assert "26D0239" not in only and "26D0244" in only
    c = _kagoshima("pref_kagoshima-2", only)
    assert c.status == "empty", (c.status, c.error)


def test_kagoshima_without_the_withdrawn_note_the_same_dog_is_listed() -> None:
    html = _fx("w006_pref_kagoshima-2_20261123.html").replace("※一時譲渡を取り下げています※", "")
    assert _nos(_kagoshima("pref_kagoshima-2", html)) == ["26D0244", "26D0239", "26D0217"]


# --- 青森市 譲渡: 「譲渡お見合い中止」の子は載せない -----------------------------------------------------------
AOMORI_FX = "t519v_g1g6_aomori1_20260205.html"


def test_aomori_drops_the_interview_stopped_animal_and_keeps_the_others() -> None:
    res = _build("city_aomori-1", _fx(AOMORI_FX))
    nos = [a["management_no"] for a in res.animals]
    assert "R07-62" not in nos
    assert nos
    assert all("お見合い中止" not in (a["note"] or "") for a in res.animals)


def test_aomori_without_the_note_the_same_animal_is_listed() -> None:
    res = _build("city_aomori-1", _fx(AOMORI_FX).replace("※体調不良のため、譲渡お見合い中止", ""))
    assert "R07-62" in [a["management_no"] for a in res.animals]


def test_aomori_all_rows_adopted_is_still_zero_by_the_container() -> None:
    # 載っている 3 頭がすべて「決まりました」の日（10/22）。お見合い中止の語を足しても 0 頭の確定は今までどおり
    res = _build("city_aomori-1", _fx("w006_zero_aomori_20261022.html"))
    assert res.animals == [] and res.empty_confirmed


def test_aomori_all_rows_interview_stopped_is_zero_by_the_container() -> None:
    html = _fx("w006_zero_aomori_20261022.html").replace("🐾新しい飼い主さんが決まりました。", "※体調不良のため、譲渡お見合い中止")
    res = _build("city_aomori-1", html)
    assert res.animals == [] and res.empty_confirmed
    assert len(res.dropped) == 3


# --- 那覇市 譲渡犬猫: 写真の枠が「譲渡されました」の画像の子は載せない --------------------------------------------
NAHA_FX = "w006_city_naha-1_20261123.html"


def test_naha_drops_the_animal_whose_photo_was_replaced_by_the_adopted_image() -> None:
    res = _build("city_naha-1", _fx(NAHA_FX))
    assert [a["name"] for a in res.animals] == ["フーガ", "平次(へいじ)", "ちよ"]
    assert [a["species"] for a in res.animals] == ["dog", "dog", "cat"]


def test_naha_under_negotiation_with_a_normal_photo_stays_listed() -> None:
    html = _fx(NAHA_FX).replace("joutosaremashita.jpg", "mako.jpg").replace('alt="譲渡されました"', 'alt="まこ"')
    res = _build("city_naha-1", html)
    mako = next(a for a in res.animals if a["name"].startswith("まこ"))
    assert "譲渡交渉中" in mako["note"]
    assert len(res.animals) == 4


@pytest.mark.parametrize(
    "old,new",
    [("joutosaremashita.jpg", "mako.jpg"), ('alt="譲渡されました"', 'alt="まこ"')],
    ids=["by-alt-only", "by-filename-only"],
)
def test_naha_either_the_alt_or_the_filename_alone_drops_the_animal(old: str, new: str) -> None:
    res = _build("city_naha-1", _fx(NAHA_FX).replace(old, new))
    assert not any(a["name"].startswith("まこ") for a in res.animals)


def test_naha_all_adopted_images_day_is_zero() -> None:
    # 4 頭の写真がすべて「譲渡されました」の画像の日
    soup = BeautifulSoup(_fx(NAHA_FX), "lxml")
    for img in soup.select("p.imagecenter img"):
        img["src"] = "joutosaremashita.jpg"
    res = _build("city_naha-1", str(soup))
    assert res.animals == [] and res.empty_confirmed   # 全頭が譲渡済みなら 0 頭が正しい（動物の見出しの器 div#voice が残る）
