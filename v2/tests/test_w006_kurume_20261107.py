"""W006 久留米市（環境省リンク集にあって台帳に無かった自治体）の追加（2026-11-07・ネットワークなし）。

city_kurume-1（保護犬・猫の情報）: 0 頭の日は「現在お迎えを待っている犬・猫はいません。」が出る。子のいる日（Wayback 2020〜2024 の 4 版）には出ない。
  子は h3「保護犬猫番号…・保護日…」の下に p が並ぶ。
city_kurume-2（犬・猫の譲渡）: h3「譲渡犬猫番号…」の下に写真・基本情報。「新しい飼い主さんが決まりました」の子は載せない。
  0 頭の日は「現在、譲渡対象の犬猫はおりません。」（Wayback 2026-03-11）。子のいる日（今日・Wayback 2021-08-14）には出ない。
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

STRAY_ZERO = "w006_city_kurume-1_zero_20261107.html"
STRAY_CHILD = {
    "w006_city_kurume-1_wb20201029.html": ["2037", "2038"],
    "w006_city_kurume-1_wb20210715.html": ["3012"],
    "w006_city_kurume-1_wb20231128.html": ["5015"],
    "w006_city_kurume-1_wb20240520.html": ["6003"],
}
ADOPT_TODAY = "w006_city_kurume-2_child_20261107.html"
ADOPT_WB2021 = "w006_city_kurume-2_wb20210814.html"
ADOPT_ZERO = "w006_city_kurume-2_zero_wb20260311.html"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry_entries():
    for slug, kind in (("city_kurume-1", "stray"), ("city_kurume-2", "adoption")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.kind == kind and s.prefecture == "福岡県"
        assert s.phone == "0942-30-1500"
        assert s.photo == "pending"  # 写真の規約は未確認


def test_stray_zero_day_is_empty():
    assert _zero(_single("city_kurume-1", _fx(STRAY_ZERO)))


def test_stray_child_days_read_and_never_zero():
    for name, nos in STRAY_CHILD.items():
        c = _single("city_kurume-1", _fx(name))
        assert c.status == "ok", (name, c.error)
        assert c.result is not None
        assert [a["management_no"] for a in c.result.animals] == nos, name
        assert _hits("city_kurume-1", _fx(name)) == [], name


def test_stray_child_fields():
    c = _single("city_kurume-1", _fx("w006_city_kurume-1_wb20240520.html"))
    a = c.result.animals[0]
    assert a["sex"] == "メス"
    assert a["shelter_date"] and "令和" in a["shelter_date"]
    assert "久留米市国分町" in (a.get("note") or "")


def test_stray_structure_change_is_not_zero():
    # h3 の見出しの語が変わって行が取れなくなった子のいる日は、0 頭にしない（文言も出ていない）
    html = _fx("w006_city_kurume-1_wb20240520.html").replace("保護犬猫番号", "保護動物ID")
    assert not _zero(_single("city_kurume-1", html))


def test_adoption_today_reads_four_and_skips_decided():
    c = _single("city_kurume-2", _fx(ADOPT_TODAY))
    assert c.status == "ok", c.error
    nos = [a["management_no"] for a in c.result.animals]
    assert nos == ["J8014、J8015", "J8013", "J8008、J8009、J8010", "J8005"]
    assert _hits("city_kurume-2", _fx(ADOPT_TODAY)) == []
    one = {a["management_no"]: a for a in c.result.animals}["J8013"]
    assert one["sex"] == "オス" and one["species"] == "cat" and one["color"] == "キジトラ"


def test_adoption_2021_layout_reads_and_skips_decided():
    c = _single("city_kurume-2", _fx(ADOPT_WB2021))
    assert c.status == "ok", c.error
    nos = [a["management_no"] for a in c.result.animals]
    assert nos == ["J3003", "J3004", "J3005", "J3006", "J3007"]  # J3001 は「決まりました」
    assert _hits("city_kurume-2", _fx(ADOPT_WB2021)) == []


def test_adoption_zero_day_is_empty():
    assert _zero(_single("city_kurume-2", _fx(ADOPT_ZERO)))


def test_adoption_structure_change_is_not_zero():
    html = _fx(ADOPT_TODAY).replace("譲渡犬猫番号", "譲渡動物ID")
    assert not _zero(_single("city_kurume-2", html))
