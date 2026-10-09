"""T519 グループ7: 鳥取市・呉市・下関市・大分県・宮崎県・鹿児島県のレシピ（ネットワークなし）。

fixture は実ページ（2026-10-05 取得）から本文だけを抜いたもの。動物が載った日の読み方は、実ページに無い日の分を
手で組み替えた HTML（コメントで「組み替え」と書く）で確かめている。
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
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


# --- 鳥取市 迷い犬猫収容情報（-1） --------------------------------------------------------------------
def _tottori1_add_row(html: str, caption: str, cells: list[str]) -> str:
    """組み替え: 表（caption）の最後に 1 行足す（実ページは 2026-10-05 に猫 1 頭だけ）。"""
    soup = BeautifulSoup(html, "lxml")
    table = next(t for t in soup.select("table") if t.select_one("caption").get_text(strip=True) == caption)
    tr = soup.new_tag("tr")
    for c in cells:
        td = soup.new_tag("td")
        td.string = c
        tr.append(td)
    (table.select_one("tbody") or table).append(tr)
    return str(soup)


def test_tottori_1_today_is_one_cat_with_number_from_the_note():
    res = _run("city_tottori-1", _fixture("t519_tottori-1.html"))
    assert len(res.animals) == 1
    assert _pick(res.animals[0], "species", "management_no", "shelter_date", "location", "breed", "color", "sex", "age") == {
        "species": "cat", "management_no": "TC53", "shelter_date": "9月11日", "location": "鳥取市滝山",
        "breed": "雑種", "color": "茶白", "sex": "オス", "age": "7歳程度"}
    assert len(res.dropped) == 5   # 他の 5 表は空白だけの行


def test_tottori_1_blank_rows_only_is_zero_not_failed():
    html = BeautifulSoup(_fixture("t519_tottori-1.html"), "lxml")
    for tr in html.select("tr:has(td)"):
        if "収容猫TC53" in tr.get_text():
            tr.decompose()
    res = _run("city_tottori-1", str(html))
    assert res.animals == [] and res.empty_confirmed


def test_tottori_1_species_comes_from_the_table_caption():
    # 組み替え: 表1 犬・表4 犬（年齢と体格の列が逆）・表3 その他の動物
    html = _fixture("t519_tottori-1.html")
    html = _tottori1_add_row(html, "表1", ["9月20日", "鳥取市湖山", "柴", "茶", "オス", "中", "5歳", "赤", "読取なし", "", "収容犬TD7"])
    html = _tottori1_add_row(html, "表4", ["9月21日", "岩美町", "雑種", "黒", "メス", "3歳", "小", "なし", "", ""])
    html = _tottori1_add_row(html, "表3", ["9月22日", "鳥取市", "ウサギ", "白", "不明", "小", "不明", "なし", "", ""])
    res = _run("city_tottori-1", html)
    by = {a["shelter_date"]: a for a in res.animals}
    assert by["9月20日"]["species"] == "dog" and by["9月20日"]["management_no"] == "TD7"
    assert by["9月21日"]["species"] == "dog" and by["9月21日"]["age"] == "3歳"
    assert by["9月22日"]["species"] == "other"
    assert all(a["species"] is not None for a in res.animals)


# --- 鳥取市 譲渡情報（-2・-3） -------------------------------------------------------------------------
def test_tottori_2_adoption_rows_include_trial_and_take_photo_and_number():
    # 2026-10-07 おまえさん方針: トライアル中の子も載せる（以前は捨てていた）。空白だけの行 1 つだけ捨てる
    res = _run("city_tottori-2", _fixture("t519_tottori-2.html"))
    assert len(res.animals) == 18
    assert [a["species"] for a in res.animals].count("dog") == 5
    assert [a["species"] for a in res.animals].count("cat") == 13
    assert all(a["image_url"] and a["management_no"] for a in res.animals)
    chibi = res.animals[0]
    assert _pick(chibi, "name", "sex", "age", "breed", "color", "management_no") == {
        "name": "チビ", "sex": "メス", "age": "18歳", "breed": "雑種", "color": "茶", "management_no": "R7−TD25"}
    assert len(res.dropped) == 1


def test_tottori_3_other_animals_table_is_blank_today_so_zero():
    res = _run("city_tottori-3", _fixture("t519_tottori-2.html"))
    assert res.animals == [] and res.empty_confirmed
