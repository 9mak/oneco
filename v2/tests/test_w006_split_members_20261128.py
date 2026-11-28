"""POLICY.md 方針 21・24（2026-11-28・ネットワークなし）: 1 件に複数の子が名前つきで並ぶ掲載を 1 匹ずつに分ける作り（split_names）。\n\n同じ日の方針 24 の変更で、写真 1 枚にまとめた掲載は分けずに 1 件で載せることになり、split_names はどのレシピにも書かない。\n下の規則の試験は作り（collector/members.py）の試験として残し、実ページの試験はまとめたまま 1 件で読むことを確かめる。

岩手県の保健所などは、兄弟の子を写真 1 枚・1 件にまとめて「名前：(左)三郎、(右)二郎」「性別：オス×2」のように書く。
方針 24「性別・毛色などが分かれば 1 匹ずつに分けて載せる」に沿って、レシピに split_names: true を書いた掲載元だけ、
名前が「、」で 2 つ以上並び、ほかの項目が全員共通（「オス×2」「みんな女の子」「メス(避妊手術済)」）か名前ごと
（「らん→オス　すー→メス」「シルビアちゃんはメス…、みかん君はオス…」）に書いてある行を分ける。
どの子の値か分からない項目（「黒白、黒白、黒」を 2 匹に）が 1 つでもあれば分けない（今までどおり 1 件）。
分けた子のうち、本文に「◯◯は譲渡が決まりました」とある子は載せない（方針 21）。
fixture は 2026-11-28 の実ページ（岩手 大船渡・宮古・県南・中部、和歌山市）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from collector.fetch import FakeFetcher
from collector.members import split_members
from collector.recipe_schema import validate_recipe_dict
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
DAY = "20261128"


# --- 分け方の規則（split_members） -------------------------------------------------


def _names(ms):
    return [m.fields["name"] for m in ms]


def test_count_suffix_is_shared_by_all():
    # 岩手 県南「名前：(左)三郎、(右)二郎」「性別：オス×2」「毛色：キジシロ×2」
    f = {"name": "(左)三郎、(右)二郎", "sex": "オス×2", "color": "キジシロ×2", "age": "生後半年くらい", "breed": "雑種",
         "note": "三郎は大人しいが少々ビビり、二郎はすごくフレンドリーです。"}
    ms = split_members(f, "")
    assert ms is not None
    assert _names(ms) == ["(左)三郎", "(右)二郎"]   # 位置の印は名前に残す（写真 1 枚に 2 匹が写っている）
    assert [m.fields["sex"] for m in ms] == ["オス", "オス"]
    assert [m.fields["color"] for m in ms] == ["キジシロ", "キジシロ"]
    assert all(m.fields["note"] == f["note"] and m.fields["age"] == "生後半年くらい" for m in ms)
    assert [m.id_key for m in ms] == ["三郎", "二郎"]   # ID は印を外した名前から（印が変わっても ID が動かない）


def test_all_prefix_is_shared_by_all():
    # 大船渡「愛称：左からえぴ、ねり、うるい、ばい、てぃい」「性別：みんな女の子」
    f = {"name": "左からえぴ、ねり、うるい、ばい、てぃい", "sex": "みんな女の子", "color": "キジトラ", "age": "3か月齢"}
    ms = split_members(f, "")
    assert _names(ms) == ["えぴ", "ねり", "うるい", "ばい", "てぃい"]
    assert {m.fields["sex"] for m in ms} == {"女の子"}
    assert {m.fields["color"] for m in ms} == {"キジトラ"}


def test_single_value_with_parenthesis_is_shared():
    # 大船渡「愛称：ココ(左)、ロコ(右)」「性別：メス(避妊手術済)」「毛色：キジトラ(ココは茶色が混じってます。)」
    f = {"name": "ココ(左)、ロコ(右)", "sex": "メス(避妊手術済)", "color": "キジトラ(ココは茶色が混じってます。)"}
    ms = split_members(f, "")
    assert _names(ms) == ["ココ(左)", "ロコ(右)"]
    assert {m.fields["sex"] for m in ms} == {"メス(避妊手術済)"}
    assert {m.fields["color"] for m in ms} == {"キジトラ(ココは茶色が混じってます。)"}


def test_arrow_mapping_per_name():
    # 岩手 中部「仮名：らん、すー、みき」「性別：らん→オス　すー→メス　　みき→メス」（印は無いが名前ごとの性別が根拠）
    f = {"name": "らん、すー、みき", "sex": "らん→オス　すー→メス　　みき→メス", "breed": "雑種"}
    ms = split_members(f, "")
    assert _names(ms) == ["らん", "すー", "みき"]
    assert [m.fields["sex"] for m in ms] == ["オス", "メス", "メス"]


def test_wa_mapping_per_name_and_management_numbers_in_order():
    # 宮古「管理番号：【左側】2026-10-086C（仮名：シルビアちゃん） 【右側】2026-10-085C（仮名：みかん君）」
    f = {"name": "シルビアちゃん、みかん君", "management_no": "2026-10-086C、2026-10-085C",
         "sex": "シルビアちゃんはメス（不妊手術済）、みかん君はオス（去勢済）", "color": "シルビアちゃんはサバ白、みかん君は茶白"}
    ms = split_members(f, "")
    assert _names(ms) == ["シルビアちゃん", "みかん君"]
    assert [m.fields["sex"] for m in ms] == ["メス（不妊手術済）", "オス（去勢済）"]
    assert [m.fields["color"] for m in ms] == ["サバ白", "茶白"]
    assert [m.fields["management_no"] for m in ms] == ["2026-10-086C", "2026-10-085C"]
    assert [m.id_key for m in ms] == ["2026-10-086C", "2026-10-085C"]   # 子ごとの管理番号があればそれで ID を作る


def test_shared_management_number_is_kept_but_not_used_for_id():
    f = {"name": "(左)三郎、(右)二郎", "sex": "オス×2", "management_no": "26034"}
    ms = split_members(f, "")
    assert [m.fields["management_no"] for m in ms] == ["26034", "26034"]   # 掲載元が 2 匹に 1 つの番号を付けている
    assert [m.id_key for m in ms] == ["三郎", "二郎"]


def test_unmappable_list_keeps_one_listing():
    # 大船渡「愛称：カナン、チェスター」「毛色：黒白、黒白、黒」（譲渡が決まったヤスパーの分が残り、どの子の毛色か分からない）
    f = {"name": "カナン、チェスター", "sex": "みんなオス(去勢済み)", "color": "黒白、黒白、黒"}
    assert split_members(f, "") is None


def test_same_count_list_is_not_mapped_by_order():
    # 並び順で当てはめない（どの子の値かは掲載元に書いていない）
    f = {"name": "(左)たま、(右)くろ", "sex": "オス×2", "color": "白、黒"}
    assert split_members(f, "") is None


def test_mapping_that_names_someone_else_is_not_split():
    # 名前の欄が 2 匹なのに性別が 3 匹分（3 匹目の値を 2 匹目につないで「オス C君はオス」にしない）
    f = {"name": "(左)Aちゃん、(右)B君", "sex": "Aちゃんはメス、B君はオス、C君はオス"}
    assert split_members(f, "") is None


def test_mapping_continuation_is_joined():
    f = {"name": "らん、すー", "sex": "らん→オス 去勢済み　すー→メス"}
    assert [m.fields["sex"] for m in split_members(f, "")] == ["オス 去勢済み", "メス"]


def test_management_number_count_must_match():
    f = {"name": "シルビアちゃん、みかん君", "management_no": "2026-10-086C、2026-10-085C、2026-10-084C",
         "sex": "シルビアちゃんはメス、みかん君はオス"}
    assert split_members(f, "") is None


def test_two_call_names_of_one_cat_are_not_split():
    # 高崎市「呼名：チビ、チー」は 1 匹の呼び名（印も、名前ごとの値も、×2 も無い）
    f = {"name": "チビ、チー", "sex": "メス", "color": "キジ白八割れ", "management_no": "2024-89", "note": "・呼名:チビ、チー"}
    assert split_members(f, "") is None


@pytest.mark.parametrize("name", [None, "", "ミント", "おとひめちゃん ※アシストファーム南国店にいます"])
def test_one_name_is_not_split(name):
    assert split_members({"name": name, "sex": "オス×2"}, "") is None


def test_group_without_names_is_not_split():
    # 福井 fapscsite-2「管理番号：HC26468~470」「性別：オス:2匹、メス:1匹」（名前が無く、どの番号が何色かも書いていない）
    f = {"name": None, "management_no": "HC26468~470", "sex": "オス:2匹、メス:1匹", "color": "短毛/黒トラ白×2、キジ白"}
    assert split_members(f, "") is None


def test_member_with_closed_note_is_dropped():
    # 方針 21: まとめた子のうち「◯◯は譲渡が決まりました」とある子は載せない
    f = {"name": "(左)てんや、(右)わんや", "sex": "オス×2", "note": "兄弟です。右側のわんや君は譲渡が決まりました。"}
    ms = split_members(f, "兄弟です。右側のわんや君は譲渡が決まりました。")
    assert _names(ms) == ["(左)てんや"]


def test_comma_inside_name_parenthesis_does_not_split_the_name():
    f = {"name": "ココ(左、茶色が混じる)、ロコ(右)", "sex": "メス×2"}
    assert _names(split_members(f, "")) == ["ココ(左、茶色が混じる)", "ロコ(右)"]


@pytest.mark.parametrize(
    ("note", "left"),
    [
        ("ねりちゃん、うるい君は譲渡が決まりました。", ["えぴ"]),          # 名前を並べた主語は全員
        ("ねりもうるいも新しいお家が決まりました。", ["えぴ"]),
        ("えぴとねりは姉妹で、ねりは譲渡が決まりました。", ["えぴ", "うるい"]),   # 前の文節の名前まで外さない
        ("うるいは、新しい家族が決まりました。", ["えぴ", "ねり"]),
        ("えぴは里親さんが決まり次第お知らせします。", ["えぴ", "ねり", "うるい"]),   # 条件・願いは決まっていない
    ],
)
def test_closed_subjects(note, left):
    f = {"name": "左からえぴ、ねり、うるい", "sex": "みんな女の子", "note": note}
    assert _names(split_members(f, note)) == left


def test_closed_name_that_contains_a_sibling_name():
    # 「みきお」が決まっても「みき」は外さない
    f = {"name": "(左)みき、(右)みきお", "sex": "オス×2", "note": "みきおは譲渡が決まりました。"}
    assert _names(split_members(f, f["note"])) == ["(左)みき"]


def test_closed_note_of_someone_outside_the_names_keeps_all():
    # 大船渡: 名前から外れたヤスパーの「譲渡が決まりました」は、残った 2 匹に効かない
    f = {"name": "(左)カナン、(右)チェスター", "sex": "みんなオス(去勢済み)", "note": "仲良し3兄弟です。ヤスパーは譲渡が決まりました!"}
    ms = split_members(f, "仲良し3兄弟です。ヤスパーは譲渡が決まりました!")
    assert _names(ms) == ["(左)カナン", "(右)チェスター"]


def test_wish_is_not_closed():
    f = {"name": "(左)たま、(右)くろ", "sex": "オス×2", "note": "たまは早く新しい家族が見つかりますように。"}
    assert len(split_members(f, f["note"])) == 2


# --- reviewer 指摘（2026-11-28 #172 M-1〜M-3・m-1） ---------------------------------------

PAIR = "(左)三郎、(右)二郎"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sex", "オスとメス"), ("sex", "オス・メス"), ("sex", "オス/メス"), ("sex", "オス メス"), ("sex", "雄雌"),
        ("sex", "オス(左)メス(右)"), ("sex", "オス1メス1"), ("color", "黒と白"), ("color", "黒・白"), ("color", "黒 白"),
        ("age", "3か月と5か月"),
    ],
)
def test_one_value_holding_two_animals_is_not_shared(field, value):
    # M-1: 読点でなく「と・/・空白」でつないだ 2 匹分や、オスとメスが並ぶ値は、どの子の値か書いていないので分けない
    f = {"name": PAIR, "sex": "オス×2", field: value}
    assert split_members(f, "") is None


@pytest.mark.parametrize("value", ["オス 去勢済み", "メス(避妊手術済)", "オス(去勢手術済み)", "メス・不妊手術済"])
def test_sex_with_surgery_note_is_still_shared(value):
    f = {"name": PAIR, "sex": value}
    assert [m.fields["sex"] for m in split_members(f, "")] == [value, value]


@pytest.mark.parametrize(("field", "value"), [("color", "三郎は茶色"), ("sex", "三郎はオス"), ("sex", "三郎→オス")])
def test_value_naming_only_one_member_is_not_shared(field, value):
    # M-2: 1 匹の名前だけを挙げる値を、全員の値にしない
    f = {"name": PAIR, "sex": "オス×2", field: value}
    assert split_members(f, "") is None


@pytest.mark.parametrize(
    "note",
    [
        "二郎は飼い主さんのもとに戻りました。", "二郎は返還されました。", "二郎は譲渡されました。", "二郎は譲渡しました。",
        "二郎の譲渡が決まりました。", "二郎君の飼い主さんが見つかりました。", "二郎は新しい飼い主さんの元へ旅立ちました。",
    ],
)
def test_closed_wordings_drop_the_member(note):
    # M-3: 方針 21「飼い主に返りました」なども載せない
    f = {"name": PAIR, "sex": "オス×2", "note": note}
    assert _names(split_members(f, note)) == ["(左)三郎"]


@pytest.mark.parametrize("note", ["二郎はお家が決まりにくいかもしれません。", "二郎は譲渡が決まりそうです。", "二郎は飼い主さんが決まりましたらお知らせします。"])
def test_not_yet_closed_wordings_keep_the_member(note):
    f = {"name": PAIR, "sex": "オス×2", "note": note}
    assert _names(split_members(f, note)) == ["(左)三郎", "(右)二郎"]


def test_closed_phrase_of_another_member_after_comma():
    # 「二郎は、三郎の譲渡が決まりました」は三郎が決まった（二郎ではない）
    note = "二郎は、三郎の譲渡が決まりました。"
    f = {"name": PAIR, "sex": "オス×2", "note": note}
    assert _names(split_members(f, note)) == ["(右)二郎"]


@pytest.mark.parametrize(
    "note",
    ["カナンの兄のヤスパーは譲渡が決まりました。", "カナンの兄弟は譲渡が決まりました。", "カナンとチェスターの兄ヤスパーは譲渡が決まりました。"],
)
def test_no_subject_does_not_reach_over_other_words(note):
    # 再レビュー N-1: 「◯◯の兄の△△は…」の「の」を主語にしない（残っている子を外さない）
    f = {"name": "(左)カナン、(右)チェスター", "sex": "オス×2", "note": note}
    assert _names(split_members(f, note)) == ["(左)カナン", "(右)チェスター"]


@pytest.mark.parametrize(
    "note",
    ["チェスターの譲渡が決まりました。", "チェスター君の飼い主さんが見つかりました。", "チェスターのお家が決まりました!", "チェスターの元の飼い主さんが見つかりました。"],
)
def test_no_subject_right_before_closed_phrase(note):
    f = {"name": "(左)カナン、(右)チェスター", "sex": "オス×2", "note": note}
    assert _names(split_members(f, note)) == ["(左)カナン"]


@pytest.mark.parametrize(("field", "value"), [("sex", "オスとメス×2"), ("sex", "三郎はオス×2"), ("color", "三郎は白×2"), ("sex", "みんなオスとメス")])
def test_plural_mark_does_not_skip_the_checks(field, value):
    # 再レビュー n-2: 「×2」「みんな」を外した値にも、2 匹分の値・1 匹だけの名前の確認をかける
    f = {"name": PAIR, "sex": "オス×2", field: value}
    assert split_members(f, "") is None


@pytest.mark.parametrize(("value", "shared"), [("白と黒×2", "白と黒"), ("みんな白と黒", "白と黒")])
def test_plural_mark_makes_two_colors_shared(value, shared):
    # 「×2」「みんな」は全員が同じと書いてあるので、1 匹が 2 色の値として全員に付ける
    f = {"name": PAIR, "sex": "オス×2", "color": value}
    assert [m.fields["color"] for m in split_members(f, "")] == [shared, shared]


def test_member_id_uses_own_shelter_date():
    # m-1: 収容日が名前ごとのとき、ほかの子が抜けても残った子の ID は動かない
    from bs4 import BeautifulSoup
    from collector.extract import build
    from collector.recipe import Doc, Recipe

    recipe = Recipe.from_dict({
        "rows": "div.row", "image": "img@src", "split_names": True,
        "fields": {"name": {"regex": "名前[:：]\\s*(\\S+)"}, "sex": {"regex": "性別[:：]\\s*(.+?)\\s*収容日"},
                   "shelter_date": {"regex": "収容日[:：]\\s*(.+)$"}},
    })

    def ids(html: str) -> dict[str, str]:
        doc = Doc(url="https://example.jp/p.html", html=html, soup=BeautifulSoup(html, "lxml"))
        return {a["name"]: a["id"] for a in build(SOURCES["pref_iwate_chubu"], recipe, [doc]).animals}

    three = ("<div class='row'><img src='/p.jpg'><p>名前：らん、すー、みき</p><p>性別：らん→オス すー→メス みき→メス</p>"
             "<p>収容日：らん→10月1日 すー→10月3日 みき→10月5日</p></div>")
    two = three.replace("、みき", "").replace(" みき→メス", "").replace(" みき→10月5日", "")
    a, b = ids(three), ids(two)
    assert set(a) == {"らん", "すー", "みき"} and set(b) == {"らん", "すー"}
    assert a["らん"] == b["らん"] and a["すー"] == b["すー"]


# --- レシピの検査 -------------------------------------------------------------------


def test_schema_accepts_bool_only():
    url = "https://www.pref.iwate.jp/morioka/hoken/1012494.html"
    assert not validate_recipe_dict({"rows": "li", "split_names": True}, url)
    assert validate_recipe_dict({"rows": "li", "split_names": "yes"}, url)


# --- 実ページ（2026-11-28） ---------------------------------------------------------


def _run(slug: str, pages: dict[str, str], mutate=None) -> Collected:
    html = {u: (FIX / f).read_text(encoding="utf-8") for u, f in pages.items()}
    if mutate:
        html = {u: mutate(h) for u, h in html.items()}
    return collect_one(SOURCES[slug], FakeFetcher(html))


OFUNATO = {"https://www.pref.iwate.jp/engan/ofuna_hoken/1014212/1014213.html": f"w006_pref_iwate_ofunato_{DAY}.html"}
MIYAKO = {"https://www.pref.iwate.jp/engan/miya_hoken/hogodoubutsu/1014161.html": f"w006_pref_iwate_miyako_{DAY}.html"}
KENNAN = {"https://www.pref.iwate.jp/morioka/hoken/1012494.html": f"w006_pref_iwate_kennan_{DAY}.html"}
CHUBU = {
    "https://www.pref.iwate.jp/kennan/hana_hoken/1013542/index.html": f"w006_pref_iwate_chubu_index_{DAY}.html",
    "https://www.pref.iwate.jp/kennan/hana_hoken/1013542/1020659.html": f"w006_pref_iwate_chubu_1020659_{DAY}.html",
    "https://www.pref.iwate.jp/kennan/hana_hoken/1013542/1013544.html": f"w006_pref_iwate_chubu_1013544_{DAY}.html",
}
WAKAYAMA = {"https://www.city.wakayama.wakayama.jp/kurashi/kenko_iryo/1009125/1035775/1002096.html": f"w006_city_wakayama_{DAY}.html"}


def _by_name(c: Collected) -> dict[str, dict]:
    return {a["name"]: a for a in c.result.animals if a.get("name")}


# 2026-11-28 POLICY.md 方針 24 の変更（おまえさん「写真が同じなら同じにしよう 説明欄に同じように書けばいいもんね」）:
# 写真 1 枚・1 件にまとめた掲載は分けずに 1 件で載せる。split_names はどのレシピにも書かない（作りと上の規則の試験は残す）。


def test_no_recipe_splits_members():
    texts = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "recipes").glob("*.yaml")}
    assert not [n for n, t in texts.items() if re.search(r"^split_names:\s*true", t, re.M)]


def test_ofunato_groups_stay_one_listing_each():
    c = _run("pref_iwate_ofunato", OFUNATO)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 14
    by = _by_name(c)
    assert by["左からえぴ、ねり、うるい、ばい、てぃい"]["sex"] == "みんな女の子"
    assert by["ココ(左)、ロコ(右)"]["sex"] == "メス(避妊手術済)"
    assert by["カナン、チェスター"]["color"] == "黒白、黒白、黒"


def test_miyako_pair_shows_both_names_and_numbers_in_one_listing():
    # 宮古は 2 匹目の名前・管理番号も読む（#172 の読み方の直しは残す。今までは【左側】の印で管理番号が読めず、名前も 1 匹目だけだった）
    c = _run("pref_iwate_miyako", MIYAKO)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 19
    by = _by_name(c)
    a = by["シルビアちゃん、みかん君"]
    assert a["management_no"] == "2026-10-086C、2026-10-085C"
    assert a["sex"] == "シルビアちゃんはメス(不妊手術済)、みかん君はオス(去勢済)"
    assert by["ミレ君"]["management_no"] == "R7-159-17-3"
    assert [x["name"] for x in c.result.animals if "、" in (x.get("management_no") or "")] == ["シルビアちゃん、みかん君"]


def test_kennan_pair_stays_one_listing():
    c = _run("pref_iwate_kennan", KENNAN)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 6
    assert _by_name(c)["(左)三郎、(右)二郎"]["sex"] == "オス×2"


def test_chubu_sex_is_read_to_the_next_label():
    # 中部の性別は次の項目名の手前まで読む（#172 の直しは残す。label では「らん→オス」で切れていた）
    c = _run("pref_iwate_chubu", CHUBU)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 7
    by = _by_name(c)
    sex = by["らん、すー、みき"]["sex"]
    assert sex.startswith("らん→オス") and "すー→メス" in sex and "みき→メス" in sex
    # 1 匹の子の性別は、変更前のエンジン（origin/main cd15c40）で同じページを読んだ値と同じ
    before = {"トッシー": "オス", "キジ太": "オス", "しろ吉": "オス", "みこ": "メス", "しーちゃん": "メス", "トム": "オス"}
    assert {n: by[n]["sex"] for n in before} == before


def test_wakayama_pair_stays_one_listing():
    c = _run("city_wakayama", WAKAYAMA)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 24
    assert _by_name(c)["むさし(手前)、あけぼの(奥)"]["sex"] == "オス(手術済)"
