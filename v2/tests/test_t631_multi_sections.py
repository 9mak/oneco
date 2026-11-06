"""W006 T631: 節が複数あるページ 13 slug の 0 頭の根拠（ネットワークなし）。

empty は ok と同じ扱いで通知も AI 修復も止まる。だから子がいる日に当たる文言を 0 頭の根拠にしてはいけない
（行の読み方が崩れた日に、子がいるのに「本日は 0 頭」と黙って出る）。ここでは、子のいる版の保存ページ・Wayback の版で
根拠（collector.extract.empty_hits）が成立しないこと、0 頭の日の版では 0 頭と確定することを確かめる。

fixture は実ページから script・style を落としたもの。名前は t631_<slug>_<kids|zero>_<日付>.html
（kids は子のいる版、zero は全部の節が 0 頭の版。wbYYYYMMDD は Wayback、それ以外は 2026-10〜11 の実ページか保存ページ）。
松本市（-2・-3）は掲載者の名前・電話が載るので fixture にせず、実ページの作りを真似た最小の HTML で確かめる。
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


def _recipe(slug: str) -> Recipe:
    return Recipe.load(ROOT / "recipes" / f"{slug}.yaml")


def _doc(html: str, url: str = "https://example.jp/p.html") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _fx(name: str) -> Doc:
    return _doc((FIX / name).read_text(encoding="utf-8"))


def _hits(slug: str, *docs: Doc):
    return empty_hits(_recipe(slug), list(docs))


def _build(slug: str, *docs: Doc):
    return build(SOURCES[slug], _recipe(slug), list(docs))


def _kinds(hits) -> list[str]:
    return [h.kind for h in hits]


# --- 佐賀県 -3・-4・-5（犬・猫・その他の 3 つの表に同じ雛形の文が入る） ----------------------------------------------
# 犬だけ 0 頭でも猫に子がいても、雛形の表の文は出る。文言でなく「表の中に写真が 1 枚も無い」ことを 0 頭の根拠にする（empty_absent）。
SAGA = {
    "pref_saga-3": (
        ["t631_pref_saga-3_kids_20261027.html", "t631_pref_saga-3_kids_wb20260113.html"],
        ["t631_pref_saga-3_zero_20261106.html", "t631_pref_saga-3_zero_wb20260712.html"],
    ),
    "pref_saga-4": (
        ["t631_pref_saga-4_kids_20261028.html", "t631_pref_saga-4_kids_wb20251211.html"],
        ["t631_pref_saga-4_zero_20261106.html", "t631_pref_saga-4_zero_wb20241209.html"],
    ),
    "pref_saga-5": (
        ["t631_pref_saga-5_kids_20261105.html", "t631_pref_saga-5_kids_wb20240718.html"],
        ["t631_pref_saga-5_zero_20261106.html", "t631_pref_saga-5_zero_wb20260207.html"],
    ),
}
SAGA_KIDS = [(s, n) for s, (kids, _) in SAGA.items() for n in kids]
SAGA_ZERO = [(s, n) for s, (_, zero) in SAGA.items() for n in zero]


@pytest.mark.parametrize(("slug", "name"), SAGA_KIDS)
def test_saga_kids_day_has_no_zero_evidence_even_though_template_sentences_appear(slug, name):
    doc = _fx(name)
    assert _hits(slug, doc) == []
    res = _build(slug, doc)
    assert len(res.animals) >= 1 and not res.empty_confirmed


@pytest.mark.parametrize(("slug", "name"), SAGA_ZERO)
def test_saga_zero_day_is_confirmed_by_no_photo_in_any_table(slug, name):
    res = _build(slug, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_absent"


@pytest.mark.parametrize("slug", sorted(SAGA))
def test_saga_table_class_renamed_is_not_zero(slug):
    # 表の名前（__wys_table）が変わった日は枠が見つからず、0 頭に見せない
    html = (
        (FIX / SAGA[slug][1][0]).read_text(encoding="utf-8").replace("__wys_table", "renamed_table")
    )
    res = _build(slug, _doc(html))
    assert not res.empty_confirmed


@pytest.mark.parametrize("slug", sorted(SAGA))
def test_saga_recipe_has_no_sentence_based_zero(slug):
    r = _recipe(slug)
    assert not r.empty_text and not r.empty_text_all


# --- 柏市 -2（犬・猫・犬と猫以外の 3 節。猫の 0 頭の文を見たことが無い） -----------------------------------------------
KASHIWA_KIDS = [
    "t631_city_kashiwa-2_kids_20261106.html",
    "t631_city_kashiwa-2_kids_wb20250624.html",
    "t517_kashiwa-2.html",
]


@pytest.mark.parametrize("name", KASHIWA_KIDS)
def test_kashiwa_kids_day_has_no_zero_evidence(name):
    doc = _fx(name)
    assert "現在、譲渡可能な犬はおりません" in doc.text()  # 子のいる日にも出る文
    assert _hits("city_kashiwa-2", doc) == []


def test_kashiwa_without_cat_cards_fails_closed():
    # 猫のカードが読めなくなった日。犬の文・犬と猫以外の文が出ていても 0 頭にしない（通知に出る）
    html = (FIX / "t631_city_kashiwa-2_kids_20261106.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    for el in soup.select("div.col2_sp2_wrap"):
        el.decompose()
    res = _build("city_kashiwa-2", _doc(str(soup)))
    assert res.animals == [] and not res.empty_confirmed


def test_kashiwa_recipe_has_no_zero_evidence_until_cat_sentence_is_confirmed():
    r = _recipe("city_kashiwa-2")
    assert not r.empty_text and not r.empty_text_all and not r.empty_absent


# --- 山形県（4 保健所のページ。節ごとの 0 頭の文が 1 つでも出れば 0 頭に見えていた） ---------------------------------------
YAMAGATA_ZERO = [
    "t631_pref_yamagata_murayama_zero_20261106.html",
    "t631_pref_yamagata_mogami_zero_20261106.html",
    "t631_pref_yamagata_okitama_zero_20261106.html",
    "t631_pref_yamagata_shonai_zero_20261106.html",
]


def test_yamagata_all_four_offices_zero_is_zero():
    docs = [_fx(n) for n in YAMAGATA_ZERO]
    hits = _hits("pref_yamagata", *docs)
    assert _kinds(hits) == ["empty_text_all"]
    res = _build("pref_yamagata", *docs)
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


@pytest.mark.parametrize(
    ("replaced", "kids"),
    [
        (
            0,
            "t631_pref_yamagata_murayama_kids_20261022.html",
        ),  # 村山: 迷い犬 1 頭（負傷犬・負傷猫の文は出ている）
        (0, "t631_pref_yamagata_murayama_kids_wb20260715.html"),
        (
            1,
            "t631_pref_yamagata_mogami_kids_wb20251111.html",
        ),  # 最上: 負傷犬・ねこ側に子（「負傷犬・ねこ情報0頭」が出ない）
        (2, "t631_pref_yamagata_okitama_kids_wb20250530.html"),  # 置賜: 「迷い犬：1頭」
    ],
)
def test_yamagata_one_office_with_animals_is_not_zero_even_if_other_offices_say_zero(
    replaced, kids
):
    docs = [_fx(n) for n in YAMAGATA_ZERO]
    docs[replaced] = _fx(kids)
    assert _hits("pref_yamagata", *docs) == []


def test_yamagata_murayama_kids_page_alone_still_carries_two_zero_sentences():
    # 以前の empty_text はこの 2 文だけで 0 頭にした（村山に迷い犬がいる日に、他の保健所の文が無くても）
    doc = _fx("t631_pref_yamagata_murayama_kids_20261022.html")
    assert (
        "現在、保護している負傷犬はいません" in doc.text()
        and "現在、保護している負傷猫はいません" in doc.text()
    )
    assert _hits("pref_yamagata", doc) == []


def test_yamagata_hub_page_is_not_evidence():
    docs = [_fx("t631_pref_yamagata_hub_20261106.html")]
    assert _hits("pref_yamagata", *docs) == []


# --- 浜松市はぴまるの丘（中央区・浜名区・天竜区の 3 節） ----------------------------------------------------------------
@pytest.mark.parametrize(
    "name", ["t631_hama_aikyou_kids_20261104.html", "t631_hama_aikyou_kids_wb20240523.html"]
)
def test_hama_kids_day_has_no_zero_evidence(name):
    doc = _fx(name)
    assert "区で保護された犬はいません" in doc.text()  # 2 区の文は出ている
    assert _hits("hama_aikyou", doc) == []


@pytest.mark.parametrize(
    "name",
    [
        "t631_hama_aikyou_zero_wb20251107.html",
        "t631_hama_aikyou_zero_wb20260209.html",
        "t631_hama_aikyou_zero_20261106.html",
    ],
)
def test_hama_all_three_wards_zero_is_zero(name):
    res = _build("hama_aikyou", _fx(name))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


# --- 宮城県 気仙沼保健所 -6（保護犬・保護猫の 2 節） ------------------------------------------------------------------
@pytest.mark.parametrize(
    "name", ["t631_pref_miyagi-6_kids_20261030.html", "t631_pref_miyagi-6_kids_wb20201101.html"]
)
def test_miyagi6_kids_day_has_no_zero_evidence(name):
    doc = _fx(name)
    assert ("現在、保護猫の情報はありません" in doc.text()) or (
        "現在，保護犬の情報はありません" in doc.text()
    )
    assert _hits("pref_miyagi-6", doc) == []


@pytest.mark.parametrize(
    "name",
    [
        "t631_pref_miyagi-6_zero_wb20240715.html",
        "t631_pref_miyagi-6_zero_wb20260305.html",
        "t631_pref_miyagi-6_zero_20261106.html",
    ],
)
def test_miyagi6_both_sections_zero_is_zero(name):
    res = _build("pref_miyagi-6", _fx(name))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


# --- 長野市 -1（犬譲渡・猫譲渡の 2 節） -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("name", "only"),
    [
        (
            "t631_city_nagano-1_kids_20261106.html",
            "現在、譲渡対象の猫は収容していません",
        ),  # 犬 1 頭・猫の文
        (
            "t631_city_nagano-1_kids_wb20260114.html",
            "現在、譲渡対象の犬は収容していません",
        ),  # 猫に子・犬の文
        ("t519v_g5_nagano1_20250814.html", "現在、譲渡対象の犬は収容していません"),
    ],
)
def test_nagano1_kids_day_has_no_zero_evidence(name, only):
    doc = _fx(name)
    assert only in doc.text()
    assert _hits("city_nagano-1", doc) == []


def test_nagano1_both_sentences_is_zero():
    # 実ページの作り（h2 の下に h3 犬譲渡・猫譲渡。0 頭の節は p の 1 文）を真似た最小の HTML。両方 0 頭の版は Wayback に無い
    html = (
        "<h2>譲渡対象動物</h2><h3>犬譲渡</h3><p>現在、譲渡対象の犬は収容していません。</p>"
        "<h3>猫譲渡</h3><p>現在、譲渡対象の猫は収容していません。</p>"
    )
    res = _build("city_nagano-1", _doc(html))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


# --- 松本市 -2（個人が保護している犬・猫。保護犬・保護猫の 2 節） -----------------------------------------------------------
M2_DOG = "現在、保護犬の情報はありません"
M2_CAT = "現在、保護猫の情報はありません"


def _m2(dog: str, cat: str) -> str:
    return f"<h2>個人の方が保護している動物の情報</h2><h3>保護犬</h3>{dog}<h3>保護猫</h3>{cat}"


M2_CAT_CHILD = (
    "<h4>保護猫No.8-1</h4><p><img src='/a.jpg'></p>"
    "<table><tr><th>保護年月日</th><td>令和8年10月28日</td></tr><tr><th>保護場所</th><td>市内</td></tr></table>"
)


def test_matsumoto2_dog_sentence_alone_with_cat_child_is_not_zero_evidence():
    html = _m2(f"<p>{M2_DOG}。</p>", M2_CAT_CHILD)
    assert _hits("city_matsumoto-2", _doc(html)) == []
    res = _build("city_matsumoto-2", _doc(html))
    assert len(res.animals) == 1 and not res.empty_confirmed


def test_matsumoto2_cat_child_unreadable_with_dog_sentence_only_is_not_zero():
    # 猫の行が読めなくなった日（猫の表の見出しが変わった）。以前は犬の文だけで 0 頭になった
    html = _m2(f"<p>{M2_DOG}。</p>", "<h4>保護猫No.8-1</h4><p>猫の情報 場所 市内</p>")
    res = _build("city_matsumoto-2", _doc(html))
    assert res.animals == [] and not res.empty_confirmed


def test_matsumoto2_both_sections_zero_is_zero():
    res = _build("city_matsumoto-2", _doc(_m2(f"<p>{M2_DOG}。</p>", f"<p>{M2_CAT}。</p>")))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


# --- 松本市 -3（逸走犬・逸走猫・その他の逸走動物。猫の 0 頭の文を見たことが無い） -------------------------------------------------
def test_matsumoto3_dog_and_other_sentences_with_unreadable_cat_rows_fail_closed():
    html = (
        "<h2>逸走動物の情報</h2><h3>逸走犬</h3><p>現在、逸走犬の情報はございません。</p>"
        "<h3>逸走猫</h3><h4>逸走猫No.8-3</h4><p>猫の情報</p><h4>その他の逸走動物</h4><p>現在その他の逸走動物の情報はありません。</p>"
    )
    res = _build("city_matsumoto-3", _doc(html))
    assert res.animals == [] and not res.empty_confirmed


def test_matsumoto3_recipe_has_no_zero_evidence_until_cat_sentence_is_confirmed():
    r = _recipe("city_matsumoto-3")
    assert not r.empty_text and not r.empty_text_all and not r.empty_absent


# --- 大阪府（犬・猫の 2 節） ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name", ["t631_pref_osaka_kids_20261016.html", "t631_pref_osaka_kids_wb20260512.html"]
)
def test_osaka_kids_day_has_no_zero_evidence(name):
    doc = _fx(name)
    assert _hits("pref_osaka", doc) == []
    res = _build("pref_osaka", doc)
    assert len(res.animals) >= 1 and not res.empty_confirmed


def test_osaka_dog_sentence_alone_with_unreadable_cat_is_not_zero():
    # 2026-10-16 の実ページ: 犬の文が出て、猫に 1 頭。猫の表が読めなくなった日を 0 頭にしない
    doc = _fx("t631_pref_osaka_kids_20261016.html")
    assert "現在対象の犬はいません" in doc.text()
    html = str(doc.soup).replace("受付番号", "番号")
    res = _build("pref_osaka", _doc(html))
    assert res.animals == [] and not res.empty_confirmed


@pytest.mark.parametrize(
    "name", ["t631_pref_osaka_zero_wb20260830.html", "t631_pref_osaka_zero_20261106.html"]
)
def test_osaka_both_sections_zero_is_zero(name):
    res = _build("pref_osaka", _fx(name))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


# --- 越谷市 個人の保護（犬の情報・猫の情報の 2 節に同じ文） ------------------------------------------------------------------
KOJIN_KIDS = [
    "t631_city_koshigaya_kojin_kids_20260413.html",
    "t631_city_koshigaya_kojin_kids_wb20230407.html",
    "t631_city_koshigaya_kojin_kids_wb20260616.html",
    "t517_koshigaya_kojin.html",  # 犬 1 頭の日（題名に頭数が無い版）
]


@pytest.mark.parametrize("name", KOJIN_KIDS)
def test_koshigaya_kojin_kids_day_has_no_zero_evidence(name):
    doc = _fx(name)
    assert "現在、情報はありません" in doc.text()  # 片方の節の 0 頭の文は子のいる日にも出る
    assert _hits("city_koshigaya_kojin", doc) == []
    if (
        "2026" in name
    ):  # 2023 の版は今と見出しの作りが違い、行は読めない（0 頭の根拠が成立しないことだけ確かめる）
        res = _build("city_koshigaya_kojin", doc)
        assert len(res.animals) >= 1 and not res.empty_confirmed


@pytest.mark.parametrize(
    "name",
    [
        "t631_city_koshigaya_kojin_zero_wb20250613.html",
        "t631_city_koshigaya_kojin_zero_wb20240119.html",
    ],
)
def test_koshigaya_kojin_zero_in_title_and_sentence_is_zero(name):
    res = _build("city_koshigaya_kojin", _fx(name))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


def test_koshigaya_kojin_sentence_without_zero_in_title_is_not_zero():
    # 題名が「（情報：1頭）」なのに行が読めなくなった日
    html = (
        (FIX / "t631_city_koshigaya_kojin_kids_20260413.html")
        .read_text(encoding="utf-8")
        .replace("partsstyle_h3", "renamed")
    )
    res = _build("city_koshigaya_kojin", _doc(html))
    assert res.animals == [] and not res.empty_confirmed


# --- 佐世保市 -1（動物愛護センターの節・市民の節に同じ文） -----------------------------------------------------------------
SASEBO_KIDS = [
    "t631_city_sasebo-1_kids_20261102.html",
    "t631_city_sasebo-1_kids_wb20251210.html",
    "t631_city_sasebo-1_kids_wb20260213.html",  # 写真が無く、リンクだけの子
]
SASEBO_ZERO = [
    "t631_city_sasebo-1_zero_20261106.html",
    "t631_city_sasebo-1_zero_wb20221204.html",
    "t631_city_sasebo-1_zero_wb20210515.html",
]


@pytest.mark.parametrize("name", SASEBO_KIDS)
def test_sasebo_kids_day_has_no_zero_evidence(name):
    doc = _fx(name)
    assert (
        "現在、情報はありません" in doc.text()
    )  # 市民の節の 0 頭の文は愛護センターに子のいる日にも出る
    assert _hits("city_sasebo-1", doc) == []
    res = _build("city_sasebo-1", doc)
    assert len(res.animals) >= 1 and not res.empty_confirmed


@pytest.mark.parametrize("name", SASEBO_ZERO)
def test_sasebo_zero_day_is_confirmed_by_no_dog_link(name):
    res = _build("city_sasebo-1", _fx(name))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_sasebo_link_pattern_renamed_with_photo_is_not_zero():
    # 個体ページのリンクの名前（_dog）が変わった日。行は取れないが、リンクつきの写真が残るので 0 頭に見せない
    html = (
        (FIX / "t631_city_sasebo-1_kids_20261102.html")
        .read_text(encoding="utf-8")
        .replace("_dog", "_inu")
    )
    res = _build("city_sasebo-1", _doc(html))
    assert res.animals == [] and not res.empty_confirmed


def test_sasebo_frame_gone_is_not_zero():
    res = _build("city_sasebo-1", _doc("<html><body><p>メンテナンス中</p></body></html>"))
    assert not res.empty_confirmed
