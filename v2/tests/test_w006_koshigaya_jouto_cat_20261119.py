"""W006 T630 越谷市「保健所収容猫の譲渡を希望される方へ」city_koshigaya-4 の追加（2026-11-19・ネットワークなし）。

作りと除外・0 頭の考え方は犬（city_koshigaya-3。test_w006_koshigaya_jouto_dog_20261119.py）と同じ。猫のページで足したもの:
- h3 が div（img-area）に包まれる子（Wayback 2026-06 の R8-06）も読む。ページ自身の頭数（title「情報:N頭」）と読めた頭数が一致することを、子のいる 6 つの日で押さえる
  （最初に h2 の後ろの兄弟の h3 だけを始まりにしていて、R8-06 が落ちて 9 頭のところ 8 頭だった）
- 市と協定のあるイオンペットの店舗（千葉市）にいる子（今日の R8-35 ぐら）は、紹介文の後ろに「越谷市にはおりませんので、店舗へ直接お問い合わせください」と出る。
  掲載元が問い合わせ先を店舗と書いていて、台帳の電話（動物管理センター）は誤りになるので載せない（決定済みと同じ「除外」。店舗の電話・住所を出す作りにするかはオーナーの判断待ち）。
  今日は「決定済み 1・店舗 1 で、載せる子 0」の日で、全行除外の 0 頭（failed や ambiguous_empty にならない）。
0 頭の根拠は文言でなく作り（決定済みの行だけの日 = Wayback 2025-11、子の h3・写真が全部消えた日）。
  2025-11 の「ただいま、譲渡募集中の猫ちゃんはいません。」は根拠にしない（レシピに empty_text を置かない）。
"""

import re
import unicodedata
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
SLUG = "city_koshigaya-4"
IMG = "https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/jouto/images/"

TODAY = "w006_city_koshigaya-4_child_20261119.html"            # R8-35 ぐら（店舗にいる）と、決定済みの R8-38。title は「情報:１頭」（店舗の子を数えている）
ZERO_2025_11 = "w006_city_koshigaya-4_zero_wb20251107.html"    # 決定済みの 5 頭だけ。「ただいま、譲渡募集中の猫ちゃんはいません。」
CHILD_2026_06 = "w006_city_koshigaya-4_child_wb20260605.html"  # 9 頭（R8-06 は h3 が div に包まれる）
CHILD_2025_04 = "w006_city_koshigaya-4_child_wb20250422.html"  # 14 頭（番号が 2 桁・仮名なし・先頭に h3「はじめに」）
CHILD_2025_01 = "w006_city_koshigaya-4_child_wb20250125.html"  # 036 だけが募集中、決定済み 9 頭
CHILD_2024_06 = "w006_city_koshigaya-4_child_wb20240622.html"  # 008 の 1 頭
OLD_2022_10 = "w006_city_koshigaya-4_old_wb20221028.html"      # 4 頭（049・048・007・006）。決定済みの h3 に class が無い
CHILD_DAYS = [CHILD_2026_06, CHILD_2025_04, CHILD_2025_01, CHILD_2024_06, OLD_2022_10]


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _swap(html: str, old: str, new: str) -> str:
    assert old in html, old
    return html.replace(old, new)


def _single(html: str) -> Collected:
    return collect_one(SOURCES[SLUG], FakeFetcher({SOURCES[SLUG].url: html}))


def _hits(html: str) -> list[str]:
    recipe = Recipe.load(ROOT / "recipes" / f"{SLUG}.yaml")
    doc = Doc(url=SOURCES[SLUG].url, html=html, soup=BeautifulSoup(html, "lxml"))
    return [h.kind for h in empty_hits(recipe, [doc], [doc])]


def _page_count(html: str) -> int:
    """ページ自身の頭数（title「…（情報:N頭）」）。全角の数字もある。"""
    title = BeautifulSoup(html, "lxml").title
    assert title is not None
    m = re.search(r"情報[:：](\d+)頭", unicodedata.normalize("NFKC", title.get_text()))
    assert m, title.get_text()
    return int(m.group(1))


def _without_animals(html: str) -> str:
    """子の ID の入った h3 と、その次の h3 か h2 の手前までを消す（子が全員いなくなった日の合成）。"""
    soup = BeautifulSoup(html, "lxml")
    for h in soup.select("div#tmp_honbun h3"):
        if not re.search(r"\d", h.get_text()):
            continue
        for sib in list(h.next_siblings):
            if isinstance(sib, Tag) and (sib.name in ("h2", "h3") or sib.select_one("h2") is not None):
                break
            sib.extract()
        h.extract()
    return str(soup)


def test_registry_entry():
    s = SOURCES[SLUG]
    assert (s.mode, s.kind, s.species, s.enabled) == ("recipe", "adoption", "cat", True)
    assert (s.municipality, s.prefecture, s.phone) == ("越谷市", "埼玉県", "048-969-8511")
    assert s.url == "https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/jouto/nekojyouto.html"
    assert s.photo == "ok"
    # city_koshigaya-1・-2 と同じ扱い: 載るのは市の動物管理センターにいる子だけ（contact_scope は facility）。住所は null（ページに市名なしの町名しか無い）
    assert s.contact_scope == "facility" and s.address is None
    assert s.verified_at and s.verified_phone_url


def test_today_is_a_confirmed_zero_decided_one_and_store_one():
    c = _single(_fx(TODAY))
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []
    assert c.result.empty_evidence == "all_excluded+container"
    assert c.result.ambiguous_empty is False
    reasons = {d.text.split()[0]: d.reason for d in c.result.dropped}   # R8-38 テルは決定済み、R8-35 ぐらは店舗にいる子
    assert set(reasons) == {"R8-38", "R8-35"}
    assert "◆" in reasons["R8-38"] and "越谷市にはおりません" in reasons["R8-35"]
    assert _hits(_fx(TODAY)) == []   # 枠だけの根拠ではない（ぐらの h3 が残る）


def test_store_cat_is_left_out_among_cats_in_the_city():
    # 2026-06 の 9 頭のうち R8-20 に店舗の文を足した合成。市にいる 8 頭だけが載る
    html = _swap(_fx(CHILD_2026_06), "まずはビジュが気になるだけでもいいので、ご連絡ください！",
                 "まずはビジュが気になるだけでもいいので、ご連絡ください！<br/>けいは現在、「ペテモライフハウスピアシティ稲毛海岸」にて里親さん募集中！<br/>越谷市にはおりませんので、店舗へ直接お問い合わせください。")
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    assert [a["management_no"] for a in c.result.animals] == ["R8-19", "R8-16", "R8-15", "R8-13", "R8-11", "R8-10", "R8-09", "R8-06"]
    assert [d.text.split()[0] for d in c.result.dropped] == ["R8-20"]


def test_store_wording_alone_is_enough_to_leave_a_cat_out():
    html = _swap(_fx(CHILD_2024_06), "同期の仲間たちがみんな卒業し", "店舗へ直接お問い合わせください。同期の仲間たちがみんな卒業し")
    c = _single(html)
    assert c.status == "empty", (c.status, c.error)   # 1 頭しかいない日に、その 1 頭が店舗の子なら載せる子 0


def test_cats_without_the_store_wording_are_listed_as_before():
    for name, n in ((CHILD_2026_06, 9), (CHILD_2025_04, 14), (CHILD_2025_01, 1), (CHILD_2024_06, 1), (OLD_2022_10, 4)):
        c = _single(_fx(name))
        assert c.status == "ok" and len(c.result.animals) == n, name
        assert not any("店舗" in d.reason or "越谷市にはおりません" in d.reason for d in c.result.dropped), name


@pytest.mark.parametrize("name", CHILD_DAYS)
def test_read_count_matches_the_count_the_page_states(name):
    # ページ自身が title に書く頭数（決定済みは数えない）と読めた頭数が同じ（h3 が div に包まれる子・先頭の h3「はじめに」・class の無い h3）
    c = _single(_fx(name))
    assert c.status == "ok", (c.status, c.error)
    assert c.result is not None
    assert len(c.result.animals) == _page_count(_fx(name))


def test_2026_06_reads_nine_including_the_h3_wrapped_in_a_div():
    c = _single(_fx(CHILD_2026_06))
    assert c.result is not None
    got = {a["management_no"]: a for a in c.result.animals}
    assert list(got) == ["R8-20", "R8-19", "R8-16", "R8-15", "R8-13", "R8-11", "R8-10", "R8-09", "R8-06"]
    sui = got["R8-06"]
    assert (sui["name"], sui["breed"], sui["sex"], sui["color"], sui["age"]) == ("すい", "雑種", "おす", "茶白", "中齢")
    assert sui["image_url"] == IMG + "sui1.jpg"
    assert sui["note"] == "去勢済。FIV陽性"
    assert got["R8-09"]["note"] == "FIV陽性"   # 手術が「不明」の子は備考だけ
    assert got["R8-20"]["note"] == "去勢済。FIV/FeLV陰性"
    assert len({a["id"] for a in c.result.animals}) == 9


def test_2025_04_reads_fourteen_without_the_intro_h3():
    c = _single(_fx(CHILD_2025_04))
    assert c.result is not None
    nos = [a["management_no"] for a in c.result.animals]
    assert nos == ["92", "90", "89", "88", "87", "86", "85", "84", "83", "82", "81", "80", "69", "66"]
    a = c.result.animals[0]
    assert (a["name"], a["breed"], a["sex"], a["color"], a["age"]) == (None, "雑種", "おす", "白", "中齢")


def test_2025_01_lists_only_the_cat_without_a_decided_mark():
    # 印の言い方は「◆譲渡決定！…」「◆譲渡が決定しました」「◆譲渡が決定しました！おめでとう！」と日で違う。印の無い 036 だけが載る
    c = _single(_fx(CHILD_2025_01))
    assert c.result is not None
    assert [a["management_no"] for a in c.result.animals] == ["036"]
    assert len(c.result.dropped) >= 9
    a = c.result.animals[0]
    assert (a["breed"], a["sex"], a["color"], a["age"], a["image_url"]) == ("雑種", "めす", "サバ白", "2歳9か月", IMG + "60a.jpeg")


def test_2022_10_old_markup_lists_the_four_and_skips_the_decided_without_h3_class():
    c = _single(_fx(OLD_2022_10))
    assert c.result is not None
    assert [a["management_no"] for a in c.result.animals] == ["049", "048", "007", "006"]
    assert {d.text.split()[0] for d in c.result.dropped} == {"044", "043", "042"}


@pytest.mark.parametrize("name", CHILD_DAYS)
def test_zero_evidence_does_not_hold_on_days_with_cats(name):
    # 0 頭の根拠（子の h3・写真が無い枠）は子のいる日に成立しない。audit_empty が毎日見る項目
    assert _hits(_fx(name)) == []


def test_decided_only_day_is_a_confirmed_zero_by_structure():
    c = _single(_fx(ZERO_2025_11))
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []
    assert c.result.empty_evidence == "all_excluded+container"
    assert len(c.result.dropped) == 5
    assert _hits(_fx(ZERO_2025_11)) == []   # 「ただいま、譲渡募集中の猫ちゃんはいません。」の文は根拠にしていない


def test_day_with_every_cat_removed_is_a_confirmed_zero():
    html = _without_animals(_fx(ZERO_2025_11))
    assert "R7-036" not in html and "ただいま、譲渡募集中の猫ちゃんはいません" in html
    c = _single(html)
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []
    assert c.result.empty_evidence == "empty_absent"


def test_same_day_without_the_section_heading_is_not_a_zero():
    html = _swap(_without_animals(_fx(ZERO_2025_11)), "譲渡動物情報", "お知らせ")
    assert _single(html).status not in ("ok", "empty")


def test_removed_day_with_a_photo_left_is_not_a_zero():
    # 子の h3 が消えても、写真（pet/jouto/images/）が残っていれば子の掲載が崩れた日。0 頭と言わない
    html = _swap(_without_animals(_fx(ZERO_2025_11)), "<h2", '<p><img alt="x" src="/kurashi_shisei/fukushi/hokenjo/pet/jouto/images/x.jpg"/></p><h2')
    assert _single(html).status not in ("ok", "empty")


def test_decided_day_with_a_mark_without_a_diamond_lists_the_cats_not_a_zero():
    # 「◆」が無く、知っている言い方（決まりました・決定）でもない印は読めない。決定済みの子が載る（0 頭と言わない側）
    html = _swap(_fx(ZERO_2025_11), "◆譲渡先が決定しました！", "お引き渡し済みです")
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    assert len(c.result.animals) == 5


def test_renamed_table_headings_are_not_a_zero():
    # 表の見出しの語（種類）が変わると行が取れない。子の h3 が残るので 0 頭と言わず failed
    html = _swap(_fx(TODAY), ">種類<", ">品種<")
    assert _single(html).status not in ("ok", "empty")


def test_cat_with_only_a_prose_decision_word_is_listed():
    # 紹介文の中の「譲渡先が決定」は決まった印ではない（印は行の先頭にある短い行）
    html = _swap(_fx(CHILD_2024_06), "同期の仲間たちがみんな卒業し", "同期の仲間たちがみんな卒業し、譲渡先が決定するまで見学できます。")
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    assert [a["management_no"] for a in c.result.animals] == ["008"]


@pytest.mark.parametrize("mark", ["◆譲渡が成立しました！", "◆お見合い中です", "◆トライアル中"])
def test_any_diamond_line_marks_a_cat_that_is_no_longer_offered(mark):
    # 「◆」は fixture 全部（今日と Wayback）で決定済みの印にしか使われていない（◆譲渡先が決定しました！ ◆譲渡が決定しました ◆譲渡決定！…）。
    # 言い方が変わっても、「◆」で始まる印の行がある子は載せない
    html = _swap(_fx(ZERO_2025_11), "◆譲渡先が決定しました！", mark)
    c = _single(html)
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == [] and len(c.result.dropped) == 5


STORE_SENTENCE = "越谷市にはおりませんので、店舗へ直接お問い合わせください。"


@pytest.mark.parametrize("replacement", [
    "",                                  # (a) 文ごと無い
    "店舗までご連絡ください。",            # (b) 言い方が変わった
    "店舗に直接ご連絡ください。",          # (c) 言い方が変わった
])
def test_store_cat_is_left_out_even_if_the_store_sentence_changes_or_is_gone(replacement):
    # 行に残る「ぐらは現在、「ペテモライフハウスピアシティ稲毛海岸」にて里親さん募集中！」（店舗名・「にて里親さん募集中」）も店舗の子の目印
    html = _swap(_fx(TODAY), STORE_SENTENCE, replacement)
    assert "ライフハウス" in html
    c = _single(html)
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []
    assert c.result.empty_evidence == "all_excluded+container" and c.result.ambiguous_empty is False
    assert {d.text.split()[0] for d in c.result.dropped} == {"R8-38", "R8-35"}


def test_store_name_alone_is_enough_to_leave_a_cat_out_among_cats_in_the_city():
    html = _swap(_fx(CHILD_2026_06), "まずはビジュが気になるだけでもいいので、ご連絡ください！",
                 "まずはビジュが気になるだけでもいいので、ご連絡ください！<br/>ネコモライフハウス幕張新都心にいます。")
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    assert [a["management_no"] for a in c.result.animals] == ["R8-19", "R8-16", "R8-15", "R8-13", "R8-11", "R8-10", "R8-09", "R8-06"]
