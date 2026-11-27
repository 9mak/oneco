"""わんにゃぴあ秋田の公開停止中の代わりに、秋田県のサイト（美の国あきたネット）の譲渡犬・譲渡猫の 2 ページを足す（2026-11-27 おまえさんの決定）。

ワンニャピアあきた（spec_wannyapia_akita-1・2）は 2026-11-26 から全ページが「サイト公開停止のお知らせ」。県のサイトの
pages/archive/100841（譲渡犬）・100815（譲渡猫）は 1 頭 = 1 つの表（caption が個体No.・th が名前）。ネットワークなし。
fixture は 2026-11-27 の実ページの本文（個人の名前・電話・メールなし）。
"""

from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW = {d["slug"]: d for d in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]}
URL = {
    "pref_akita-2": "https://www.pref.akita.lg.jp/pages/archive/100841",
    "pref_akita-3": "https://www.pref.akita.lg.jp/pages/archive/100815",
}


def _run(slug: str, html: str):
    src = SOURCES[slug]
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("slug", list(URL))
def test_new_sources_are_adoption_recipes_with_photos_held(slug: str) -> None:
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.kind, s.photo) == ("recipe", True, "adoption", "pending")
    assert s.url == URL[slug]
    assert s.phone == "018-827-5051"
    assert s.address == "〒010-1211 秋田県秋田市雄和椿川字奥椿岱1番地"
    # 電話は掲載元のページの問い合わせ欄、所在地はそのページから案内される「秋田県動物愛護センターについて」で確かめた
    assert s.verified_phone_url == URL[slug]
    assert s.verified_address_url == "https://www.pref.akita.lg.jp/pages/archive/41009"
    assert (ROOT / s.recipe).exists()


def test_species_follow_the_page() -> None:
    assert SOURCES["pref_akita-2"].species == "dog"
    assert SOURCES["pref_akita-3"].species == "cat"


@pytest.mark.parametrize("slug", list(URL))
def test_note_says_why_added_and_to_stop_when_wannyapia_returns(slug: str) -> None:
    note = RAW[slug]["note"]
    assert "公開停止" in note and "二重" in note and "enabled: false" in note
    assert "spec_wannyapia_akita" in note


def test_wannyapia_entries_are_left_as_they_were() -> None:
    for slug in ("spec_wannyapia_akita-1", "spec_wannyapia_akita-2"):
        s = SOURCES[slug]
        assert (s.mode, s.enabled, s.photo) == ("recipe", True, "pending")
        assert s.url.startswith("https://wannyapia.akita.jp/pages/protective-")


def test_discover_known_lists_the_new_slugs_as_covered() -> None:
    known = yaml.safe_load((ROOT / "registry" / "discover_known.yaml").read_text(encoding="utf-8"))
    row = known["domains"]["pref.akita.lg.jp"]
    assert row["status"] == "covered"
    assert {"pref_akita-2", "pref_akita-3"} <= set(row["slugs"])


def test_dog_page_reads_one_dog_from_the_table() -> None:
    res = _run("pref_akita-2", _fixture("w006_pref_akita-2_20261127.html"))
    assert (res.docs, res.rows, len(res.animals), len(res.dropped)) == (1, 1, 1, 0)
    a = res.animals[0]
    assert (a["name"], a["management_no"], a["species"], a["sex"], a["age"], a["color"], a["size"]) == (
        "デンチ",
        "18",
        "dog",
        "オス",
        "2~5歳",
        "茶色系",
        "約9.7kg",
    )
    assert "混合ワクチン" in a["note"]
    assert a["source_url"] == URL["pref_akita-2"]


def test_cat_page_reads_each_table_as_one_cat() -> None:
    res = _run("pref_akita-3", _fixture("w006_pref_akita-3_20261127.html"))
    assert (res.rows, len(res.animals), len(res.dropped)) == (3, 3, 0)
    got = {a["management_no"]: (a["name"], a["sex"], a["age"], a["color"], a["size"]) for a in res.animals}
    assert got == {
        "327": ("リース", "メス", "3か月齢", "茶白", "約1.2kg"),
        # 値が「メ」「ス」の 2 行に割れて書かれている行も 1 つの値にまとまる
        "247": ("紅はるか", "メス", "6か月", "黒白", "約2.5kg"),
        "217": ("しまじろう", "オス (去勢済み)", "4~6歳", "キジ白", "約4.1kg"),
    }
    assert {a["species"] for a in res.animals} == {"cat"}
    assert len({a["id"] for a in res.animals}) == 3


def test_page_without_tables_is_not_read_as_zero_animals() -> None:
    # 0 頭の日の書き方は未確認（方針 52）。表が 0 個の日は 0 頭と確定せず、読めなかった扱いにする
    html = "<html><body><article class='page-contents'><div class='page-body'><p>ここでは新しい家族を募集中の犬について紹介しております。</p></div></article></body></html>"
    res = _run("pref_akita-2", html)
    assert res.animals == [] and not res.empty_confirmed
