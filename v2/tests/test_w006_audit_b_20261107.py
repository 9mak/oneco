"""W006 全ページ監査 B 班（2026-11-07）: 取りこぼし・区分や種別の誤り・値の取り違えの直し（ネットワークなし）。

fixture は実ページから script・style を落としたもの（名前は w006_<slug>_<状態>_<日付>.html）。
- 札幌市 迷子猫（city_sapporo-2）: 市が写真のファイル名を打ち間違える（見出し LC081104-01 の写真が lc081104-03_1.jpeg）ので、管理番号は写真でなく見出しから読む
- 船橋市 譲渡可能犬猫（city_funabashi-2）: 猫の表は見出しが「毛色」、犬の表は見出し行が無く 2 列目が種類。列の意味は表の見出しに従う
- 大分県 北部（pref_oita-2）: 公式が項目名を「種茶」と誤記（種類の取り違え）。品種が空で、柴の語もあるのに種別が決まらなかった
- 山口県（pref_yamaguchi）: 周南 8-3-120〜123 は本文に「この犬は、…」とあるのに種別なしだった
- 滋賀県（spec_sapca）: 種類が「シーズー」だけの子が種別なしだった
- 福井県（fapscsite-2）: 見出しの管理番号が「HC26251.253.254(柳町)、HC26266(市姫)」と 2 つ並ぶ子の後ろ半分が欠けていた
- 長崎犬猫ネット（animal_net_nagasaki-1〜4）: 犬猫の別を「柄が三毛…なら猫、それ以外は犬」で決めていたため、猫を犬と表示していた。
  サイト自身の絞り込み（?animal-type=dog|cat|others）で入口を分けて種別を決める
- 岩手県 県央・宮古: 迷子の節（元の飼主さんを探しています）を譲渡の slug から分け（kennan-2・miyako-2）、行の取りこぼし・写真の取り違えを直す
- 福山市 迷い猫（city_fukuyama-2）: 同じ市の迷い犬（-1）と同じ stray に揃える
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str, url: str | None = None):
    src = SOURCES[slug]
    recipe = Recipe.load(ROOT / src.recipe)
    return build(src, recipe, [Doc(url=url or src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _by(res, key: str) -> dict:
    return {a[key]: a for a in res.animals}


# --- 札幌市 迷子猫・迷子犬 --------------------------------------------------------------------------------------------


def test_sapporo_2_management_no_comes_from_the_heading_not_the_photo_file_name():
    res = _run("city_sapporo-2", _fx("w006_city_sapporo-2_20261107.html"))
    assert [a["management_no"] for a in res.animals] == ["LC081104-01", "LC081102-01"]


def test_sapporo_2_ids_and_photos_do_not_change():
    # ID は写真から決まる。写真の取り違え（市の打ち間違い）は掲載元のとおりで、変えない
    res = _run("city_sapporo-2", _fx("w006_city_sapporo-2_20261107.html"))
    assert [a["id"] for a in res.animals] == ["de5facd50eac", "c0b5d73773fe"]
    assert res.animals[0]["image_url"].endswith("/lc081104-03_1.jpeg")


def test_sapporo_1_dog_page_also_reads_the_heading():
    res = _run("city_sapporo-1", _fx("w006_city_sapporo-1_last_ok_20261105.html"))
    assert res.animals
    for a in res.animals:
        assert a["management_no"] and a["management_no"] == a["management_no"].upper()


# --- 船橋市 譲渡可能犬猫 ----------------------------------------------------------------------------------------------


def test_funabashi_2_cat_table_second_column_is_color_dog_table_is_breed():
    res = _run("city_funabashi-2", _fx("w006_city_funabashi-2_20261107.html"))
    by = _by(res, "id")
    dog = by["da4fb41ca554"]
    assert dog["species"] == "dog" and dog["breed"] == "ミックス (チワワ系)" and dog.get("color") is None
    cats = [a for a in res.animals if a["species"] == "cat"]
    assert len(cats) == 4
    assert {a["color"] for a in cats} == {"三毛", "サバ", "子猫"}
    assert all(a.get("breed") is None for a in cats)


def test_funabashi_2_ids_do_not_change():
    res = _run("city_funabashi-2", _fx("w006_city_funabashi-2_20261107.html"))
    assert sorted(a["id"] for a in res.animals) == sorted(
        ["da4fb41ca554", "0c8e623c8975", "7858ce1cae9a", "5082e9749497", "ea8c33bb21d9"]
    )


# --- 大分県 北部 ------------------------------------------------------------------------------------------------------


def test_oita_2_misspelled_label_is_read_as_breed_and_dog_is_inferred():
    res = _run("pref_oita-2", _fx("w006_pref_oita-2_20261107.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["id"] == "3482eed2b210"
    assert a["breed"] == "雑種(シバ)" and a["species"] == "dog"


# --- 山口県 周南 ------------------------------------------------------------------------------------------------------


def _yamaguchi():
    html = _fx("w006_pref_yamaguchi_10022_20261107.html")
    return _by(_run("pref_yamaguchi", html, url="https://www.pref.yamaguchi.lg.jp/site/doubutuaigo/10022.html"), "management_no")


def test_yamaguchi_text_saying_this_dog_decides_species():
    by = _yamaguchi()
    for no in ("8-3-120", "8-3-121", "8-3-122", "8-3-123"):
        assert by[no]["species"] == "dog", no


def test_yamaguchi_rows_without_any_evidence_stay_unknown():
    by = _yamaguchi()
    assert by["8-3-119"]["species"] is None and by["8-3-124"]["species"] is None


# --- 滋賀県 ----------------------------------------------------------------------------------------------------------


def test_sapca_shih_tzu_is_a_dog():
    res = _run("spec_sapca", _fx("w006_spec_sapca_22141_20261107.html"), url="https://www.sapca.jp/lost/22141.html")
    assert len(res.animals) == 1 and res.animals[0]["breed"] == "シーズー"
    assert res.animals[0]["species"] == "dog"


# --- 福井県 ----------------------------------------------------------------------------------------------------------


def test_fapscsite_2_reads_both_management_numbers_of_a_two_group_entry():
    res = _run("fapscsite-2", _fx("w006_fapscsite-2_p2_20261107.html"))
    nos = {a["management_no"] for a in res.animals}
    assert "HC26251.253.254、HC26266" in nos


def test_fapscsite_2_single_group_entries_are_unchanged():
    res = _run("fapscsite-2", _fx("w006_fapscsite-2_p2_20261107.html"))
    nos = {a["management_no"] for a in res.animals}
    assert {"FC26024", "SC26011", "HC25258"} <= nos


# --- 福山市 ----------------------------------------------------------------------------------------------------------


def test_fukuyama_kinds_match_between_dog_and_cat():
    assert SOURCES["city_fukuyama-1"].kind == "stray"
    assert SOURCES["city_fukuyama-2"].kind == "stray"


# --- 長崎犬猫ネット --------------------------------------------------------------------------------------------------

NAG = "https://animal-net.pref.nagasaki.jp"
NAG3_IDS = {"20155": "4992ed3e17c6", "20152": "254b214e9398", "20108": "d522eb420bdb", "20106": "c323d04c225c", "20102": "a599d0618f8d"}


def _nag3_pages(dog_html: str | None = None) -> dict[str, str]:
    pages = {
        f"{NAG}/maigo/?animal-type=dog": dog_html or _fx("w006_animal_net_nagasaki-3_list_dog_20261107.html"),
        f"{NAG}/maigo/?animal-type=cat": _fx("w006_animal_net_nagasaki-3_list_cat_20261107.html"),
        f"{NAG}/maigo/?animal-type=others": _fx("w006_animal_net_nagasaki-3_list_others_20261107.html"),
    }
    for no in NAG3_IDS:
        pages[f"{NAG}/animal/no-{no}/"] = _fx(f"w006_animal_net_nagasaki-3_no{no}_20261107.html")
    return pages


def _nag3(pages: dict[str, str]):
    return collect_one(SOURCES["animal_net_nagasaki-3"], FakeFetcher(pages))


def test_nagasaki_3_species_follows_the_sites_own_animal_type_list():
    c = _nag3(_nag3_pages())
    assert c.status == "ok", c.error
    by = _by(c.result, "management_no")
    assert set(by) == set(NAG3_IDS)
    # 20106 は品種「日本ねこ」、20155・20108 は柄・品種に猫の手がかりが無い猫。以前は犬と表示していた
    assert {a["species"] for a in by.values()} == {"cat"}


def test_nagasaki_3_ids_do_not_change():
    c = _nag3(_nag3_pages())
    assert {a["management_no"]: a["id"] for a in c.result.animals} == NAG3_IDS


def test_nagasaki_3_a_child_on_the_dog_list_is_a_dog():
    # 犬の一覧に載った子は、柄や品種に関係なく犬（一覧の URL が根拠）。同じ子が猫の一覧に無いときだけ成り立つ作りの確認
    pages = _nag3_pages(dog_html=_fx("w006_animal_net_nagasaki-3_list_cat_20261107.html"))
    pages[f"{NAG}/maigo/?animal-type=cat"] = _fx("w006_animal_net_nagasaki-3_list_dog_20261107.html")
    c = _nag3(pages)
    assert c.status == "ok", c.error
    assert {a["species"] for a in c.result.animals} == {"dog"}


def test_nagasaki_3_all_three_lists_empty_is_zero():
    empty = _fx("w006_animal_net_nagasaki-3_list_dog_20261107.html")
    pages = {f"{NAG}/maigo/?animal-type={t}": empty for t in ("dog", "cat", "others")}
    c = _nag3(pages)
    assert c.status == "empty" and c.result.animals == []


def test_nagasaki_3_a_failing_list_is_not_zero():
    pages = _nag3_pages()
    del pages[f"{NAG}/maigo/?animal-type=others"]
    c = _nag3(pages)
    assert c.status == "failed"


@pytest.mark.parametrize("slug", ["animal_net_nagasaki-1", "animal_net_nagasaki-2", "animal_net_nagasaki-3", "animal_net_nagasaki-4"])
def test_nagasaki_family_never_defaults_to_dog(slug):
    text = (ROOT / "recipes" / f"{slug}.yaml").read_text(encoding="utf-8")
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    assert recipe.species.get("from") == "parent_url"
    assert '"": dog' not in text
    assert len(recipe.urls) == 3 and all("animal-type=" in u for u in recipe.urls)
    assert validate_recipe_dict(
        __import__("yaml").safe_load(text), SOURCES[slug].url
    ) == []


# --- 岩手県 県央 -----------------------------------------------------------------------------------------------------

KENNAN = "w006_pref_iwate_kennan_20261107.html"


def test_kennan_adoption_cats_keep_their_own_photos():
    res = _run("pref_iwate_kennan", _fx(KENNAN))
    by = _by(res, "name")
    sabu = by["(左)三郎、(右)二郎"]
    assert sabu["image_url"].endswith("/2026.10.14.jpg")
    assert len(res.animals) == 8 and not any(a["management_no"] == "26040" for a in res.animals)


def test_kennan_adoption_other_ids_do_not_change():
    res = _run("pref_iwate_kennan", _fx(KENNAN))
    ids = {a["name"]: a["id"] for a in res.animals}
    assert ids["ゴロさん"] == "7b41311f4aa6" and ids["レオン"] == "8753afc2f959" and ids["ルビー"] == "66f4d2c67735"


def test_kennan_2_reads_the_stray_dog_section():
    assert SOURCES["pref_iwate_kennan-2"].kind == "stray"
    res = _run("pref_iwate_kennan-2", _fx(KENNAN))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["management_no"] == "26040" and a["species"] == "dog" and a["breed"] == "柴犬"
    assert a["image_url"].endswith("/2026.11.4.jpg")
    assert a["location"] == "紫波町彦部一ノ沢" and a["shelter_date"].startswith("令和8年11月4日")
    assert a["kind"] == "stray"


def test_kennan_2_zero_day_is_zero_only_when_the_whole_stray_section_is_gone():
    soup = BeautifulSoup(_fx(KENNAN), "lxml")
    h2 = next(h for h in soup.find_all("h2") if "飼主さんを探しています" in h.get_text())
    for sib in list(h2.find_next_siblings()):
        if sib.name == "h2":
            break
        sib.decompose()
    h2.decompose()
    res = _run("pref_iwate_kennan-2", str(soup))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_kennan_2_reworded_heading_or_missing_frame_is_not_zero():
    # 見出しの言い回しが変わっても行（保護日時の p）は読める
    html = _fx(KENNAN).replace("元の飼主さんを探しています（迷子犬猫情報）", "迷子の犬猫")
    assert len(_run("pref_iwate_kennan-2", html).animals) == 1
    # 本文の枠（h1）が無い日（ブロック画面・作り替え）は 0 頭にしない
    soup = BeautifulSoup(_fx(KENNAN), "lxml")
    for t in soup.find_all(["h2", "p"]):
        if t.name == "h2" or "保護日時" in t.get_text() or t.find("img"):
            t.decompose()
    for h1 in soup.find_all("h1"):
        h1.decompose()
    res = _run("pref_iwate_kennan-2", str(soup))
    assert res.animals == [] and not res.empty_confirmed


# --- 岩手県 宮古 -----------------------------------------------------------------------------------------------------

MIYAKO = "w006_pref_iwate_miyako_20261107.html"


def test_miyako_adoption_keeps_the_cat_whose_note_mentions_the_adopted_sibling():
    res = _run("pref_iwate_miyako", _fx(MIYAKO))
    by = _by(res, "management_no")
    assert "2026-9-067C" in by
    assert by["2026-9-067C"]["name"] == "てんや君"
    assert by["2026-9-067C"]["image_url"].endswith("/tenyawanya.jpg")


def test_miyako_adoption_excludes_the_stray_and_the_reports_of_adoption():
    res = _run("pref_iwate_miyako", _fx(MIYAKO))
    nos = {a["management_no"] for a in res.animals}
    assert "2026-10-074C" not in nos
    for closed in ("2026-8-061D", "2026-8-061C", "2026-8-052C", "2026-8-062C", "2026-5-026C", "2026-8-063C", "2026-8-053C"):
        assert closed not in nos
    assert len(res.animals) == 13
    assert {a["kind"] for a in res.animals} == {"adoption"}


def test_miyako_adoption_ids_do_not_change():
    res = _run("pref_iwate_miyako", _fx(MIYAKO))
    ids = {a["management_no"]: a["id"] for a in res.animals}
    assert ids["2026-8-060C"] == "5c77954138df" and ids["R7-159-17-3"] == "34b660f3a2b4"


def test_miyako_2_stray_cat_with_place_and_date():
    assert SOURCES["pref_iwate_miyako-2"].kind == "stray"
    res = _run("pref_iwate_miyako-2", _fx(MIYAKO))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["management_no"] == "2026-10-074C" and a["species"] == "cat" and a["kind"] == "stray"
    assert a["location"] == "上閉伊郡山田町豊間根(国道45号豊間根バス停付近)"
    assert a["shelter_date"] == "令和8年10月8日"
    assert a["image_url"].endswith("/20261008.jpg")


def test_miyako_2_zero_day_when_the_stray_section_is_gone():
    soup = BeautifulSoup(_fx(MIYAKO), "lxml")
    h2 = next(h for h in soup.find_all("h2") if "【保護】" in h.get_text())
    for sib in list(h2.find_next_siblings()):
        if sib.name == "h2":
            break
        sib.decompose()
    h2.decompose()
    res = _run("pref_iwate_miyako-2", str(soup))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_absent"


# --- エンジン: 追加したキーの検査 ------------------------------------------------------------------------------------


def test_new_recipe_keys_pass_the_strict_schema():
    base = {"rows": "tr", "urls": ["https://example.jp/a?x=1", "https://example.jp/a?x=2"],
            "species": {"from": "parent_url", "map": {"x=1": "dog"}},
            "image": {"selector": "img@src", "scope": "prev_siblings", "stop_at": "row, h2"},
            "fields": {"color": {"selector": "td:nth-of-type(2)", "if_header": "毛色"},
                       "breed": {"selector": "td:nth-of-type(2)", "unless_header": "毛色"}}}
    assert validate_recipe_dict(base, "https://example.jp/a") == []
    assert validate_recipe_dict({**base, "urls": ["javascript:alert(1)"]}, "https://example.jp/a") != []
    assert validate_recipe_dict({**base, "empty_text_entries": ["投稿がありません"]}, "https://example.jp/a") == []
    assert validate_recipe_dict({**base, "empty_text_entries": [""]}, "https://example.jp/a") != []


# --- 0 頭の根拠が子のいる日に成り立たないこと（audit_empty と同じ観点） ---------------------------------------------------


def _hits(slug: str, html: str):
    from collector.extract import empty_hits

    src = SOURCES[slug]
    recipe = Recipe.load(ROOT / src.recipe)
    d = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return empty_hits(recipe, [d], [d])


def test_no_zero_evidence_on_the_child_days_of_the_split_iwate_slugs():
    assert _hits("pref_iwate_kennan-2", _fx(KENNAN)) == []
    assert _hits("pref_iwate_miyako-2", _fx(MIYAKO)) == []


def test_nagasaki_entries_rule_does_not_fire_on_a_child_day():
    from collector.extract import empty_hits
    from collector.recipe import Executor

    src = SOURCES["animal_net_nagasaki-3"]
    recipe = Recipe.load(ROOT / src.recipe)
    ex = Executor(FakeFetcher(_nag3_pages()), recipe)
    docs = ex.resolve(src.url)
    assert empty_hits(recipe, list(docs) + ex.visited, docs) == []
