"""W006 朝の直し 2026-11-25: 0:05 の収集で新しく読めなくなった 3 つと、0 頭の監査（ops/audit_empty.py）で当たった 2 つ（ネットワークなし）。

fixture は実ページから script・style を落としたもの（名前は w006_<slug>_<状態>_<日付>.html）。
- 札幌市 迷子猫（city_sapporo-2）: 11/13〜11/24 のホームページ改装で表（h2 + table）が div.col2 に変わり、行が 0 になった
- 愛媛県（pref_ehime-1）: 0 頭の文が「現在迷い犬猫情報はありません」（読点なし）に変わった。捨てた 1 行は値が「―」の雛形
- 鹿児島県 犬（pref_kagoshima-1）: 残っているのが「帰りました」の子だけの日。text_lacks は行を数える前に落とすので「0 行・捨てた 0」になり、0 頭の根拠が無かった
- 佐賀県 鳥栖（pref_saga-2）・札幌市 迷子犬（city_sapporo-1）: 子のいる日にも 0 頭の文が出る（audit_empty が当たった）
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import build, empty_hits
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _recipe(slug: str) -> Recipe:
    return Recipe.load(ROOT / "recipes" / f"{slug}.yaml")


def _doc(html: str) -> Doc:
    return Doc(url=SOURCES_URL, html=html, soup=BeautifulSoup(html, "lxml"))


SOURCES_URL = "https://example.jp/p.html"


def _build(slug: str, html: str):
    return build(SOURCES[slug], _recipe(slug), [_doc(html)])


def _hits(slug: str, html: str):
    return empty_hits(_recipe(slug), [_doc(html)])


# --- 札幌市 迷子猫（city_sapporo-2） ----------------------------------------------------------------------------------
SAPPORO2 = "city_sapporo-2"


def test_sapporo_2_renewed_page_reads_the_cat():
    res = _build(SAPPORO2, _fx("w006_city_sapporo-2_cat_20261125.html"))
    assert len(res.animals) == 1 and not res.empty_confirmed
    a = res.animals[0]
    assert a["species"] == "cat"
    assert a["management_no"] == "LC081120-01"
    assert a["shelter_date"] == "令和8年11月20日"
    assert a["location"] == "南区澄川4条6丁目6付近"
    assert a["color"] == "キジトラ" and a["sex"] == "メス" and a["size"] == "中"
    assert a["image_url"].endswith("/images/68127/lc081120-01_1.jpeg")


def test_sapporo_2_old_template_pages_are_still_read_as_before():
    res = _build(SAPPORO2, _fx("w006_city_sapporo-2_20261107.html"))
    assert len(res.animals) >= 1
    zero = _build(SAPPORO2, _fx("w006_city_sapporo-2_zero_20261113.html"))
    assert zero.animals == [] and zero.empty_confirmed and zero.empty_evidence == "empty_text"


def test_sapporo_2_poster_image_after_the_cat_is_not_a_second_cat():
    res = _build(SAPPORO2, _fx("w006_city_sapporo-2_cat_20261125.html"))
    assert all("shitsunaigai" not in a["image_url"] for a in res.animals)


# --- 愛媛県（pref_ehime-1） -------------------------------------------------------------------------------------------
EHIME = "pref_ehime-1"


def test_ehime_zero_day_without_comma_is_zero():
    res = _build(EHIME, _fx("w006_pref_ehime-1_zero_20261125.html"))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_text"
    assert len(res.dropped) == 1   # 値が「―」だけの雛形の行（子ではない）


def test_ehime_day_with_a_dog_has_no_zero_evidence():
    html = _fx("w006_pref_ehime-1_dog_20261117.html")
    assert _hits(EHIME, html) == []
    res = _build(EHIME, html)
    assert len(res.animals) == 1 and res.animals[0]["species"] == "dog"


def test_ehime_zero_sentence_gone_is_not_zero():
    html = _fx("w006_pref_ehime-1_zero_20261125.html")
    changed = html.replace("現在迷い犬猫情報はありません", "お知らせ")
    assert changed != html
    res = _build(EHIME, changed)
    assert res.animals == [] and not res.empty_confirmed


# --- 鹿児島県 犬（pref_kagoshima-1） ----------------------------------------------------------------------------------
KAGO1 = "pref_kagoshima-1"


def test_kagoshima_1_only_returned_dogs_left_is_zero():
    # 結果は「2 件」だが 2 件とも「無事に…帰りました」。0 頭の根拠は「除外語の無い子が 1 頭もいない」（empty_absent）
    res = _build(KAGO1, _fx("w006_pref_kagoshima-1_all_returned_20261125.html"))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_kagoshima_1_live_dog_next_to_returned_ones_is_still_read_and_not_zero():
    html = _fx("w006_pref_kagoshima-1_one_live_20261124.html")
    assert _hits(KAGO1, html) == []
    res = _build(KAGO1, html)
    assert [a["management_no"] for a in res.animals] == ["26D0325"] and not res.empty_confirmed


def test_kagoshima_1_result_table_renamed_is_not_zero():
    html = _fx("w006_pref_kagoshima-1_all_returned_20261125.html").replace("t-jouto", "t-renamed")
    res = _build(KAGO1, html)
    assert res.animals == [] and not res.empty_confirmed


def test_kagoshima_1_returned_word_changed_on_a_dog_is_not_zero():
    # 除外語が別の言い方に変わった子（読めている）は 0 頭の根拠にならない（動物として載る）
    html = _fx("w006_pref_kagoshima-1_all_returned_20261125.html").replace("おうちに帰りました", "おうちで暮らしています")
    res = _build(KAGO1, html)
    assert len(res.animals) == 2 and not res.empty_confirmed


# --- 佐賀県 鳥栖（pref_saga-2） ---------------------------------------------------------------------------------------
SAGA2 = "pref_saga-2"
SAGA_ZERO = ["t631_pref_saga-3_zero_20261106.html", "t631_pref_saga-3_zero_wb20260712.html"]   # 同じ雛形（事務所違い）


def test_saga_2_dog_day_has_no_zero_evidence_though_blank_tables_say_it():
    html = _fx("w006_pref_saga-2_kids_20261125.html")
    assert html.count("現在保護情報はありません") == 2   # 猫と保護動物の空の表
    assert _hits(SAGA2, html) == []
    res = _build(SAGA2, html)
    assert len(res.animals) == 1 and not res.empty_confirmed


@pytest.mark.parametrize("name", SAGA_ZERO)
def test_saga_2_zero_day_is_confirmed_by_no_photo_in_any_table(name):
    res = _build(SAGA2, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_saga_2_table_class_renamed_is_not_zero():
    html = _fx(SAGA_ZERO[0]).replace("__wys_table", "renamed_table")
    res = _build(SAGA2, html)
    assert not res.empty_confirmed


def test_saga_2_recipe_has_no_sentence_based_zero():
    r = _recipe(SAGA2)
    assert not r.empty_text and not r.empty_text_all


# --- 札幌市 迷子犬（city_sapporo-1） ----------------------------------------------------------------------------------
SAPPORO1 = "city_sapporo-1"
SAPPORO1_ZERO = [
    "w006_city_sapporo-1_zero_20261106.html",
    "w006_city_sapporo-1_zero_wb20250621.html",
    "w006_city_sapporo-1_zero_wb20251118.html",
]


def test_sapporo_1_dog_under_the_zero_heading_has_no_zero_evidence():
    # 2026-11-25: 迷子犬の見出しが「現在迷子犬は収容されていません」のまま、下の表に子（柴犬）が入っている
    html = _fx("w006_city_sapporo-1_dog_20261125.html")
    assert "現在迷子犬は収容されていません" in html
    assert _hits(SAPPORO1, html) == []
    res = _build(SAPPORO1, html)
    assert len(res.animals) == 1 and not res.empty_confirmed
    assert res.animals[0]["breed"] == "柴犬"


def test_sapporo_1_dog_whose_table_cannot_be_read_is_not_zero():
    # 表の作りが変わって行が取れなくなっても、写真が残っていれば 0 頭にしない
    html = _fx("w006_city_sapporo-1_dog_20261125.html").replace("<table", "<section").replace("</table", "</section")
    res = _build(SAPPORO1, html)
    assert res.animals == [] and not res.empty_confirmed


@pytest.mark.parametrize("name", SAPPORO1_ZERO)
def test_sapporo_1_zero_days_in_every_observed_wording_are_zero(name):
    res = _build(SAPPORO1, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_sapporo_1_last_ok_day_with_management_number_heading_is_not_zero():
    html = _fx("w006_city_sapporo-1_last_ok_20261105.html")
    assert _hits(SAPPORO1, html) == []
    assert len(_build(SAPPORO1, html).animals) == 1


def test_sapporo_1_zero_sentence_gone_is_not_zero():
    html = _fx("w006_city_sapporo-1_zero_20261106.html")
    changed = html.replace("現在迷子犬は収容されていません", "お知らせ")
    assert changed != html
    res = _build(SAPPORO1, changed)
    assert res.animals == [] and not res.empty_confirmed
