"""T656 直し 1 回目・項目 10（2026-11-20・ネットワークなし）: 子のいた日の保存ページにも当たる 0 頭の根拠の直し。

毎晩の ops/audit_empty.py（11/20 0:05）が挙げた 3 件のうち、群馬県 本所（pref_gunma-1）と松本市 収容（city_matsumoto-1）。
- 群馬県: 一覧が地区ごとに「現在、保管期間中の犬はおりません。」を出す作りで、1 地区に子がいる日（11/19 は西毛に 26-139）にも他の地区が出す
  → empty_text「保管期間中の犬はおりません」が成立していた。地区の見出し付きの文を全部そろえる empty_text_all だけにする
- 松本市: 犬と猫が同じページで、猫が 0 頭の日にも犬がいる（11/19 は犬 8-2、猫「現在、猫の収容はありません。」）
  → empty_text「現在、猫の収容はありません」が成立していた。「収容犬」「収容猫」の見出し付きの文を両方そろえる empty_text_all だけにする
保存ページは本番 last_ok（読むだけ）から複写した（松本は個人保護の連絡先を伏せ字にした）。
"""

import re
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

GUNMA_ENTRY = "w006_pref_gunma-1_entry_20261119.html"
GUNMA_CHILD = "w006_pref_gunma-1_child_20261119.html"
MATSUMOTO = "w006_city_matsumoto-1_dog_20261119.html"


def _gunma(entry_mutate=None) -> Collected:
    s = SOURCES["pref_gunma-1"]
    entry = (FIX / GUNMA_ENTRY).read_text(encoding="utf-8")
    if entry_mutate:
        entry = entry_mutate(entry)
    child = (FIX / GUNMA_CHILD).read_text(encoding="utf-8")
    pages = {s.url: entry}
    for href in set(re.findall(r'href="((?:https://www\.pref\.gunma\.jp)?/page/\d+\.html)"', entry)):
        pages[href if href.startswith("http") else "https://www.pref.gunma.jp" + href] = child
    return collect_one(s, FakeFetcher(pages))


def _matsumoto(mutate=None) -> Collected:
    s = SOURCES["city_matsumoto-1"]
    html = (FIX / MATSUMOTO).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    return collect_one(s, FakeFetcher({s.url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(SOURCES[slug].recipe_path)
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


# --- 群馬県 本所 ---------------------------------------------------------------
def test_gunma_child_day_has_no_zero_evidence_and_is_read():
    c = _gunma()
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in c.result.animals] == ["26-139"]
    entry = (FIX / GUNMA_ENTRY).read_text(encoding="utf-8")
    assert entry.count("現在、保管期間中の犬はおりません。") == 2     # 中毛・北毛。西毛には子がいる
    assert _hits("pref_gunma-1", entry) == []                          # 子のいた日に 0 頭の根拠が当たらない


def test_gunma_zero_when_every_area_says_none():
    def none_everywhere(h: str) -> str:
        # 西毛の子のリンク（管理番号：26-139）を「おりません」の文に置く。0 頭の日は個体ページへのリンクも無い
        out = re.sub(r"<a [^>]*>\s*管理番号：26-139.*?</a>", "現在、保管期間中の犬はおりません。", h, count=1, flags=re.S)
        assert out != h
        return out

    entry = none_everywhere((FIX / GUNMA_ENTRY).read_text(encoding="utf-8"))
    assert entry.count("現在、保管期間中の犬はおりません。") == 3
    hits = _hits("pref_gunma-1", entry)
    assert [h.kind for h in hits] == ["empty_text_all"]
    c = _gunma(none_everywhere)
    assert c.status == "empty", c.error


def test_gunma_one_area_missing_is_not_zero():
    def two_areas_only(h: str) -> str:
        return h.replace("西毛地区（藤岡市、富岡市、安中市、多野郡、甘楽郡）", "西毛地区（藤岡市）")

    assert _hits("pref_gunma-1", two_areas_only((FIX / GUNMA_ENTRY).read_text(encoding="utf-8"))) == []


def test_gunma_recipe_has_no_bare_empty_text():
    assert Recipe.load(SOURCES["pref_gunma-1"].recipe_path).empty_text == []


# --- 松本市 収容 ----------------------------------------------------------------
def test_matsumoto_dog_day_has_no_zero_evidence_and_is_read():
    html = (FIX / MATSUMOTO).read_text(encoding="utf-8")
    assert "現在、猫の収容はありません" in html
    c = _matsumoto()
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1 and c.result.animals[0]["species"] == "dog"
    assert c.result.animals[0]["management_no"] == "8-2"
    assert _hits("city_matsumoto-1", html) == []


def test_matsumoto_zero_only_when_dogs_and_cats_both_none():
    def no_dog(h: str) -> str:
        i = h.index("収容犬No.8-2")
        j = h.index("収容猫", i)
        k = h.rindex("<h", 0, i)
        return h[:k] + "<h3>収容犬</h3><p>現在、犬の収容はありません。</p>" + h[h.rindex("<h", 0, j):]

    html = no_dog((FIX / MATSUMOTO).read_text(encoding="utf-8"))
    hits = _hits("city_matsumoto-1", html)
    assert [h.kind for h in hits] == ["empty_text_all"]
    assert _matsumoto(no_dog).status == "empty"


def test_matsumoto_dog_none_but_cat_present_is_not_zero():
    # 猫だけいる日（犬の文だけ出る）は 0 頭にしない
    def cat_only(h: str) -> str:
        i = h.index("収容犬No.8-2")
        k = h.rindex("<h", 0, i)
        j = h.index("収容猫", i)
        return (h[:k] + "<h3>収容犬</h3><p>現在、犬の収容はありません。</p>" + h[h.rindex("<h", 0, j):]).replace(
            "現在、猫の収容はありません。", "収容猫No.8-3 掲載日 令和8年11月19日")

    assert _hits("city_matsumoto-1", cat_only((FIX / MATSUMOTO).read_text(encoding="utf-8"))) == []


def test_matsumoto_recipe_has_no_bare_empty_text():
    assert Recipe.load(SOURCES["city_matsumoto-1"].recipe_path).empty_text == []
