"""W006 T620 の後始末: 公開中の誤り・読めているのに抜けている子（2026-11-07。ネットワークなし）。

長野 nagano_hello_animal-1: 0 頭の日の雛形（h3「現在、飼い主募集中の犬はいません」）を 1 頭の犬として載せていた。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build, empty_hits, make_id
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe, extract_rows
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


def test_nagano_dog_wayback_child_days_read_all_fields():
    # Wayback の実物（子のいる日）。2025-12 は h3・写真の div と 種類〜備考の div が別々の作り、2024-09 は 1 つの div
    c = _single("nagano_hello_animal-1", _fx("w006_nagano_hello_animal-1_child_wb20251211.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["name"], a["breed"], a["color"], a["sex"], a["age"]) == (
        "2025-102", "ミックス", "白茶", "オス(去勢済み)", "2021年10月頃生まれ")
    assert a["note"].startswith("20キロ前後の大型犬です。")
    assert _hits("nagano_hello_animal-1", _fx("w006_nagano_hello_animal-1_child_wb20251211.html")) == []
    c = _single("nagano_hello_animal-1", _fx("w006_nagano_hello_animal-1_child_wb20240918.html"))
    a = c.result.animals[0]
    assert (a["name"], a["breed"], a["sex"], a["age"]) == ("2023-107", "小型ミックス", "メス(避妊手術済み)", "2018年1月頃生まれ")
    assert _hits("nagano_hello_animal-1", _fx("w006_nagano_hello_animal-1_child_wb20240918.html")) == []


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

    html = ("<div><p>No.1</p></div><div><p>種類：犬</p><h2>終了</h2><p>種類：猫</p><p>No.2</p></div>")
    r = Recipe.from_dict({"rows": "p:-soup-contains('No.')", "row_until": "h2", "fields": {"breed": {"label": "種類"}}})
    rows = extract_rows(r, Doc(url="http://x/", html=html, soup=BeautifulSoup(html, "lxml")))
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


def _miyagi6_fourth(fourth: str):
    html = _fx(MIYAGI6_KIDS).replace("赤い革首輪にフック付き、お座りなどしつけがされている", fourth)
    return _single("pref_miyagi-6", html).result.animals[0]


def test_miyagi_6_age_stops_at_the_age_word_even_without_a_separator():
    # 公開ゲート F-05: 「／」の日に「3歳首輪なし」のように区切り無しで続けても、年齢に備考まで入らない
    a = _miyagi6_fourth("3歳首輪なし／人懐こい")
    assert (a["age"], a["note"]) == ("3歳", "首輪なし/人懐こい")   # 区切りの「／」は取り込みの正規化で「/」になる


def test_miyagi_6_month_ages_are_ages_not_notes():
    for text, age in (("1か月", "1か月"), ("3ヶ月", "3ヶ月"), ("生後2カ月くらい", "生後2カ月くらい")):
        a = _miyagi6_fourth(text)
        assert a.get("age") == age and a.get("note") is None, (text, a)
    # 変更前から読めていた書き方（Wayback の保存版: 「1か月齢前後」「7週齢前後」）は年齢のまま
    for text in ("1か月齢前後", "7週齢前後", "推定3歳以上"):
        a = _miyagi6_fourth(text)
        assert a.get("age") == text and a.get("note") is None, (text, a)
    a = _miyagi6_fourth("3月に保護された")
    assert a.get("age") is None and a["note"] == "3月に保護された"   # 「月」だけでは年齢にしない


# --- ID の衝突: 同じ写真を使う別の子（管理番号が違う）を「同じ ID」で捨てない ------------------------------------

SAITAMA_MINAMI = "w006_pref_saitama_joto_neko_minami_20261107.html"
IWATE_OSHU = "w006_pref_iwate_oshu_20261107.html"


def test_saitama_minami_cats_sharing_a_photo_are_all_kept():
    c = _single("pref_saitama_joto_neko_minami", _fx(SAITAMA_MINAMI))
    assert c.status == "ok", c.error
    nos = [a["management_no"] for a in c.result.animals]
    assert nos == ["南2026-C76", "南2026-C77", "南2026-C78"]
    ids = [a["id"] for a in c.result.animals]
    assert len(set(ids)) == 3
    assert c.result.dropped == []


def test_saitama_minami_first_cat_id_is_unchanged():

    c = _single("pref_saitama_joto_neko_minami", _fx(SAITAMA_MINAMI))
    # 公開中の C76 の ID（2026-11-07 の本番 animals の値）は変わらない
    assert c.result.animals[0]["id"] == "42cfb147dce1"
    # 衝突した 2 頭は、公開中の ID が無い（今まで捨てられていた）ので管理番号から作る
    for b in c.result.animals[1:]:
        assert b["id"] == make_id(SOURCES["pref_saitama_joto_neko_minami"], None, {"management_no": b["management_no"]})


def test_iwate_oshu_r8_9_3_is_kept():
    c = _single("pref_iwate_oshu", _fx(IWATE_OSHU))
    assert c.status == "ok", c.error
    nos = [a["management_no"].split("(")[0] for a in c.result.animals]
    assert "R8-9-3" in nos and len(nos) == 8 and c.result.dropped == []
    assert len({a["id"] for a in c.result.animals}) == 8
    # 公開中の 7 頭の ID（2026-11-07 の本番 animals の値）は 1 つも変わらない
    now = {"6079c2b07254", "b6f465c22036", "ed16499b473b", "103bedd35ff1", "a2514874bbff", "ae7e7d3594f7", "e05d9f5eb4b4"}
    assert now <= {a["id"] for a in c.result.animals}


def _without(html: str, selector: str, marker: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for el in soup.select(selector):
        if marker in el.get_text():
            el.decompose()
    return str(soup)


def test_saitama_minami_c77_id_stays_when_c76_is_gone():
    # 公開ゲート F-02: 先に載った C76 が譲渡されて消えても、C77・C78 の ID が写真由来（C76 の ID）に変わらない
    c = _single("pref_saitama_joto_neko_minami", _without(_fx(SAITAMA_MINAMI), "#tmp_contents table", "南2026-C76"))
    got = {a["management_no"]: a["id"] for a in c.result.animals}
    assert "南2026-C76" not in got
    for no in ("南2026-C77", "南2026-C78"):
        assert got[no] == make_id(SOURCES["pref_saitama_joto_neko_minami"], None, {"management_no": no})
    assert "42cfb147dce1" not in got.values()


def test_iwate_oshu_r8_9_3_id_stays_when_r8_9_2_is_gone():
    html = _fx(IWATE_OSHU)
    full = {a["management_no"].split("(")[0]: a["id"] for a in _single("pref_iwate_oshu", html).result.animals}
    c = _single("pref_iwate_oshu", _without(html, "p", "管理番号：R8-9-2（"))
    got = {a["management_no"].split("(")[0]: a["id"] for a in c.result.animals}
    assert "R8-9-2" not in got
    assert got["R8-9-3"] == full["R8-9-3"]


def test_same_management_no_twice_is_still_dropped_as_duplicate():
    # 同じ子が 2 行書かれた重複（水戸 公表181）は従来どおり 1 頭
    html = ("<table><tr><td>A-1</td><td><img src='/p.jpg'></td><td>雑種</td></tr>"
            "<tr><td>A-1</td><td><img src='/p.jpg'></td><td>雑種</td></tr></table>")

    r = Recipe.from_dict({"rows": "tr", "image": "img@src", "fields": {"management_no": {"selector": ":scope > :nth-child(1)"},
                                                                  "breed": {"selector": ":scope > :nth-child(3)"}}})
    res = build(SOURCES["pref_iwate_oshu"], r, [Doc(url="http://x/", html=html, soup=BeautifulSoup(html, "lxml"))])
    assert len(res.animals) == 1 and res.dropped and res.dropped[0].reason == "同じ ID の行が既にある"


# --- 枚方市 city_hirakata: 写真の次のブロックにある表（種類・性別・毛色・体格・収容地域・その他）を読む ---------------

HIRAKATA = "w006_city_hirakata_20261107.html"


def test_hirakata_cat_reads_the_table_next_to_the_photo():
    c = _single("city_hirakata", _fx(HIRAKATA))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1
    a = c.result.animals[0]
    assert a["species"] == "cat" and a["image_url"].endswith("/1430/ten1.jpeg")
    assert (a["breed"], a["sex"], a["color"], a["size"], a["location"], a["note"]) == (
        "雑種", "メス", "灰", "小", "黄金野", "体重 約2kg")


def test_hirakata_photo_card_id_is_unchanged():
    # 公開中の ID（2026-11-07 の本番 animals の値）は変わらない
    c = _single("city_hirakata", _fx(HIRAKATA))
    assert c.result.animals[0]["id"] == "a411a796bbc0"


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
