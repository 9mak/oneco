"""W006（2026-11-07）「静的に取れていないページ」B 班: 相模原市 収容犬の公示（city_sagamihara-2）など、
link_only だった掲載元を、子が載った日に読めなければ failed になる形で読む（ネットワークなし）。

city_sagamihara-2: 0 頭の日は h2「公示に基づく収容犬情報」の下に「現在、迷い犬の情報はありません。」の 1 文だけが出る。
子のいる日（Wayback 2026-09-03）はこの文が消え、p「令和…の公示」・p「整理番号　N」・ul（収容日時・収容場所・犬の種類…）が並ぶ。
"""

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector import recipe as recipe_mod
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# ---- 相模原市 収容犬の公示 ----
SAGA_ZERO = "w006_city_sagamihara-2_zero_20261107.html"
SAGA_ZERO_WB = "w006_city_sagamihara-2_zero_wb20250613.html"
SAGA_DOG = "w006_city_sagamihara-2_dog_wb20260903.html"


def test_sagamihara_is_recipe_mode():
    assert SOURCES["city_sagamihara-2"].mode == "recipe"


def test_sagamihara_zero_days_are_empty():
    for name in (SAGA_ZERO, SAGA_ZERO_WB):
        assert _zero(_single("city_sagamihara-2", _fx(name))), name


def test_sagamihara_dog_day_is_read_and_never_zero():
    c = _single("city_sagamihara-2", _fx(SAGA_DOG))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert a["species"] == "dog"
    assert a["breed"] == "雑種" and a["color"] == "黒白" and a["sex"] == "オス"
    assert "二本松2-30" in a["location"]
    assert a["shelter_date"].startswith("令和8年8月28日")
    assert _hits("city_sagamihara-2", _fx(SAGA_DOG)) == []


def test_sagamihara_unknown_dog_layout_fails_instead_of_zero():
    # 犬が載った日にレシピで行が取れなくなった（作りが変わった）日は 0 頭にせず failed
    html = _fx(SAGA_DOG).replace("<li>収容日時", "<li>収容した日時").replace("整理番号", "番号")
    c = _single("city_sagamihara-2", html)
    assert not _zero(c)
    assert c.status == "failed"


def test_sagamihara_zero_sentence_alongside_other_content_is_not_zero():
    # 「情報はありません」の文が残ったまま別の内容（表・リスト・別の段落）が足された日は 0 頭にしない
    base = _fx(SAGA_ZERO)
    for extra in ("<ul><li>収容日時　令和8年11月8日</li></ul>", "<p>令和8年11月8日の公示</p>", "<table><tr><td>x</td></tr></table>"):
        html = base.replace("<p>現在、迷い犬の情報はありません。</p>", "<p>現在、迷い犬の情報はありません。</p>" + extra)
        assert not _zero(_single("city_sagamihara-2", html)), extra


# ---- 神奈川県動物愛護センター その他動物（pref_kanagawa-3） ----
# 犬猫以外（カメ・インコ等）は species other で載せる方針（他の掲載元と同じ）に合わせ、link_only をやめて PDF を読む。
# 入口は PDF（acsonota.pdf）を 1 本落とすだけ。0 頭の日は PDF に「現在、収容期間中の犬・猫以外の動物はいません」の 1 文だけ、
# 子のいる日（Wayback 2025-06・2026-10-23）の PDF にはその文が無く表の行がある。
KG = SOURCES["pref_kanagawa-3"]
KG_PDF = "https://www.pref.kanagawa.jp/osirase/1594/awc/assets/pdf/lost/acsonota.pdf"


def _kg(monkeypatch, name: str, tables: list | None = None) -> Collected:
    pdf = json.loads(_fx(name))
    rows = pdf["pdf_tables"] if tables is None else tables
    monkeypatch.setattr(recipe_mod, "_make_pdf_doc",
                        lambda url, content, columns=1: Doc(url=url, pdf_tables=rows, pdf_text=pdf["pdf_text"]))
    pages = {KG.url: _fx("w006_pref_kanagawa-3_entry_20261107.html"), KG_PDF: b"%PDF-1.4\n"}
    return collect_one(KG, FakeFetcher(pages))


def test_kanagawa_other_is_recipe_mode_and_photo_stays_pending():
    assert KG.mode == "recipe"
    assert KG.photo == "pending"


def test_kanagawa_other_zero_day_is_empty(monkeypatch):
    assert _zero(_kg(monkeypatch, "w006_pref_kanagawa-3_zero_20261107.json"))


@pytest.mark.parametrize("name,n", [("w006_pref_kanagawa-3_wb20261023.json", 1), ("w006_pref_kanagawa-3_wb20250602.json", 2)])
def test_kanagawa_other_animal_days_are_read_as_other_and_never_zero(monkeypatch, name, n):
    c = _kg(monkeypatch, name)
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == n
    assert {a["species"] for a in c.result.animals} == {"other"}


def test_kanagawa_other_table_without_rows_and_without_the_zero_sentence_is_not_zero(monkeypatch):
    # 表の作りが変わって行が取れず、0 頭の文も無い日は 0 頭にしない
    assert not _zero(_kg(monkeypatch, "w006_pref_kanagawa-3_wb20261023.json", tables=[]))
