"""T519 G4: 川越市・川口市のレシピ（ネットワークなし）。

fixture は実ページの本文（川越: article#content、川口: div#contents-in）だけを抜いたもの（2026-10-05 の取得）。
- t519_kawagoe_hogo_20261005.html: 保護収容動物情報（犬 1 頭・猫 1 頭。city_kawagoe-1・-2 が同じページ）
- t519_kawagoe-3_20261005.html: 譲渡情報（4 頭とも「譲渡が決まりました」・更新日 2024-11-22）
- t519_kawaguchi-2_20261005.html: 譲渡（犬 0 頭・猫 6 頭）
複数頭の日・負傷で写真なしの日・0 頭の日は、実ページの作りを保ったまま書き換えて確かめる（動物が載った日の保存ページが無いため）。
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


KAWAGOE = "t519_kawagoe_hogo_20261005.html"
DOG_LI = "<li>No005　7月21日収容（小仙波）　ビーグル　黒白茶　成犬</li>"
CAT_LI = "<li>No005 8月24日収容（鯨井）　雑種　白に茶混じり　年齢不明</li>"


# --- 川越市 保護収容（犬・猫は同じページの別の節。管理番号 No005 が重なるので slug を分けてある） ---------------------
def test_kawagoe_dog_and_cat_come_from_their_own_sections():
    dog = _run("city_kawagoe-1", _fixture(KAWAGOE))
    cat = _run("city_kawagoe-2", _fixture(KAWAGOE))
    assert [a["species"] for a in dog.animals] == ["dog"]
    assert [a["species"] for a in cat.animals] == ["cat"]
    assert _pick(dog.animals[0], "management_no", "shelter_date", "location", "breed", "color", "age", "image_url") == {
        "management_no": "No005", "shelter_date": "7月21日", "location": "小仙波", "breed": "ビーグル", "color": "黒白茶", "age": "成犬", "image_url": None}
    assert _pick(cat.animals[0], "management_no", "shelter_date", "location", "breed", "color", "age", "image_url") == {
        "management_no": "No005", "shelter_date": "8月24日", "location": "鯨井", "breed": "雑種", "color": "白に茶混じり", "age": "年齢不明", "image_url": None}
    assert dog.animals[0]["id"] != cat.animals[0]["id"]


def test_kawagoe_two_dogs_and_the_injury_note_line_is_not_an_animal():
    # 犬が 2 頭の日・負傷で写真を載せない旨の注記が別の li で付く日
    html = _fixture(KAWAGOE).replace(DOG_LI, DOG_LI + "<li>No006　9月2日収容（的場）　雑種　茶　成犬</li><li>※負傷のため写真は掲載しません。</li>")
    res = _run("city_kawagoe-1", html)
    assert [a["management_no"] for a in res.animals] == ["No005", "No006"]
    assert res.animals[1]["location"] == "的場"
    cat = _run("city_kawagoe-2", html)
    assert [a["management_no"] for a in cat.animals] == ["No005"]


def test_kawagoe_empty_day_is_zero_not_failed():
    # 0 頭の日の文言は 2025 年のアーカイブで確認した「現在、情報はございません。」。犬だけ 0 頭・猫だけ 0 頭の両方
    no_dog = _fixture(KAWAGOE).replace("<ul><li>No005　7月21日収容（小仙波）　ビーグル　黒白茶　成犬</li></ul>", "<p>現在、情報はございません。</p>")
    if no_dog == _fixture(KAWAGOE):  # 元の html の空白の入り方に依らず li を丸ごと置き換える
        soup = BeautifulSoup(_fixture(KAWAGOE), "lxml")
        li = soup.find("li", string=lambda t: t and "7月21日収容" in t)
        li.parent.replace_with(BeautifulSoup("<p>現在、情報はございません。</p>", "lxml").p)
        no_dog = str(soup)
    res = _run("city_kawagoe-1", no_dog)
    assert res.animals == [] and res.empty_confirmed
    assert len(_run("city_kawagoe-2", no_dog).animals) == 1


def test_kawagoe_missing_section_is_failed_not_zero():
    # 節が無くなった日（構造が変わった日）は 0 頭に見せない
    html = _fixture(KAWAGOE).replace("保護犬情報", "保護している犬")
    res = _run("city_kawagoe-1", html)
    assert res.animals == [] and not res.empty_confirmed


# --- 川越市 譲渡 -----------------------------------------------------------------------------------------------
def test_kawagoe_3_all_decided_is_zero():
    res = _run("city_kawagoe-3", _fixture("t519_kawagoe-3_20261005.html"))
    assert res.animals == [] and res.empty_confirmed


def test_kawagoe_3_new_animal_without_decided_mark_is_read_with_photo_and_species_from_h3():
    html = _fixture("t519_kawagoe-3_20261005.html")
    mark = '<p><strong class="red">譲渡が決まりました</strong></p>'
    i = html.find("R5―猫No19")
    j = html.find(mark, i)
    html = html[:j] + html[j + len(mark):]
    res = _run("city_kawagoe-3", html)
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "management_no", "species", "breed", "color", "age") == {
        "management_no": "R5―猫No19", "species": "cat", "breed": "雑種", "color": "ムギワラ", "age": "不明"}
    assert a["image_url"].endswith("/993/dsc02437.jpg")


# --- 川口市 譲渡 -----------------------------------------------------------------------------------------------
def test_kawaguchi_2_reads_six_cats_and_no_dog():
    res = _run("city_kawaguchi-2", _fixture("t519_kawaguchi-2_20261005.html"))
    assert [a["management_no"] for a in res.animals] == ["R8-0007", "R8-0009", "R8-0010", "R8-0011", "R8-0019", "R8-0021"]
    assert {a["species"] for a in res.animals} == {"cat"}
    assert all(a["image_url"] and a["image_url"].startswith("https://www.city.kawaguchi.lg.jp/material/images/") for a in res.animals)
    first = res.animals[0]
    assert _pick(first, "sex", "age", "breed") == {"sex": "オス", "age": "4歳齢", "breed": "雑種(キジ白)"}
    assert first["note"].startswith("好奇心旺盛で")
    assert res.dropped == []


def test_kawaguchi_2_dog_section_is_not_mistaken_for_an_animal_and_dogs_get_species_dog():
    # 犬の節に 1 頭載った日（同じ div.cmstag の作り）。種別は直前の h3
    html = _fixture("t519_kawaguchi-2_20261005.html")
    one = BeautifulSoup(html, "lxml").select("div.cmstag")[0]
    dog = str(one).replace("R8-0007", "R8-0100").replace("雑種（キジ白）", "柴犬").replace("photo_20260615-104725.jpg", "dog_0100.jpg")
    html = html.replace("<p>現在、譲渡対象の犬はおりません。</p>", dog)
    res = _run("city_kawaguchi-2", html)
    assert res.animals[0]["species"] == "dog" and res.animals[0]["management_no"] == "R8-0100"
    assert [a["species"] for a in res.animals[1:]] == ["cat"] * 6


def test_kawaguchi_2_cat_zero_day_uses_the_cat_sentence_only():
    html = _fixture("t519_kawaguchi-2_20261005.html")
    soup = BeautifulSoup(html, "lxml")
    for d in soup.select("div.cmstag"):
        d.decompose()
    plain = str(soup)
    res = _run("city_kawaguchi-2", plain)
    assert res.animals == [] and not res.empty_confirmed  # 猫の 0 頭の文言が無い日は読めなかった扱い
    res = _run("city_kawaguchi-2", plain.replace("</h3>", "</h3>", 1).replace("現在、譲渡対象の犬はおりません。", "現在、譲渡対象の犬はおりません。現在、譲渡対象の猫はおりません。"))
    assert res.animals == [] and res.empty_confirmed


# city_kawaguchi-1 は T519 検証 g4a で link_only → recipe（子ページのリンクを辿る・empty_absent）に切り替えた。
# 読み方のテストは test_recipes_t519v_g4a.py。
