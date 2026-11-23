"""T519 G4: 高崎市 動物愛護センター 8 ページのレシピ（ネットワークなし）。

fixture は実ページ（2026-10-06 の取得）の一覧の table だけを抜いたもの。
- takasaki-1: 保護している犬（1 頭）／ -2: 負傷している猫その他（全部空欄の行が 1 本 = 0 頭）
- takasaki-3: 一般の方が保護している犬（4 頭）／ -4: 同 猫その他（猫 7・インコ・ミドリガメ）
- takasaki-5: 飼い主が探している犬（46 行・2024 年 10 月から）／ -6: 同 猫その他（131 行・2024 年 9 月から）
- takasaki-7: 譲渡予定の犬（3 頭）／ -8: 同 猫（11 頭）
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SITE = "https://www.city.takasaki.gunma.jp"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fixture(n: int) -> str:
    return (FIX / f"t519_takasaki-{n}.html").read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def test_registry_has_eight_takasaki_pages_with_the_right_kinds():
    srcs = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug.startswith("city_takasaki-")}
    assert sorted(srcs) == [f"city_takasaki-{i}" for i in range(1, 9)]
    assert {s.slug: s.kind for s in srcs.values()} == {
        "city_takasaki-1": "sheltered", "city_takasaki-2": "sheltered", "city_takasaki-3": "sheltered", "city_takasaki-4": "sheltered",
        "city_takasaki-5": "lost", "city_takasaki-6": "lost", "city_takasaki-7": "adoption", "city_takasaki-8": "adoption"}
    assert all(s.phone == "027-330-2323" and s.prefecture == "群馬県" and s.mode == "recipe" for s in srcs.values())


def test_sheltered_dog_reads_the_row_with_photo_and_detail_page():
    res = _run("city_takasaki-1", _fixture(1))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "species", "management_no", "shelter_date", "breed", "sex", "location") == {
        "species": "dog", "management_no": "2026-50", "shelter_date": "令和8年10月2日", "breed": "雑種(柴系)", "sex": "オス", "location": "上里見町"}
    assert a["image_url"] == SITE + "/uploaded/image/69400.jpg"
    assert a["source_url"] == SITE + "/page/98346.html"


def test_blank_row_is_zero_not_failed_for_both_sheltered_pages():
    # 負傷猫のページ（2026-10-05 は全部空欄の行が 1 本）。保護犬のページも 0 頭の日は同じ作りと推測しているので同じ表で確かめる
    for slug in ("city_takasaki-1", "city_takasaki-2"):
        res = _run(slug, _fixture(2))
        assert res.animals == [] and res.empty_confirmed, slug


def test_table_with_a_row_that_has_text_but_no_number_is_failed_not_zero():
    # 空欄の行に何か文字が入ったのに管理番号も日付も写真も取れない日（構造が変わった日）は 0 頭に見せない
    html = _fixture(2).replace("\xa0</td>", "調整中</td>", 1)
    assert "調整中" in html
    res = _run("city_takasaki-2", html)
    assert res.animals == [] and not res.empty_confirmed


def test_resident_protected_dogs_split_the_combined_cells():
    res = _run("city_takasaki-3", _fixture(3))
    assert [a["management_no"] for a in res.animals] == ["2026-12", "2026-11", "2026-10", "2026-9"]
    a = res.animals[0]
    assert _pick(a, "species", "kind", "shelter_date", "location", "breed", "sex", "size", "age", "color") == {
        "species": "dog", "kind": "sheltered", "shelter_date": "令和8年9月21日", "location": "中里町", "breed": "雑種", "sex": "オス", "size": "中型",
        "age": "10才", "color": "白が多い"}   # 2026-11-13: 「毛色・首輪」の首輪は備考へ（test_collector_review_20261113.py）
    assert "腫瘍" in a["note"]


def test_resident_protected_cats_and_others_get_other_for_birds_and_turtles():
    res = _run("city_takasaki-4", _fixture(4))
    assert len(res.animals) == 9
    sp = {a["management_no"]: a["species"] for a in res.animals}
    assert sp["2026-16"] == "other" and sp["2026-10"] == "other"      # セキセイインコ・ミドリガメ
    assert sorted(set(sp.values())) == ["cat", "other"] and list(sp.values()).count("cat") == 7
    cat = next(a for a in res.animals if a["management_no"] == "2026-19")
    assert _pick(cat, "breed", "sex", "age", "location", "shelter_date") == {
        "breed": "雑種", "sex": "メス", "age": "1~2ヶ月", "location": "吉井町池", "shelter_date": "令和8年9月29日"}
    assert cat["image_url"] == SITE + "/uploaded/image/69115.jpg"


def test_lost_dogs_keep_every_row_the_page_still_lists_and_take_the_call_name():
    # 方針 31: 掲載元が載せているかぎり載せる（受付の年で切らない）。fixture は 2026-10-06 の実ページで 46 行（2024 年 10 月から）
    res = _run("city_takasaki-5", _fixture(5))
    assert len(res.animals) == 46
    assert all(a["kind"] == "lost" and a["species"] == "dog" for a in res.animals)
    first = res.animals[0]
    assert _pick(first, "management_no", "name", "shelter_date", "location", "breed", "sex", "size", "age") == {
        "management_no": "2026-22", "name": "りま", "shelter_date": "令和8年9月8日", "location": "北群馬郡吉岡町漆原", "breed": "柴", "sex": "オス", "size": "中型", "age": "15才"}
    numbers = [a["management_no"].replace("‐", "-") for a in res.animals]
    assert "2025-48" in numbers and "2025-69" in numbers and len(set(numbers)) == 46
    # 受付が令和7年以前の行も、日付・場所・項目が 1 行ぶんずれずに読める（2025-48 は 2025-10-28 受付）
    old = next(a for a in res.animals if a["management_no"].replace("‐", "-") == "2025-48")
    assert old["shelter_date"].startswith("令和7年") and old["location"] and old["breed"] and old["sex"].startswith(("オス", "メス"))
    assert next(a for a in res.animals if a["management_no"] == "2026-4")["shelter_date"] == "令和7年10月18日"
    # 行方不明が日付の幅で書かれた行（令和8年8月7日～13日）は初日と場所を取る
    wide = next(a for a in res.animals if a["management_no"] == "2026-13")
    assert wide["shelter_date"] == "令和8年8月7日" and wide["location"] == "渋川、高崎周辺"


def test_lost_cats_and_others_keep_every_row_and_birds_are_other():
    res = _run("city_takasaki-6", _fixture(6))
    assert len(res.animals) == 131
    by = {a["management_no"]: a for a in res.animals}
    assert by["2026-56"]["species"] == "cat" and by["2026-56"]["name"] == "リュウ"
    assert by["2026-55"]["species"] == "other" and by["2026-55"]["breed"] == "セキセイインコ"
    assert any(n.startswith("2024") for n in by)
    assert all(a["shelter_date"] and a["management_no"] for a in res.animals)


def test_lost_pages_have_no_year_filter_and_the_header_row_is_not_an_animal():
    for n in (5, 6):
        assert not (Recipe.load(ROOT / "recipes" / f"city_takasaki-{n}.yaml").row_filter or {}).get("text_has_any")
    html = _fixture(5)
    res = _run("city_takasaki-5", html)
    assert len(res.animals) == 46
    # 受付が令和7年だけの日（年を書き換えて再現）も 0 行にならず、全行を読む
    old = _run("city_takasaki-5", html.replace("令和8年", "令和7年"))
    assert len(old.animals) == 46
    # 見出しの行（th だけ）は子に数えない
    assert all(a["management_no"] for a in res.animals) and "受付日時" not in " ".join(a["management_no"] for a in res.animals)


def test_adoption_dogs_and_cats_read_name_photo_detail_and_birth_month():
    dogs = _run("city_takasaki-7", _fixture(7))
    assert [(a["management_no"], a["name"]) for a in dogs.animals] == [("2025-D-60", "まつ"), ("2026-D-14", "シロ"), ("2026-D-18", "くろみ")]
    d = dogs.animals[2]
    assert _pick(d, "species", "kind", "breed", "color", "sex", "age", "note") == {
        "species": "dog", "kind": "adoption", "breed": "柴", "color": "黒", "sex": "メス", "age": "平成25年7月", "note": "腹部にしこり有"}
    assert d["image_url"] == SITE + "/uploaded/image/66595.jpg" and d["source_url"] == SITE + "/page/96186.html"
    cats = _run("city_takasaki-8", _fixture(8))
    assert len(cats.animals) == 11 and cats.animals[0]["name"] == "モッチー" and cats.animals[0]["species"] == "cat"
    assert all(a["image_url"] and a["source_url"].startswith(SITE + "/page/") for a in cats.animals)


def test_lost_row_whose_age_cell_holds_only_an_age_does_not_put_it_in_the_sex():
    # 実ページ（2026-11-23）のアヒル 2 行は 4 列目が「5か月齢」だけ。性別・体格は書かれていないので、年齢だけ取る
    html = _fixture(6)
    cell = BeautifulSoup(html, "lxml").select("tr:has(td)")[0].select("td")[3]
    html = html.replace(str(cell), "<td>5か月齢</td>", 1)
    assert "<td>5か月齢</td>" in html
    first = _run("city_takasaki-6", html).animals[0]
    assert first["sex"] is None and first["size"] is None and first["age"] == "5か月齢"
    normal = _run("city_takasaki-6", _fixture(6)).animals[0]
    assert normal["sex"] and normal["size"] and normal["age"]
