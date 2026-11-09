"""W006 2026-11-10 0:05 の収集で新しく読めなかった 3 件（ネットワークなし）。

- 寝屋川市（city_neyagawa-1）: 収容の子が初めて載った日の作りは表ではなく p の箇条書き（「1.引取り又は収容の場所：…」）。
  本番の AI 修復が出した案（draft PR #115）を実ページで確かめ、項目の読み方を採った。0 頭の雛形の日（2023-03）の根拠は残す。
- 千葉市 迷子犬（city_chiba-1）: 0 頭の日の書き方が、h4「現在情報はありません」＋空欄の雛形に変わった。
- 岩手 県央 迷子（pref_iwate_kennan-2）: 0 頭の日も節の見出しが残り、「現在元の飼い主を探している動物はいません。」と出る。
fixture は 2026-11-10 0:05 に取得した実ページ（script・style を落とした）。
"""

from pathlib import Path

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
    recipe = Recipe.load(ROOT / src.recipe)
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


# --- 寝屋川市 ---------------------------------------------------------------------------------------------
def test_neyagawa_reads_the_cat_listed_as_numbered_paragraphs():
    res = _run("city_neyagawa-1", _fx("w006_city_neyagawa-1_20261110.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["species"] == "cat"
    assert a["location"] == "寝屋川市豊里町9-10付近(拾得場所)"
    assert a["shelter_date"] == "11月9日"
    assert a["color"] == "灰色、白(ハチワレ)"
    assert a["sex"] == "去勢雄"
    assert a["size"] == "大(成猫)"
    assert a["note"] == "老齢、黒の首輪"
    assert a["image_url"].endswith("/1109neko2.jpg")


def test_neyagawa_blank_template_day_is_still_a_zero_day():
    res = _run("city_neyagawa-1", _fx("t519v_g1g6_neyagawa1_20230311_template.html"))
    assert res.animals == [] and res.empty_confirmed


# --- 千葉市 迷子犬 ------------------------------------------------------------------------------------------
def test_chiba_city_dog_new_zero_wording_with_blank_template_is_a_zero_day():
    res = _run("city_chiba-1", _fx("w006_city_chiba-1_zero_20261110.html"))
    assert res.animals == [] and res.empty_confirmed


def test_chiba_city_dog_child_days_do_not_contain_the_new_zero_wording():
    for name in ("t518_chiba-1.html", "w006c_city_chiba-1_20261107.html"):
        assert "現在情報はありません" not in _fx(name)
        assert _run("city_chiba-1", _fx(name)).animals


# --- 岩手 県央 迷子 ------------------------------------------------------------------------------------------
def test_kennan_lost_section_with_no_dog_sentence_is_a_zero_day():
    res = _run("pref_iwate_kennan-2", _fx("w006_pref_iwate_kennan_zero_20261110.html"))
    assert res.animals == [] and res.empty_confirmed


def test_kennan_lost_dog_day_still_reads_the_dog():
    html = _fx("w006_pref_iwate_kennan_20261107.html")
    assert "現在元の飼い主を探している動物はいません" not in html
    assert [a["management_no"] for a in _run("pref_iwate_kennan-2", html).animals] == ["26040"]
