"""T519 グループ7: 大分県 西部・北部・豊後高田の保護情報（pref_oita-1・-2・-3）。fixture は 2026-10-05 の div#main_body。

-2・-3 は 2026-10-05 に保護中の子が 1 頭も載っていない（返還済みと空の雛形だけ）。動物が載った日は、雛形の表に値を入れた組み替え HTML で確かめる。
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(slug: str, html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _fill_template(html: str, marker: str, values: dict[str, str]) -> str:
    """組み替え: marker（管理番号 or 見出し）を含む空の雛形の表に、項目名の隣のセルへ値を入れる。"""
    soup = BeautifulSoup(html, "lxml")
    table = next(t for t in soup.select("table") if marker in t.get_text())
    for td in table.select("td"):
        label = td.get_text(strip=True).replace(" ", "").replace("　", "")
        if label in values:
            nxt = td.find_next_sibling("td")
            nxt.clear()
            nxt.string = values[label]
    return str(soup)


def test_oita_1_seibu_takes_the_one_dog_and_drops_templates_and_returned():
    res = _run("pref_oita-1", _fixture("t519_oita_seibu.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert {k: a.get(k) for k in ("species", "shelter_date", "age", "location", "color", "breed", "size", "sex", "note", "image_url")} == {
        "species": "dog", "shelter_date": "令和 8年 9月 14日", "age": "5歳", "location": "九重町 町田", "color": "白・茶",
        "breed": "雑種", "size": "中", "sex": "オス", "note": "左耳の先が切れている。白いビニール紐付き",
        "image_url": "https://www.pref.oita.jp/uploaded/image/2087538.JPG"}
    reasons = [d.reason for d in res.dropped]
    assert sum("見つかりました" in r for r in reasons) == 3   # 返還済み（成猫の 1 頭を含む）は載せない
    assert sum("shelter_date" in r for r in reasons) == 2     # 空の雛形（保護日時が空。保護場所に市の名前だけが入る日があるので、日付の有無で見分ける）


def test_oita_1_without_the_dog_is_zero_not_failed():
    html = re.sub(r"令和\s*8年\s*9月\s*14日", "", _fixture("t519_oita_seibu.html"))   # 保護日時が空 = 雛形
    res = _run("pref_oita-1", html)
    assert res.animals == [] and res.empty_confirmed


def test_oita_2_hokubu_today_is_zero_and_confirmed():
    res = _run("pref_oita-2", _fixture("t519_oita_hokubu.html"))
    assert res.animals == [] and res.empty_confirmed
    assert len(res.dropped) == 6   # 返還済み 1 + 空の雛形 5


def test_oita_2_hokubu_filled_template_is_read_with_number_and_inferred_species():
    # 組み替え: 空の雛形 a-791 に値を入れた日
    html = _fill_template(_fixture("t519_oita_hokubu.html"), "a-791", {
        "保護日時": "令和8年10月2日", "推定年齢": "3歳", "保護場所": "中津市中央町", "毛色": "白", "種類": "柴", "毛の長さ": "短毛",
        "大きさ": "中", "首輪": "赤", "性別": "オス", "その他": "リードあり"})
    res = _run("pref_oita-2", html)
    assert len(res.animals) == 1
    a = res.animals[0]
    assert {k: a.get(k) for k in ("management_no", "species", "shelter_date", "location", "breed", "sex")} == {
        "management_no": "a-791", "species": "dog", "shelter_date": "令和8年10月2日", "location": "中津市中央町", "breed": "柴", "sex": "オス"}


def test_oita_3_bungotakada_today_is_zero_and_confirmed():
    res = _run("pref_oita-3", _fixture("t519_oita_bungotakada.html"))
    assert res.animals == [] and res.empty_confirmed
    assert len(res.dropped) == 1


def test_oita_3_bungotakada_filled_template_is_a_dog():
    html = _fill_template(_fixture("t519_oita_bungotakada.html"), "保護・収容しました", {
        "収容日": "令和8年10月3日", "保護場所": "豊後高田市是永町", "種類": "雑種", "性別": "メス"})
    res = _run("pref_oita-3", html)
    assert len(res.animals) == 1
    assert {k: res.animals[0].get(k) for k in ("species", "shelter_date", "location", "sex")} == {
        "species": "dog", "shelter_date": "令和8年10月3日", "location": "豊後高田市是永町", "sex": "メス"}
