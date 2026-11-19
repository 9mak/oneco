"""W006 T630 越谷市「保健所収容犬の譲渡を希望される方へ」city_koshigaya-3 の追加（2026-11-19・ネットワークなし）。

背景: 越谷市動物管理センターから 11/16・11/17 に、譲渡の 2 ページ（犬・猫）は市の収容動物なので写真・リンクを使ってよいと返事があった。
ページの作り: h2「譲渡動物情報」の下に、1 頭ごとに h3（管理番号）→（決まった子は「◆譲渡先が決定しました！」）→ 写真 → 表（見出し行と値の行）→ 紹介文。
  表の見出しは日によって 仮名・種類・性別・毛色・年齢・備考／手術（去勢・避妊・不妊の手術）と変わる。
0 頭の日は 2 通り（どちらも本文に 0 頭と言う文は出ない。title・h1 の「情報:0頭」は更新を忘れうるので根拠にしない）:
  - 決まった子だけが残る日（今日 2026-11-19 の R8-06・Wayback 2023-03-21 の 4 頭）: 行が 1 つ以上あり、全部が「決まった」印で除外され、枠（h2「譲渡動物情報」）が残る日。
    印が読めない行は動物として載るので、全行がこれで除外されるのは全部の行に印がある日だけ。表の見出しの語が変わった日は行そのものが取れず 0 頭にならない
  - 番号も表の値も空の雛形（h3 が空）だけが残る日（Wayback 2025-06-19）: 子の番号（数字を含む h3）も写真も無く、h2「譲渡動物情報」の枠がある日
子のいる日（Wayback 2024-09-15 の 3 頭・2025-02-16 の 1 頭）には、どちらも成立しない。
作りが変わった日（Wayback 2022-08 は #tmp_honbun の無い旧 CMS の作り）は 0 頭と言わず failed。
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
SLUG = "city_koshigaya-3"
IMG = "https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/jouto/images/"

TODAY = "w006_city_koshigaya-3_zero_decided_20261119.html"          # R8-06 だけ（決定済み）。title は「情報:0頭」
CHILD_2024 = "w006_city_koshigaya-3_child_wb20240915.html"          # 004・003・002
CHILD_2025 = "w006_city_koshigaya-3_child_wb20250216.html"          # 009
ZERO_TEMPLATE = "w006_city_koshigaya-3_zero_wb20250619.html"        # 空の h3 と空の表だけ
ZERO_DECIDED = "w006_city_koshigaya-3_zero_wb20230321.html"         # 4 頭とも「新しい飼い主が決まりました！」
OLD_LAYOUT = "w006_city_koshigaya-3_old_wb20220816.html"            # 旧 CMS（#tmp_honbun なし）に 2 頭


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


def test_registry_entry():
    s = SOURCES[SLUG]
    assert (s.mode, s.kind, s.species, s.enabled) == ("recipe", "adoption", "dog", True)
    assert (s.municipality, s.prefecture, s.phone) == ("越谷市", "埼玉県", "048-969-8511")
    assert s.url == "https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/jouto/20150909092350779.html"
    assert s.photo == "ok"   # 11/16・11/17 の返事（市の収容動物。写真・リンク・広告つきの掲載とも可）
    assert s.contact_scope == "facility"


def test_today_only_a_decided_dog_is_a_confirmed_zero():
    c = _single(_fx(TODAY))
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []
    assert c.result.empty_evidence == "all_excluded+container"   # 本文に 0 頭の文は無い。行が 1 つ以上あり全部に決定済みの印があって、枠（h2「譲渡動物情報」）が残る


def test_decided_four_dogs_in_2023_are_a_confirmed_zero():
    c = _single(_fx(ZERO_DECIDED))
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []


def test_template_only_day_is_a_confirmed_zero():
    c = _single(_fx(ZERO_TEMPLATE))
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []
    assert c.result.empty_evidence == "empty_absent"


def test_dogs_of_2024_are_read():
    c = _single(_fx(CHILD_2024))
    assert c.status == "ok", c.error
    assert c.result is not None
    got = [(a["management_no"], a["breed"], a["sex"], a["color"], a["age"], a["species"], a["image_url"]) for a in c.result.animals]
    assert got == [
        ("004", "プードル系", "めす", "クリーム", "推定8歳", "dog", IMG + "marupu1.jpg"),
        ("003", "M・ダックスフンド", "めす", "茶(ゴールド系)", "5歳", "dog", IMG + "melon1.jpg"),
        ("002", "M・ダックスフンド", "めす", "茶(レッド系)", "10歳", "dog", IMG + "maron1.jpg"),
    ]
    for a in c.result.animals:
        assert (a["kind"], a["phone"], a["contact_scope"]) == ("adoption", "048-969-8511", "facility")


def test_dog_of_2025_is_read():
    c = _single(_fx(CHILD_2025))
    assert c.status == "ok", c.error
    assert c.result is not None
    (a,) = c.result.animals
    assert (a["management_no"], a["breed"], a["sex"], a["color"], a["age"]) == ("009", "雑種", "おす", "クリーム", "16歳")
    assert a["image_url"] == IMG + "09a.jpg"
    assert a["source_url"] == SOURCES[SLUG].url


@pytest.mark.parametrize("name", [CHILD_2024, CHILD_2025])
def test_zero_evidence_does_not_hold_on_days_with_dogs(name):
    # 0 頭の根拠（空の枠・本文の文）は子のいる日に成立しない。audit_empty が毎日見る項目
    assert _hits(_fx(name)) == []


@pytest.mark.parametrize("name", [TODAY, ZERO_DECIDED])
def test_decided_days_have_no_page_level_zero_evidence(name):
    # 決定済みの子の h3 が残る日は「番号が付いた h3」があるので、空の枠の根拠は成立しない（全行除外の根拠だけが 0 頭にする）
    assert _hits(_fx(name)) == []


def test_template_day_with_a_dog_number_typed_in_is_a_dog_not_a_zero():
    # 空の雛形に番号が入っただけの日（表の値はまだ）は 0 頭と言わない
    html = _swap(_fx(ZERO_TEMPLATE), '<a id="c009"></a></h3>', '<a id="c009"></a>009</h3>')
    assert _hits(html) == []
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    assert [a["management_no"] for a in c.result.animals] == ["009"]


def test_template_day_without_the_section_heading_is_not_a_zero():
    # 枠（h2「譲渡動物情報」）が無い日は、雛形だけでも 0 頭と言わない
    html = _swap(_fx(ZERO_TEMPLATE), "譲渡動物情報", "お知らせ")
    assert _single(html).status not in ("ok", "empty")


def test_old_layout_with_dogs_is_not_a_zero():
    # 旧 CMS の作り（2022-08・2 頭）。行は読めないが、0 頭とも言わず failed（通知される）
    c = _single(_fx(OLD_LAYOUT))
    assert c.status not in ("ok", "empty"), (c.status, c.error)


def test_decided_day_with_renamed_table_headings_is_not_a_zero():
    # 決定済みの行しか読めない日でも、表の見出しの語が変わった（作りが変わった）日は 0 頭にしない
    html = _fx(TODAY)
    for old, new in (("仮名", "名前"), ("種類", "品種"), ("性別", "sex"), ("毛色", "色"), ("年齢", "歳"), ("備考", "メモ")):
        html = _swap(html, f">{old}<", f">{new}<")
    c = _single(html)
    assert c.status not in ("ok", "empty"), (c.status, c.error)


def test_dog_without_the_decided_mark_is_listed():
    # 決まった印が無い日の R8-06 は載る（印の語で除外していて、番号の h3 そのものを落としていない）
    html = _swap(_fx(TODAY), "◆譲渡先が決定しました！", "◆見学受付中")
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    (a,) = c.result.animals
    assert (a["management_no"], a["breed"], a["sex"], a["name"]) == ("R8-06", "マルチーズ", "めす", "ハナ")


def test_prose_mentioning_a_decision_does_not_hide_a_dog():
    # 紹介文の「決定」は決まった印ではない（印は表の前の短い行）
    html = _swap(_fx(CHILD_2025), "もふもふおじいちゃん☆", "もふもふおじいちゃん☆ 譲渡先が決定するまで見学できます。")
    c = _single(html)
    assert c.status == "ok", (c.status, c.error)
    assert [a["management_no"] for a in c.result.animals] == ["009"]
