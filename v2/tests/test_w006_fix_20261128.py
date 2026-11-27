"""2026-11-28 の収集で見つかった 2 件（ネットワークなし。fixture は 11/28 の実ページ）。

- 札幌市 迷子猫（city_sapporo-2）: 0 頭の文が「現在迷子猫の収容されていません」（「は」が「の」の誤字）になり、空欄の雛形の表だけが
  残って「0 頭で empty_text も無い」で読めなかった。POLICY.md 方針 52（新しい書き方で読めなくなったら足す）
- 佐賀県 佐賀中部（pref_saga-1）: 子のいる日にも「その他の保護動物」の空の表に「現在保護中の動物はいません」が出る（audit_empty が当たった）。
  犬の表が読めなくなった日に「本日は 0 頭」と言い切る穴なので、ほかの佐賀県の事務所（-2〜-5）と同じく、表の中に写真が 1 枚も無いことを
  0 頭の根拠にする（方針 52: 誤って 0 頭と出す穴は見つけしだい直す）
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build, empty_hits
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _recipe(slug: str) -> Recipe:
    return Recipe.load(ROOT / "recipes" / f"{slug}.yaml")


def _doc(html: str) -> Doc:
    return Doc(url="https://example.jp/p.html", html=html, soup=BeautifulSoup(html, "lxml"))


def _build(slug: str, html: str):
    return build(SOURCES[slug], _recipe(slug), [_doc(html)])


def _hits(slug: str, html: str):
    return empty_hits(_recipe(slug), [_doc(html)])


# --- 札幌市 迷子猫（city_sapporo-2） -------------------------------------------------------------------------------
def test_sapporo_2_zero_day_with_typo_is_zero():
    html = _fx("w006_city_sapporo-2_zero_20261128.html")
    assert "現在迷子猫の収容されていません" in html
    res = _build("city_sapporo-2", html)
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text"


def test_sapporo_2_cat_day_is_still_read():
    res = _build("city_sapporo-2", _fx("w006_city_sapporo-2_cat_20261125.html"))
    assert len(res.animals) == 1 and not res.empty_confirmed


# --- 佐賀県 佐賀中部（pref_saga-1） --------------------------------------------------------------------------------
def test_saga_1_dog_day_has_no_zero_evidence_though_the_other_table_says_none():
    html = _fx("w006_pref_saga-1_kids_20261128.html")
    assert "現在保護中の動物はいません" in html   # その他の保護動物の空の表
    assert _hits("pref_saga-1", html) == []
    res = _build("pref_saga-1", html)
    assert len(res.animals) == 1 and res.animals[0]["species"] == "dog" and not res.empty_confirmed


def test_saga_1_zero_evidence_needs_no_photo_in_any_table():
    # 犬の表の項目が読めなくなった日（ここでは表の文字を全部消して再現）でも、表に写真が残る日は 0 頭の根拠にならない
    soup = BeautifulSoup(_fx("w006_pref_saga-1_kids_20261128.html"), "lxml")
    dog = next(t for t in soup.select("table.__wys_table") if t.find("img"))
    for text in dog.find_all(string=True):
        text.replace_with("")
    html = str(soup)
    assert _hits("pref_saga-1", html) == []
    assert not _build("pref_saga-1", html).empty_confirmed


def test_saga_1_zero_day_is_confirmed_by_no_photo_in_any_table():
    res = _build("pref_saga-1", _fx("t518_saga-1_wb20251205.html"))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_saga_1_table_class_renamed_is_not_zero():
    html = _fx("t518_saga-1_wb20251205.html").replace("__wys_table", "renamed_table")
    assert not _build("pref_saga-1", html).empty_confirmed
