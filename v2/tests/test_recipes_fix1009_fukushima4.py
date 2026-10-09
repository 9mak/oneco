"""福島県 相双支所 迷子犬（pref_fukushima-4）の 0 頭の日（2026-10-09）のテスト（ネットワークなし）。

10/8 にいた 1 頭（20260915-01）が消えた 10/9 は、値の無い雛形の表（管理番号・保護日…の見出しだけ）が残り、0 頭の文言は出ない。
管理番号に数字の無い行を捨て、捨てた行が全部なら 0 頭と確定する（10/9 0:05 の収集はこの日 failed）。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "pref_fukushima-4")
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_fukushima_4_template_only_day_is_empty():
    res = _run("fix1009_fukushima-4_20261009_template.html")
    assert res.animals == [] and res.empty_confirmed


def test_fukushima_4_day_with_a_dog_is_unchanged():
    (a,) = _run("fix1009_fukushima-4_20261005.html").animals
    assert (a["id"], a["management_no"], a["shelter_date"], a["breed"]) == ("456e942e700f", "20260915-01", "令和8年9月15日", "雑種(ビーグル系)")
