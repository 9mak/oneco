"""W006 T620 の後始末: 公開中の誤り・読めているのに抜けている子（2026-11-07。ネットワークなし）。

長野 nagano_hello_animal-1: 0 頭の日の雛形（h3「現在、飼い主募集中の犬はいません」）を 1 頭の犬として載せていた。
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


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 長野 nagano_hello_animal-1 ---------------------------------------------------------------

NAGANO_ZERO = "w006_nagano_hello_animal-1_zero_20261107.html"
NAGANO_CHILD = "w006_nagano_hello_animal-1_child_rearranged.html"


def test_nagano_dog_zero_day_is_empty_not_a_fake_dog():
    c = _single("nagano_hello_animal-1", _fx(NAGANO_ZERO))
    assert _zero(c), (c.status, c.result and c.result.animals)


def test_nagano_dog_child_day_still_read_and_never_zero():
    c = _single("nagano_hello_animal-1", _fx(NAGANO_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["name"], a["breed"], a["color"]) == ("やまと", "ミックス", "薄茶")
    assert a["image_url"].endswith("/images/yamato.jpg")
    assert _hits("nagano_hello_animal-1", _fx(NAGANO_CHILD)) == []


def test_nagano_dog_structure_change_is_not_zero():
    # 雛形の文が変わった（根拠が無い）日は、偽の犬にも 0 頭にもせず「読めなかった」にする
    html = _fx(NAGANO_ZERO).replace("飼い主募集中の犬はいません", "里親募集中の犬は現在おりません")
    assert not _zero(_single("nagano_hello_animal-1", html))
    c = _single("nagano_hello_animal-1", html)
    assert c.status != "ok"


# --- 長野 nagano_hello_animal-2（猫）: 犬ページと同じ雛形が 0 頭の日に出ると推定して同じ型を防ぐ ------------

NAGANO_CAT_CHILD = "w006_nagano_hello_animal-2_child_20261107.html"
NAGANO_CAT_ZERO = "w006_nagano_hello_animal-2_zero_rearranged.html"


def test_nagano_cat_child_day_reads_four_cats():
    c = _single("nagano_hello_animal-2", _fx(NAGANO_CAT_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 4
    assert _hits("nagano_hello_animal-2", _fx(NAGANO_CAT_CHILD)) == []


def test_nagano_cat_placeholder_day_is_empty_not_a_fake_cat():
    c = _single("nagano_hello_animal-2", _fx(NAGANO_CAT_ZERO))
    assert _zero(c), (c.status, c.result and c.result.animals)


# --- さいたま市 city_saitama-2: 管理番号の p だけが div に包まれ、写真・属性が次の子の div の前半に入る日 ----------

SAITAMA = "w006_city_saitama-2_20261107.html"


def test_saitama_2_first_cat_keeps_photo_and_attributes():
    c = _single("city_saitama-2", _fx(SAITAMA))
    assert c.status == "ok", c.error
    by_no = {a["management_no"]: a for a in c.result.animals}
    assert set(by_no) == {"R08-58", "R08-60"}
    a = by_no["R08-58"]
    assert a["image_url"].endswith("/p019971_d/img/143_s.jpg")
    assert (a["shelter_date"], a["location"], a["breed"], a["color"], a["sex"], a["age"], a["note"]) == (
        "令和8年10月21日", "浦和区領家", "雑種", "白", "メス", "6~10歳", "左耳カットあり")
    b = by_no["R08-60"]
    # 次の子の分は混ざらない
    assert (b["shelter_date"], b["color"], b["note"]) == ("令和8年10月30日", "茶白", "右耳カットあり")
    assert b["image_url"].endswith("/p019971_d/img/145_s.jpg")


def test_grouped_rows_partial_sibling_stops_at_row_until():
    from collector.recipe import Doc as D2
    from collector.recipe import Recipe as R2
    from collector.recipe import extract_rows

    html = ("<div><p>No.1</p></div><div><p>種類：犬</p><h2>終了</h2><p>種類：猫</p><p>No.2</p></div>")
    r = R2.from_dict({"rows": "p:-soup-contains('No.')", "row_until": "h2", "fields": {"breed": {"label": "種類"}}})
    rows = extract_rows(r, D2(url="http://x/", html=html, soup=BeautifulSoup(html, "lxml")))
    assert "種類：犬" in rows[0].el.get_text() and "種類：猫" not in rows[0].el.get_text()


# --- 岩手 pref_iwate_kennan: 公式の「雑種：雑種」（項目名が種類でない）と「特徴；」（セミコロン）を読む ----------

IWATE_KENNAN = "w006_pref_iwate_kennan_20261107.html"


def test_iwate_kennan_leon_reads_breed_and_note():
    c = _single("pref_iwate_kennan", _fx(IWATE_KENNAN))
    assert c.status == "ok", c.error
    by_no = {a.get("management_no"): a for a in c.result.animals}
    leon = by_no["26030"]
    assert (leon["name"], leon["breed"], leon["note"]) == ("レオン", "雑種", "人懐こい")
    # 「種類：雑種」「特徴：…」で書く子は従来どおり
    rubi = by_no["24034"]
    assert (rubi["breed"], rubi["note"]) == ("雑種", "食欲旺盛で元気な子です。性格は大人しい。")


# --- 宮城 pref_miyagi-6: 3 つ目のセルの区切りが全角の「／」の日（10/29〜10/30）---------------------------------------

MIYAGI6_KIDS = "t631_pref_miyagi-6_kids_20261030.html"


def test_miyagi_6_fullwidth_slash_cell_is_split():
    c = _single("pref_miyagi-6", _fx(MIYAGI6_KIDS))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["breed"], a["color"], a["sex"]) == ("雑種", "茶(尾の先が黒)", "オス")   # 全角括弧は半角にそろう
    # 4 つ目は年齢ではなく特徴（公式の見出しは「犬種/毛色/性別/特徴」）
    assert a.get("age") is None
    assert a["note"] == "赤い革首輪にフック付き、お座りなどしつけがされている"
    assert a["location"] == "気仙沼市赤岩牧沢地内" and a["shelter_date"] == "10月28日"


def test_miyagi_6_halfwidth_slash_with_age_still_reads_age_and_note():
    html = _fx(MIYAGI6_KIDS).replace(
        "雑種／茶（尾の先が黒）／オス／赤い革首輪にフック付き、お座りなどしつけがされている",
        "雑種/キジトラ白/メス/推定３歳以上/マイクロチップ反応なし、人慣れしている")
    c = _single("pref_miyagi-6", html)
    a = c.result.animals[0]
    assert (a["breed"], a["color"], a["sex"], a["age"], a["note"]) == (
        "雑種", "キジトラ白", "メス", "推定3歳以上", "マイクロチップ反応なし、人慣れしている")   # 全角数字は半角にそろう


# --- 千葉県 pref_chiba-1〜5: 公式の誤字「【容場所】」でも場所・品種・毛色を読む -----------------------------

CHIBA_TYPO = "w006_pref_chiba-1_typo_20261107.html"
CHIBA_SLUGS = ["pref_chiba-1", "pref_chiba-2", "pref_chiba-3", "pref_chiba-4", "pref_chiba-5"]


def test_chiba_1_typo_label_reads_location_breed_color():
    c = _single("pref_chiba-1", _fx(CHIBA_TYPO))
    assert c.status == "ok", c.error
    by_no = {a["management_no"]: a for a in c.result.animals}
    assert set(by_no) == {"kt261104-01", "sa261102-01", "sa261102-02"}
    got = {k: (a.get("location"), a.get("breed"), a.get("color")) for k, a in by_no.items()}
    assert got["kt261104-01"] == ("香取市米井野", "雑種", "茶白")
    assert got["sa261102-01"] == ("山武市埴谷", "柴犬", "茶黒")
    assert got["sa261102-02"] == ("山武市草深", "フレンチブルドッグ", "白色")


def test_chiba_1_spaced_typo_label_also_read():
    # 「【 容場所】」（空白入り）や「収場所」の揺れ
    html = _fx(CHIBA_TYPO).replace("【容場所】", "【 容場所】", 1).replace("【<span style=\"color: inherit;\">容場所】", "【収場所】<span>", 1)
    c = _single("pref_chiba-1", html)
    assert c.status == "ok", c.error
    assert all(a.get("location") and a.get("breed") and a.get("color") for a in c.result.animals)


def test_chiba_family_all_use_tolerant_location_anchor():
    # 同じ書き方の 2〜5 も誤字に強くする（子のいる日の保存版は無いので、1 の保存版を各レシピに当てて確かめる）
    for slug in CHIBA_SLUGS[1:]:
        recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
        for k in ("location", "breed", "color"):
            assert "収容場所】" not in recipe.fields[k]["regex"], (slug, k)
