"""W006 T624 見守り運転: 2026-11-06 の収集で読めなかった掲載元のレシピの直し（ネットワークなし）。

fixture は実ページから script・style を落としたもの。名前は w006_<slug>_<状態>_<日付>.html（zero はその日の 0 頭、last_ok は直前まで正常に読めた日、wb は Wayback の版）。
- 札幌市 迷子犬（city_sapporo-1）: 0 頭の日の文言が「現在迷子犬は収容されていません」で empty_text に無く failed だった
- 広島県 迷い猫（pref_hiroshima-2）: 0 頭の日に文言が出ず、案内の p だけになって failed だった
- 福岡市 暫定ページの犬（city_fukuoka_interim-1）は 404。直さない（市の一覧から消えているだけ）
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str):
    src = SOURCES[slug]
    recipe = Recipe.load(ROOT / src.recipe)
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


# --- 札幌市 迷子犬（city_sapporo-1） ----------------------------------------------------------------------------------
# 11/06 の 0 頭の日は「現在迷子犬は収容されていません」の見出しと、値の無い雛形の表（収容年月日 ： 保護場所： …）だけ。
# 市は 0 頭の書き方を何度も変えている（Wayback 2025-02「迷子収容犬はいません。」、2025-06「現在、迷子犬は収容されていません。」、2025-11・2026-03「現在、迷子収容犬はいません。」）。
# 子のいる版（11/05 の保存ページ、Wayback 2019-04・2019-07・2020-01）にはこれらの文が出ない。
SAPPORO1 = "city_sapporo-1"
SAPPORO1_ZERO = [
    "w006_city_sapporo-1_zero_20261106.html",
    "w006_city_sapporo-1_zero_wb20250621.html",
    "w006_city_sapporo-1_zero_wb20251118.html",
]


@pytest.mark.parametrize("name", SAPPORO1_ZERO)
def test_sapporo_1_zero_days_in_every_observed_wording_are_zero(name):
    res = _run(SAPPORO1, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_text"


def test_sapporo_1_today_zero_page_has_the_empty_template_row_that_is_dropped():
    # 値の無い雛形の表が 1 行になるが、写真も管理番号も収容日も無いので動物にならない（0 頭の根拠は文言）
    res = _run(SAPPORO1, _fx("w006_city_sapporo-1_zero_20261106.html"))
    assert len(res.dropped) == 1


def test_sapporo_1_zero_sentence_gone_is_not_zero():
    html = _fx("w006_city_sapporo-1_zero_20261106.html")
    changed = html.replace("現在迷子犬は収容されていません", "お知らせ")
    assert changed != html and "収容されていません" not in _text(changed)
    res = _run(SAPPORO1, changed)
    assert res.animals == [] and not res.empty_confirmed


def test_sapporo_1_last_ok_day_is_read_as_before():
    res = _run(SAPPORO1, _fx("w006_city_sapporo-1_last_ok_20261105.html"))
    assert len(res.animals) == 1 and not res.empty_confirmed
    # 管理番号は写真のファイル名から取る既存の読み方のまま（見出しは AD081026-01）
    assert res.animals[0]["management_no"].lower().endswith("d081026-01")


def test_sapporo_1_day_with_a_dog_never_shows_a_zero_sentence():
    # 子のいる日に 0 頭の文言が出ないこと（出ると、子がいるのに行の読み方が崩れた日が 0 頭に見える）
    html = _fx("w006_city_sapporo-1_last_ok_20261105.html")
    recipe = Recipe.load(ROOT / "recipes" / f"{SAPPORO1}.yaml")
    text = _text(html)
    assert recipe.empty_text and all(t not in text for t in recipe.empty_text)


def test_sapporo_1_empty_text_keeps_only_sentences_seen_on_the_real_page():
    # 以前は猫ページからの類推で一度もページに出ていない文を並べていた。実ページで見た文だけにする
    recipe = Recipe.load(ROOT / "recipes" / f"{SAPPORO1}.yaml")
    assert set(recipe.empty_text) == {
        "迷子収容犬はいません",
        "現在迷子犬は収容されていません",
        "現在、迷子犬は収容されていません",
        "現在、迷子収容犬はいません",
    }


# --- 広島県 迷い猫（pref_hiroshima-2） ----------------------------------------------------------------------------------
# 11/06 の 0 頭の日は div.detail_free に案内の p（「この情報は、迷い猫を探している飼い主さんのための情報提供です。…」）だけで、0 頭の文が無い
# （Wayback 2025-01 も同じ形）。文が出る版もある（2024-07・2025-05「※現在、新たな迷い猫の収容はありません」、2026-04「現在、迷い猫は収容されていません。」）。
# 案内の p は子のいる日にも出るので 0 頭の根拠にしない。0 頭は「案内の p があり、動物の印（見出し h2・写真・表・収容日や保護の状況の行）が 1 つも無い」日だけ（empty_absent）。
HIRO2 = "pref_hiroshima-2"
HIRO2_ZERO_ABSENT = [
    "w006_pref_hiroshima-2_zero_20261106.html",
    "w006_pref_hiroshima-2_zero_wb20250123.html",
]
HIRO2_ZERO_SENTENCE = [
    "w006_pref_hiroshima-2_zero_wb20250524.html",
    "w006_pref_hiroshima-2_zero_wb20260414.html",
]
HIRO2_KIDS = [
    "w006_pref_hiroshima-2_last_ok_20261105.html",
    "w006_pref_hiroshima-2_last_ok_wb20251108.html",
]


@pytest.mark.parametrize("name", HIRO2_ZERO_ABSENT)
def test_hiroshima_2_zero_days_without_a_sentence_are_zero_by_absence(name):
    res = _run(HIRO2, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_absent"


@pytest.mark.parametrize("name", HIRO2_ZERO_SENTENCE)
def test_hiroshima_2_zero_days_with_a_sentence_are_zero(name):
    res = _run(HIRO2, _fx(name))
    assert res.animals == []
    assert res.empty_confirmed


@pytest.mark.parametrize("name", HIRO2_KIDS)
def test_hiroshima_2_days_with_a_cat_are_read_and_have_no_zero_evidence(name):
    html = _fx(name)
    recipe = Recipe.load(ROOT / "recipes" / f"{HIRO2}.yaml")
    text = _text(html)
    assert recipe.empty_text and all(t not in text for t in recipe.empty_text)
    res = _run(HIRO2, html)
    assert len(res.animals) == 1 and not res.empty_confirmed


def test_hiroshima_2_last_ok_day_is_read_as_before():
    res = _run(HIRO2, _fx("w006_pref_hiroshima-2_last_ok_20261105.html"))
    assert res.animals[0]["management_no"] == "1HN20260102"
    assert res.animals[0]["shelter_date"] == "令和8年10月20日"


def test_hiroshima_2_cat_listed_but_rows_unreadable_is_not_zero():
    # 子がいる日に属性 p の書き方が変わって行が 0 になっても、見出し・写真が残る間は 0 頭にしない（これが 11/05 までの失敗の再発防止）
    html = _fx("w006_pref_hiroshima-2_last_ok_20261105.html")
    changed = html.replace("センターに収容された日", "センター収納日").replace(
        "保護された状況", "状況"
    )
    assert changed != html
    res = _run(HIRO2, changed)
    assert res.animals == [] and not res.empty_confirmed


def test_hiroshima_2_cat_text_only_without_heading_or_photo_is_not_zero():
    # 見出し h2 と写真を落として属性の文だけ残した形でも、収容日・保護の状況の文が残る日は 0 頭にしない
    html = _fx("w006_pref_hiroshima-2_last_ok_20261105.html")
    soup = BeautifulSoup(html, "lxml")
    for el in soup.select("div.detail_free h2, div.detail_free img"):
        el.decompose()
    changed = str(soup).replace("センターに収容された日", "センター受入日")
    assert "収容された日" not in changed and "保護された状況" in changed
    res = _run(HIRO2, changed)
    assert res.animals == [] and not res.empty_confirmed


def test_hiroshima_2_page_without_the_frame_is_not_zero():
    # 案内の p が無い（ブロック画面・作り替え）なら 0 頭にしない
    html = _fx("w006_pref_hiroshima-2_zero_20261106.html")
    changed = html.replace("この情報は、迷い猫を探している飼い主さんのための情報提供です。", "")
    assert changed != html
    res = _run(HIRO2, changed)
    assert res.animals == [] and not res.empty_confirmed


# --- 福岡市 暫定ページの犬（city_fukuoka_interim-1） ----------------------------------------------------------------------
# 11/06 00:05 の収集では URL が HTTP 404 だった（市が 0 頭で一時的に消した）。同日中に同じ URL で復活し、0 頭の日の文は
# 「現在、飼い主不明の迷い犬はセンターに収容されていません。」の p 1 つ（h2「収容犬一覧」の下の div.f_parallel2 の中）。URL は変わっていない。
# 子のいる版は 2026-10-31 の保存ページ（返還済の 1 件）しか無く、Wayback にも版が無い。そのため文言だけの empty_text にせず、
# 「文の p があり、同じ div に li・写真・表が無い」日だけ 0 頭（empty_absent）にする。
FUK1 = "city_fukuoka_interim-1"
FUK2 = "city_fukuoka_interim-2"


def test_fukuoka_1_zero_day_is_zero_by_absence():
    res = _run(FUK1, _fx("w006_city_fukuoka_doghoused_zero_20261106.html"))
    assert res.animals == []
    assert res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_fukuoka_1_url_is_unchanged():
    assert (
        SOURCES[FUK1].url
        == "https://www.city.fukuoka.lg.jp/hofuku/dobutsukanri/life/doghoused-.html"
    )


def test_fukuoka_1_day_with_a_dog_does_not_show_the_zero_sentence():
    text = _text(_fx("w006_city_fukuoka_doghoused_20261031.html"))
    assert "収容されていません" not in text


def test_fukuoka_1_closed_dog_day_is_still_zero_as_before():
    res = _run(FUK1, _fx("w006_city_fukuoka_doghoused_20261031.html"))
    assert res.animals == [] and res.empty_confirmed


@pytest.mark.parametrize("edit", [("返還済", ""), ("管理番号", "整理番号")])
def test_fukuoka_1_stale_sentence_with_a_dog_row_is_not_zero(edit):
    # 手編集で文を消し忘れたまま子の行が足された日。読めても（状況が空）、項目名が変わって読めなくても、li が残るので 0 頭にしない
    zero = _fx("w006_city_fukuoka_doghoused_zero_20261106.html")
    dog = BeautifulSoup(_fx("w006_city_fukuoka_doghoused_20261031.html"), "lxml").select_one(
        "div.f_parallel2"
    )
    rows = "".join(str(ul) for ul in dog.select("ul")).replace(*edit)
    changed = zero.replace("</b></p>", "</b></p>" + rows, 1)
    assert changed != zero
    res = _run(FUK1, changed)
    assert not res.empty_confirmed


def test_fukuoka_1_sentence_gone_is_not_zero():
    zero = _fx("w006_city_fukuoka_doghoused_zero_20261106.html")
    changed = zero.replace("現在、飼い主不明の迷い犬はセンターに収容されていません。", "")
    assert changed != zero
    res = _run(FUK1, changed)
    assert res.animals == [] and not res.empty_confirmed


def test_fukuoka_2_cat_page_is_untouched_by_the_dog_sentence():
    # 猫ページの 0 頭の日の文言は未確認のまま。犬の文には当たらず、従来どおり
    res = _run(FUK2, _fx("w006_city_fukuoka_cathoused_20261031.html"))
    assert res.animals == [] and res.empty_confirmed  # 死亡の 1 件だけ（全行除外）
