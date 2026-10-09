"""北九州市 保護犬（city_kitakyushu-1）の 0 頭の日のテスト（ネットワークなし）。

0 頭の日は「収容表」の tbody に td が全部空の雛形行が 1 つ残り、0 頭の文言は出ない（10/9 11:28 の収集はこの日 failed。
Wayback 10 版〔2024-12〜2026-03〕中 3 版も同じ）。収容日に数字の無い行を捨て、捨てた行が全部なら 0 頭と確定する。
犬がいた日（Wayback 2026-03-12 の保存ページ、2 頭）は直す前と同じ結果になることも確かめる。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "city_kitakyushu-1")
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_kitakyushu_1_template_row_only_day_is_empty():
    res = _run("fix1009_kitakyushu-1_20261009_template.html")
    assert res.animals == [] and res.empty_confirmed


def test_kitakyushu_1_day_with_dogs_is_unchanged():
    a, b = _run("fix1009_kitakyushu-1_wb20260312.html").animals
    assert (a["shelter_date"], a["location"], a["breed"], a["color"], a["sex"], a["size"]) == ("3月6日", "門司区", "シーズー", "白・茶・灰", "メス", "小")
    assert (b["shelter_date"], b["location"], b["breed"], b["color"], b["sex"], b["size"]) == ("3月11日", "八幡西区", "雑", "茶・白", "メス", "小")
