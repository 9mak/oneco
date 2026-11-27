"""W006 札幌市 譲渡犬（city_sapporo-3）: 11/24 のホームページ改装で 1 頭分が表から p の並びに変わり、11/26 から 0 頭になった（2026-11-27）。

- 改装後（h2「AD081124-01」→ 写真の p → 「・種類：」などの p → 紹介文の p）の 1 頭を読む。表の版（11/25 の保存ページ）も同じレシピで読む
- 「譲渡されました」「譲渡済」の子は載せない（除外語は減らさない）
- 0 頭の根拠（empty_absent）は /images/ 以下の名前で当て、子のいる日の保存ページには当たらない（#168 reviewer の指摘）
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build, empty_hits
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
DOG = "city_sapporo-3"
RECIPE = Recipe.load(ROOT / "recipes" / f"{DOG}.yaml")
RENEWED = "w006_city_sapporo-3_renewed_20261127.html"
LAST_OK = "w006_city_sapporo-3_last_ok_20261125.html"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _doc(html: str) -> Doc:
    return Doc(url=SOURCES[DOG].url, html=html, soup=BeautifulSoup(html, "lxml"))


def _build(html: str):
    return build(SOURCES[DOG], RECIPE, [_doc(html)])


def _hits(html: str):
    return empty_hits(RECIPE, [_doc(html)])


def test_renewed_page_reads_the_one_dog():
    res = _build(_fx(RENEWED))
    assert len(res.animals) == 1 and not res.empty_confirmed
    a = res.animals[0]
    assert (a["management_no"], a["name"], a["breed"], a["sex"], a["age"], a["size"], a["species"]) == (
        "AD081124-01", "ゆたかちゃん", "雑種", "メス", "推定10歳", "小", "dog")
    assert a["image_url"].endswith("/images/30069/ad081119-01_1.jpg")
    assert a["note"].startswith("小柄で控えめな女の子") and "ゆたかちゃんのペースで" in a["note"]


def test_renewed_page_only_the_dog_is_a_row():
    res = _build(_fx(RENEWED))
    assert res.dropped == []   # 注意事項・体格の表記・即日譲渡不可犬などの h2 は行にならない
    assert all("banner" not in a["image_url"] for a in res.animals)


def test_table_version_last_ok_page_reads_the_same_dog_and_the_note_is_not_empty():
    old = _build(_fx(LAST_OK))
    new = _build(_fx(RENEWED))
    assert len(old.animals) == 1
    keys = ("management_no", "name", "breed", "sex", "age", "size", "image_url")
    assert [old.animals[0][k] for k in keys] == [new.animals[0][k] for k in keys]
    # 備考は今までどおり読む（表の版は 1 つ目の li、改装後は紹介文の p。v4 の「備考が空になる」を起こさない）
    assert old.animals[0]["note"].startswith("小柄で控えめな女の子") and new.animals[0]["note"].startswith(old.animals[0]["note"])


def test_adopted_dog_is_not_listed_in_the_renewed_layout():
    for word in ("譲渡されました（11/27）", "譲渡済"):
        html = _fx(RENEWED).replace("<h2>AD081124-01</h2>", f"<h2>AD081124-01は{word}</h2>")
        assert f"AD081124-01は{word}" in html
        res = _build(html)
        assert res.animals == [] and len(res.dropped) == 1, word


def test_two_dogs_in_the_renewed_layout_are_two_rows_and_the_adopted_one_is_skipped():
    html = _fx(RENEWED)
    block = html[html.index("<h2>AD081124-01</h2>"):html.index("<h2><a id=sokujitsuFuka")]
    second = block.replace("AD081124-01", "AD081126-02").replace("ゆたかちゃん", "はなちゃん").replace("ad081119-01_1", "ad081126-02_1")
    third = block.replace("AD081124-01", "AD081127-03は譲渡されました（11/27）")
    res = _build(html.replace(block, block + second + third))
    assert [a["management_no"] for a in res.animals] == ["AD081124-01", "AD081126-02"]
    assert res.animals[1]["name"] == "はなちゃん" and res.animals[1]["image_url"].endswith("ad081126-02_1.jpg")
    assert len(res.dropped) == 1


def test_empty_absent_does_not_match_the_page_of_a_child_day():
    # 子のいた日の保存ページ（表の版）と改装後のページの両方で、0 頭の根拠（「無い」ことの確認）が崩れて 0 頭と確定しない
    assert _hits(_fx(LAST_OK)) == []
    assert _hits(_fx(RENEWED)) == []
    assert not _build(_fx(LAST_OK)).empty_confirmed


def test_empty_absent_selector_uses_the_name_under_images_not_the_old_path():
    none = RECIPE.empty_absent["none"]
    assert "syuuyou_doubutsu" not in none and "/images/" in none


def test_dog_photo_of_the_renewed_layout_blocks_zero_even_without_a_row():
    # 行が読めなくなっても（項目名が変わるなど）、改装後の画像の道（/images/30069/ad…）の写真があれば 0 頭とは決めない
    res = _build(_fx(RENEWED).replace("種類", "区分"))
    assert res.animals == [] and not res.empty_confirmed
