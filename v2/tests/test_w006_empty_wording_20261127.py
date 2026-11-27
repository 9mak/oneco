"""W006 毎朝の直し 2026-11-27: 0 頭の書き方が変わって「0 頭で empty_text も無い」になった 3 掲載元（POLICY.md 方針 52・25）。

fixture は 11/26〜27 の収集が保存した実ページ（zero は 0 頭の日、child は子のいた最後の日）。PDF の中身は入口ページに無い（豊田は PDF リンクごと消えた）。
- 豊田市: 入口ページから PDF リンクが消え、本文に「現在、豊田市では迷子の動物を収容していません。」の 1 文が出る（11/26〜）
- 香川県 東讃: 収容が無い日は PDF リンクが消え「現在、情報はありません。」（11/27〜。小豆は「現在、収容動物情報はありません」だった）
- 埼玉県 東松山: 新着情報が「【2026年11月25日更新】現在、収容はありません。」（11/27〜。以前は「現在収容犬情報はありません」）。空欄の雛形 table は残る
どれも子のいた日の保存ページには当たらない（子のいる日を 0 頭に見せない）。
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

TOYOTA_FINAL = "https://www.city.toyota.aichi.jp/sumaikankyo/pet/pet/1073803/1003696.html"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str, redirects: dict[str, str] | None = None) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}, redirects))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == [] and c.result.empty_evidence == "empty_text"


def test_toyota_entry_page_without_pdf_link_and_with_the_one_sentence_is_zero():
    c = _run("city_toyota_pdf", _fx("w006_city_toyota_pdf_zero_20261127.html"), {SOURCES["city_toyota_pdf"].url: TOYOTA_FINAL})
    assert _zero(c), (c.status, c.error)


def test_toyota_the_sentence_is_the_only_text_that_makes_it_zero():
    html = _fx("w006_city_toyota_pdf_zero_20261127.html")
    old = "現在、豊田市では迷子の動物を収容していません。"
    assert old in html
    c = _run("city_toyota_pdf", html.replace(old, "現在、豊田市では迷子の動物の情報を準備しています。"), {SOURCES["city_toyota_pdf"].url: TOYOTA_FINAL})
    assert c.status == "failed" and not _zero(c)


def test_toyota_day_with_the_pdf_link_is_not_zero_by_the_sentence():
    # 10/31 保存の入口ページ（PDF リンクあり＝子のいた日）に新しい文は当たらない
    assert _hits("city_toyota_pdf", _fx("w006_city_toyota_pdf_entry_20261031.html")) == []


def test_kagawa_tosan_zero_day_sentence_is_zero():
    c = _run("pref_kagawa_pdf-1", _fx("w006_pref_kagawa_pdf-1_zero_20261127.html"))
    assert _zero(c), (c.status, c.error)


def test_kagawa_tosan_day_with_the_pdf_link_is_not_zero_by_the_sentence():
    assert _hits("pref_kagawa_pdf-1", _fx("w006_pref_kagawa_pdf-1_child_20261126.html")) == []


def test_higashimatsuyama_new_zero_sentence_with_blank_templates_is_zero():
    c = _run("pref_saitama_higashimatsuyama", _fx("w006_pref_saitama_higashimatsuyama_zero_20261127.html"))
    assert _zero(c), (c.status, c.error)


def test_higashimatsuyama_day_with_an_animal_is_read_and_not_zero():
    c = _run("pref_saitama_higashimatsuyama", _fx("w006_pref_saitama_higashimatsuyama_child_20261124.html"))
    assert c.status == "ok", (c.status, c.error)
    assert c.result is not None and len(c.result.animals) == 1
    assert _hits("pref_saitama_higashimatsuyama", _fx("w006_pref_saitama_higashimatsuyama_child_20261124.html")) == []
