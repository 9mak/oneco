"""T521（2026-10-07）静岡県 迷い犬情報一覧と、0 頭の日に一覧の器ごと消えるページ用の empty_absent のテスト（ネットワークなし）。

静岡県の一覧（CMS の子ページ一覧）は、0 頭の日に ul.listlink が丸ごと出なくなり、0 頭の文言も出ない。
2026-10-06・10-07 の 0:05 の収集はこれで failed になった。Wayback 2025-08-31・2025-10-10 も同じ作りの 0 頭の日で、
ul.listlink が無い以外は動物がいる日（2025-03〜2026-05 の 8 版）と同じ。empty_absent は「枠（見出し）があり、
個体ページへのリンクも一覧の器も 1 つも無い」ときだけ 0 頭とする。枠が無い日（ブロック画面・作り替え）や、
器の名前が変わってもリンクが残る日は failed のまま通知される。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Executor, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
URL = "https://www.pref.shizuoka.jp/kenkofukushi/eiseiyakuji/dobutsuaigo/1066835/index.html"


def _src() -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "pref_shizuoka")


def _collect(html: str, details: dict[str, str] | None = None):
    src = _src()
    recipe = Recipe.load(ROOT / src.recipe)
    ex = Executor(FakeFetcher({URL: html, **(details or {})}), recipe)
    docs = ex.resolve(src.url)
    return build(src, recipe, docs, ex.visited)


def test_shizuoka_today_zero_day_without_list_is_empty():
    res = _collect((FIX / "t521_pref_shizuoka_20261007.html").read_text(encoding="utf-8"))
    assert res.animals == [] and res.empty_confirmed


def test_shizuoka_wayback_zero_day_is_empty():
    res = _collect((FIX / "t521_pref_shizuoka_wb20251010.html").read_text(encoding="utf-8"))
    assert res.animals == [] and res.empty_confirmed


def test_shizuoka_list_present_but_details_unreadable_is_not_empty():
    """一覧にリンクがあるのに子が読めない日は 0 頭にしない（ここでは子を辿らずに入口だけで照合する）。"""
    src = _src()
    recipe = Recipe.load(ROOT / src.recipe)
    html = (FIX / "t521_pref_shizuoka_wb20250915.html").read_text(encoding="utf-8")
    res = build(src, recipe, [], [Doc(url=URL, html=html, soup=BeautifulSoup(html, "lxml"))])
    assert res.empty_confirmed is False


def test_shizuoka_list_renamed_but_links_remain_is_not_empty():
    """器のクラス名が変わって follow_all が 1 本も拾えない日（構造の変更）は failed のまま。"""
    html = (FIX / "t521_pref_shizuoka_wb20250915.html").read_text(encoding="utf-8").replace(
        'class="listlink clearfix"', 'class="childlist"')
    res = _collect(html)
    assert res.animals == [] and res.empty_confirmed is False


def test_shizuoka_page_without_frame_is_not_empty():
    """ブロック画面や作り替えで見出しの枠が無い日は 0 頭にしない。"""
    res = _collect("<html><body><p>Request unsuccessful. Incapsula incident ID: 0</p></body></html>")
    assert res.animals == [] and res.empty_confirmed is False


def test_empty_absent_generic_rules():
    src = Source(slug="t", name="t", municipality="t", prefecture="静岡県", url="https://x.jp/", kind="stray", species="dog")
    recipe = Recipe.from_dict({"rows": "ul.list li", "empty_absent": {"page": "h1:-soup-contains('一覧')", "none": "ul.list, a[href*='/c/']"}})

    def doc(h: str) -> Doc:
        return Doc(url="https://x.jp/", html=h, soup=BeautifulSoup(h, "lxml"))

    assert build(src, recipe, [doc("<h1>迷い犬情報一覧</h1><p>説明</p>")]).empty_confirmed is True
    assert build(src, recipe, [doc("<h1>迷い犬情報一覧</h1><ul class='list'></ul>")]).empty_confirmed is False
    assert build(src, recipe, [doc("<h1>迷い犬情報一覧</h1><div><a href='/c/1.html'>1</a></div>")]).empty_confirmed is False
    assert build(src, recipe, [doc("<h1>お知らせ</h1>")]).empty_confirmed is False
