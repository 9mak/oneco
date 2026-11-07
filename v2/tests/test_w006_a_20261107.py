"""W006（2026-11-07）未読の掲載元 A 班: 大船渡保健所 迷子猫（pref_iwate_ofunato-2）・名古屋市 譲渡犬（city_nagoya-2）の 0 頭の日（ネットワークなし）。

大船渡 迷子: 子のいる日は h2「元の飼い主を探しています」の節がある。子がいなくなった 10/20 からは節ごと消え、0 頭の文言も出ない
  （empty_text が当たらず 19 日 failed）。節ごと消える日を、本文の枠（h1）があり迷子の節の見出し・写真が 1 つも無い日として 0 頭にする。
名古屋市 譲渡犬: ページは「長期収容犬を紹介します」と書くが 2025-12〜2026-11 の 4 版とも犬を載せていない。0 頭は「2 節の見出しがあり、
  犬を載せうる要素が 1 つも無い日」。犬が載る作りは未確認なので、載った日は 0 頭にならず failed になる（rows は今のページに無いものを指す）。
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

OFU_ZERO = "w006_pref_iwate_ofunato-2_zero_20261107.html"
OFU_CHILD = "w006_pref_iwate_ofunato-2_child_20261019.html"
NG_ZERO = "w006_city_nagoya-2_zero_20261107.html"
NG_WB = "w006_city_nagoya-2_wb20251210.html"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(
        recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))]
    )


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 大船渡 迷子猫 -------------------------------------------------------------------------


def test_ofunato_zero_day_without_the_stray_section_is_empty():
    assert _zero(_single("pref_iwate_ofunato-2", _fx(OFU_ZERO)))


def test_ofunato_child_day_is_still_read_and_never_zero():
    c = _single("pref_iwate_ofunato-2", _fx(OFU_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    assert _hits("pref_iwate_ofunato-2", _fx(OFU_CHILD)) == []


def test_ofunato_old_layout_days_never_become_zero_by_absence():
    # Wayback 2025-09・2026-03 の作り（h2「【保護】もとの飼い主さんを探しています」が毎日あり、0 頭の日は
    # 「現在、もとの飼主さんを待っている動物はおりません」）。節の見出しが none に当たり、0 頭の根拠は従来の empty_text だけ
    for name in (
        "w006_pref_iwate_ofunato-2_wb20250915.html",
        "w006_pref_iwate_ofunato-2_wb20260309.html",
    ):
        kinds = [h.kind for h in _hits("pref_iwate_ofunato-2", _fx(name))]
        assert "empty_absent" not in kinds and kinds == ["empty_text"], (name, kinds)


def test_ofunato_missing_frame_is_not_zero():
    # 本文の h1 が無い（ブロック画面・作り替え）日は 0 頭にしない
    html = _fx(OFU_ZERO).replace("<h1>", "<p>").replace("</h1>", "</p>")
    assert not _zero(_single("pref_iwate_ofunato-2", html))


def test_ofunato_stray_heading_reworded_is_not_zero():
    # 迷子の節が戻り、見出しの言い回しだけ変わった日（写真が付く）は 0 頭にしない
    html = _fx(OFU_CHILD).replace("元の飼い主を探しています", "保護しています")
    assert "保護しています" in html
    assert _hits("pref_iwate_ofunato-2", html) == []
    assert not _zero(_single("pref_iwate_ofunato-2", html))


def test_ofunato_stray_heading_back_on_zero_page_is_not_zero():
    html = _fx(OFU_ZERO).replace(
        "<h2>保護猫譲渡会を開催します！</h2>",
        "<h2>元の飼い主を探しています</h2><p>準備中</p><h2>保護猫譲渡会を開催します！</h2>",
    )
    assert "元の飼い主を探しています" in html
    assert not _zero(_single("pref_iwate_ofunato-2", html))


# --- 名古屋市 譲渡犬 -----------------------------------------------------------------------


def test_nagoya_dog_is_read_as_recipe():
    s = SOURCES["city_nagoya-2"]
    assert (s.mode, s.enabled, s.kind, s.photo) == ("recipe", True, "adoption", "pending")


def test_nagoya_dog_zero_days_are_empty():
    for name in (NG_ZERO, NG_WB):
        assert _zero(_single("city_nagoya-2", _fx(name))), name


def _with(html: str, add: str) -> str:
    marker = '<div id="reference">'
    assert marker in html
    return html.replace(marker, add + marker, 1)


def test_nagoya_dog_listing_elements_are_never_zero():
    base = _fx(NG_ZERO)
    adds = {
        "h3": "<h3>ポチ</h3><p>説明</p>",
        "img": '<p><img src="/uploaded/image/1.jpg" alt="ポチ"></p>',
        "table": "<table><tr><td>ポチ</td></tr></table>",
        "pdf": '<p><a href="/uploaded/attachment/1.pdf">長期収容犬</a></p>',
        "child": '<p><a href="/kurashi/pet/1015473/1015483/1999999.html">ポチ</a></p>',
        "label": "<p>性別：オス</p>",
        "h2": "<h2>ポチ</h2><p>おとなしい</p>",
    }
    for key, add in adds.items():
        c = _single("city_nagoya-2", _with(base, add))
        assert not _zero(c), key
        assert c.status == "failed", (key, c.status)


def test_nagoya_dog_missing_section_heading_is_not_zero():
    html = _fx(NG_ZERO).replace("長期収容中の犬", "長期収容犬")
    assert not _zero(_single("city_nagoya-2", html))
