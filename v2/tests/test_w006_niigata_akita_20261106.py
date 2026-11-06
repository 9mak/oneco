"""W006 T624・T631: 新潟県の新しい書式と、秋田市 迷子（紛失）の 0 頭の根拠（ネットワークなし）。

新潟県（pref_niigata）: 2026-11-06 のページは 1 つの枠に h3（管理番号）で子が並ぶ書式に変わり、「保護した日時：」「動物種：」の形になった。
今までのレシピは h3 に犬・猫がある枠だけを読むので 2 頭を読めず、常に出る案内文で 0 頭と出ていた（T631 で failed にした）。旧書式も読めるようにする。
秋田市（city_akita-2）: 犬の節の「現在、紛失した犬の情報はありません。」は猫のいる日にも出る。犬と猫の両方の文が揃った日だけ 0 頭にする。
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

NIIGATA_OLD = "t631_pref_niigata_children_20261022.html"
NIIGATA_NEW = "t631_pref_niigata_children_20261106.html"
NIIGATA_ZERO = "t631_pref_niigata_zero_wb20260410.html"
AKITA_DOG_ZERO = "w006_city_akita-2_dog_zero_20261106.html"
AKITA_BOTH = "t519v_g2_city_akita-2_today.html"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _by_no(c: Collected) -> dict[str, dict]:
    assert c.result is not None
    return {a["management_no"]: a for a in c.result.animals}


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 新潟県 ---------------------------------------------------------------------------------------------------------
def test_niigata_new_format_reads_every_child_with_official_values():
    c = _single("pref_niigata", _fx(NIIGATA_NEW))
    assert c.status == "ok", c.error
    kids = _by_no(c)
    assert set(kids) == {"26長FC010", "26長MC042"}

    a = kids["26長FC010"]
    assert a["species"] == "cat"
    assert a["shelter_date"] == "2026年11月5日"
    assert a["location"] == "小千谷市旭町甲地内"
    assert a["breed"] == "MIX"
    assert a["color"] == "キジトラ白"
    assert a["sex"] == "メス"
    assert a["size"] == "1.64Kg"
    assert a["image_url"].endswith("/uploaded/image/334685.jpg")
    assert "尾椎骨折" in a["note"] and "人馴れしている" in a["note"]

    b = kids["26長MC042"]
    assert b["species"] == "cat"
    assert b["shelter_date"] == "2026年10月31日"
    assert b["location"] == "長岡市島崎地内"
    assert b["breed"] == "MIX(長毛)"  # 値はエンジンが NFKC で正規化する
    assert b["color"] == "こげ茶"
    assert b["sex"] == "オス(去勢済)"
    assert b["size"] == "4.12Kg"
    assert b["image_url"].endswith("/uploaded/image/334468.jpg")


def test_niigata_new_format_keeps_each_child_apart():
    # 同じ枠に並ぶ 2 頭の値が混ざらない（次の h3 の手前までが 1 頭）
    kids = _by_no(_single("pref_niigata", _fx(NIIGATA_NEW)))
    assert "長岡市" not in kids["26長FC010"]["location"]
    assert "尾椎骨折" not in (kids["26長MC042"].get("note") or "")


def test_niigata_old_format_values_are_unchanged():
    c = _single("pref_niigata", _fx(NIIGATA_OLD))
    assert c.status == "ok", c.error
    kids = _by_no(c)
    assert set(kids) == {"26長FC009"}
    a = kids["26長FC009"]
    assert a["species"] == "cat"
    assert a["shelter_date"] == "10月18日"
    assert a["location"] == "長岡市宮内地内"
    assert a["breed"] == "MIX"
    assert a["sex"] == "オス"
    assert a["color"] == "グレー"
    assert a["size"] == "2.07Kg"
    assert a["image_url"].endswith("/uploaded/image/333417.jpg")


def test_niigata_block_of_return_items_is_not_a_child():
    # 「返還の際に必要な物」の h3 は行にしない
    c = _single("pref_niigata", _fx(NIIGATA_NEW))
    assert c.result is not None
    assert not any("返還の際" in (a.get("management_no") or "") for a in c.result.animals)
    assert len(c.result.animals) == 2


def test_niigata_zero_day_is_still_zero():
    c = _single("pref_niigata", _fx(NIIGATA_ZERO))
    assert _zero(c), c.error
    assert c.result.empty_evidence == "empty_absent"


# --- 秋田市 迷子（紛失） ---------------------------------------------------------------------------------------------
def test_akita_dog_zero_sentence_alone_is_not_evidence():
    html = _fx(AKITA_DOG_ZERO)
    assert "現在、紛失した犬の情報はありません" in html
    assert "現在、紛失した猫の情報は5件です" in html
    assert _hits("city_akita-2", html) == []


def test_akita_dog_zero_day_reads_the_cats():
    c = _single("city_akita-2", _fx(AKITA_DOG_ZERO))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 5
    assert {a["species"] for a in c.result.animals} == {"cat"}


def test_akita_rows_broken_on_dog_zero_day_is_not_zero():
    # 猫の見出しの作りが崩れて行を読めない日に、犬の文だけで 0 頭にしない
    html = _fx(AKITA_DOG_ZERO).replace("<h3>届出番号", "<h4>届出番号")
    assert "<h4>届出番号" in html
    c = _single("city_akita-2", html)
    assert not _zero(c)


def _both_zero(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    voice = soup.select_one("#voice")
    assert voice is not None
    cat_h2 = next(h for h in voice.find_all("h2") if "紛失猫" in h.get_text())
    for sib in list(cat_h2.find_next_siblings()):
        if sib.name == "h2":
            break
        sib.decompose()
    p = soup.new_tag("p")
    p.string = "現在、紛失した猫の情報はありません。"
    cat_h2.insert_after(p)
    return str(soup)


def test_akita_both_sections_zero_is_zero():
    c = _single("city_akita-2", _both_zero(_fx(AKITA_DOG_ZERO)))
    assert _zero(c), c.error
    assert c.result.empty_evidence == "empty_text_all"


@pytest.mark.parametrize("name", [AKITA_BOTH, "t519v_g2_city_akita-2_wb20251112.html"])
def test_akita_days_with_both_kinds_have_no_zero_evidence(name):
    assert _hits("city_akita-2", _fx(name)) == []
