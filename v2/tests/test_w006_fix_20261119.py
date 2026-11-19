"""W006 2026-11-19 の通知の直し（ネットワークなし）。

さいたま市（保護犬）city_saitama-1: 11/18 に収容された R08-17 が載っているのに「本日は 0 頭」と出ていた
  （T632 の「0 頭のまま本文が変わった」の通知で発見）。管理番号が p ではなく div > span に入る作りの日で行が取れず、
  0 頭の根拠にしていた雛形の「管理番号 R08-」が、本物の「管理番号 R08-17」にも含まれるので 0 頭と確定していた。
  - 行の始まりを、自分の文字に「管理番号」を持つ要素（タグを問わない）にする
  - 0 頭の根拠を city_saitama-2（T631）と同じ empty_absent にする（見出しがあり、番号の付いた管理番号も値の入った収容日も無い）
岡山市（保護動物情報）city_okayama: 個別情報の記事が掲載期限で消え、入口の一覧に「保護猫情報一覧」「保護犬情報一覧」と
  訓練プロジェクトの記事だけが残った日に「0 頭で empty_text も無い」で読めなかった（以前の 0 頭の日は「現在、保護犬はいません」の記事が出ていた）。
  - 入口の一覧に、一覧ページと訓練プロジェクト以外の記事が 1 本も無い日を 0 頭にする（empty_absent）。
    個別情報の題名が変わった日・知らない記事が出た日は 0 頭にせず failed で通知される
fixture は実ページ（script・style を落とした）: さいたま市は 2026-11-19 と Wayback 4 版、岡山市は 2026-11-19 と本番の last_ok（2026-11-18）。
同じ通知の鳥取市 -3（その他の動物）と石狩 江別保健所 -1（迷い犬猫）は、本文が変わったのは同じページの別の節（犬猫の譲渡）で、
この slug の 0 頭は実ページのとおりだった（直しなし）。
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector.extract import Result, empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _collect(slug: str, pages: dict[str, str | bytes]) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _single(slug: str, html: str) -> Collected:
    return _collect(slug, {SOURCES[slug].url: html})


def _res(c: Collected) -> Result:
    assert c.result is not None, c.error
    return c.result


def _hits(slug: str, url: str, html: str) -> list[str]:
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))
    return [h.kind for h in empty_hits(recipe, [doc], [doc])]


def _swap(html: str, old: str, new: str) -> str:
    assert old in html, old
    return html.replace(old, new)


# --- さいたま市（保護犬） --------------------------------------------------------------------------------------------
SAITAMA = "city_saitama-1"
SAI_TODAY = "w006_city_saitama-1_child_20261119.html"      # R08-17（管理番号が div > span。11/18 収容）と空の雛形
SAI_IMG = "https://www.city.saitama.lg.jp/008/004/003/004/p003138_d/img/"
SAI_CHILD = {                                              # 子のいる日: 管理番号と ID（直す前のレシピと同じ値）
    "w006_city_saitama-1_child_wb20260609.html": [("R8-3", "533e09f2822e")],
    "w006_city_saitama-1_child_wb20250620.html": [("R07-8", "3bef44d14d25")],     # 写真なし・前年度の番号
    "t517_saitama-1.html": [("R8-8", "17cc2dc55d54"), ("R8-9", "db341e0551bf")],  # 1 頭目が平ら・2 頭目が div の中
}
SAI_ZERO = ["w006_city_saitama-1_zero_wb20260210.html", "w006_city_saitama-1_zero_wb20250715.html"]   # 雛形だけの日（R08-・R07-）


def test_saitama_1_reads_the_dog_whose_number_is_in_a_span():
    c = _single(SAITAMA, _fx(SAI_TODAY))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals                                  # 空の雛形（管理番号 R08-）は動物にしない
    assert {k: a.get(k) for k in ("management_no", "shelter_date", "location", "breed", "color", "sex", "size", "note", "species")} == {
        "management_no": "R8-17", "shelter_date": "令和8年11月18日", "location": "浦和区木崎", "breed": "雑種", "color": "茶白",
        "sex": "オス", "size": "中型", "note": "なし", "species": "dog"}
    assert a["age"] in ("10~14歳", "10～14歳")
    assert a["image_url"] == SAI_IMG + "005_s.jpg"          # 雛形の写真（alt 作業用）ではない


@pytest.mark.parametrize("name", [SAI_TODAY, *SAI_CHILD])
def test_saitama_1_zero_evidence_does_not_hold_on_days_with_a_dog(name):
    # 直す前は雛形の「管理番号 R08-」が empty_text で、子のいる日にも成立していた
    assert _hits(SAITAMA, SOURCES[SAITAMA].url, _fx(name)) == []


@pytest.mark.parametrize("name,want", list(SAI_CHILD.items()))
def test_saitama_1_other_layouts_keep_their_dogs_and_ids(name, want):
    c = _single(SAITAMA, _fx(name))
    assert c.status == "ok", c.error
    assert [(a["management_no"], a["id"]) for a in _res(c).animals] == want


@pytest.mark.parametrize("name", SAI_ZERO)
def test_saitama_1_template_only_day_is_a_confirmed_zero(name):
    c = _single(SAITAMA, _fx(name))
    assert c.status == "empty", (c.status, c.error)
    assert _res(c).animals == []


def test_saitama_1_unreadable_dog_is_not_a_zero():
    # 管理番号の語が変わって行が取れなくなった日は、値の入った収容日が残っているので 0 頭にしない
    html = _swap(_fx(SAI_TODAY), "管理番号 R08-17", "整理番号 R08-17")
    c = _single(SAITAMA, html)
    assert c.status not in ("ok", "empty"), (c.status, c.error)


def test_saitama_1_without_the_heading_is_not_a_zero():
    # 枠（見出し）が無い日は、雛形だけでも 0 頭と言わない
    html = _swap(_fx(SAI_ZERO[0]), "迷子の犬を保護しています", "お知らせ")
    assert _single(SAITAMA, html).status != "empty"


# --- 岡山市（保護動物情報） ------------------------------------------------------------------------------------------
OKAYAMA = "city_okayama"
OKA_URL = SOURCES[OKAYAMA].url
OKA_ZERO = "w006_city_okayama_index_zero_20261119.html"    # 保護猫情報一覧・訓練プロジェクト・保護犬情報一覧 の 3 本だけ
OKA_CHILD = "w006_city_okayama_index_child_20261118.html"  # 上の 3 本＋「1D2026074保護犬個別情報」
OKA_DOG_URL = "https://www.city.okayama.jp/kurashi/0000086918.html"
OKA_DOG = "w006_city_okayama_dog_20261118.html"


def test_okayama_no_individual_article_is_a_confirmed_zero():
    c = _single(OKAYAMA, _fx(OKA_ZERO))
    assert c.status == "empty", (c.status, c.error)
    assert _res(c).animals == []


def test_okayama_day_with_a_dog_reads_it_and_is_never_zero():
    c = _collect(OKAYAMA, {OKA_URL: _fx(OKA_CHILD), OKA_DOG_URL: _fx(OKA_DOG)})
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in _res(c).animals] == ["1D2026074"]
    assert _hits(OKAYAMA, OKA_URL, _fx(OKA_CHILD)) == []
    assert _hits(OKAYAMA, OKA_DOG_URL, _fx(OKA_DOG)) == []
    assert _hits(OKAYAMA, OKA_URL, _fx("w006a_city_okayama_index_20261107.html")) == []     # 11/07 の子のいる日


def test_okayama_renamed_individual_article_is_not_a_zero():
    # 個別情報の題名が変わって辿れなくなった日は、知らない記事が一覧にあるので 0 頭にしない
    html = _swap(_fx(OKA_CHILD), "1D2026074保護犬個別情報", "1D2026074 保護犬のお知らせ")
    assert _single(OKAYAMA, html).status != "empty"


def test_okayama_unknown_article_is_not_a_zero():
    # 一覧ページと訓練プロジェクト以外の記事が出た日（動物かどうか分からない）は人が見る
    html = _swap(_fx(OKA_ZERO), "保護犬の人馴れ訓練プロジェクト", "保護動物についてのお知らせ")
    assert _single(OKAYAMA, html).status != "empty"


def test_okayama_without_the_article_list_is_not_a_zero():
    html = _swap(_fx(OKA_ZERO), "category_end", "category_gone")
    assert _single(OKAYAMA, html).status != "empty"
