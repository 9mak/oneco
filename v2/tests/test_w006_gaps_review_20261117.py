"""W006 T640 #129 reviewer F-01: 子のいる日にページの作りが変わっても 0 頭と読まない（2026-11-17・ネットワークなし）。

札幌市の譲渡犬（city_sapporo-3）と福島県 会津支所の譲渡犬（pref_fukushima-8）・相双支所の譲渡猫（pref_fukushima-9）は、
0 頭の条件（empty_absent の none）が行の形（h2 + table・table の中の img）に縛られていて、表が div に、h2 が h3 に変わるだけで
本物の子がいる日を 0 頭と読んでいた。0 頭の条件を行の形から切り離し、動物の写真そのもの（と札幌は管理番号の見出し）で決める。
0 頭の日（今日の札幌の犬・会津の猫・相双の犬）は、飾りの画像（ページ上部の画像・リンクのアイコン）があっても 0 頭のまま。
"""

import re
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def _tables_to_divs(html: str) -> str:
    return re.sub(r"<(/?)(table|thead|tbody|tr|th|td)\b", r"<\1div", html)


def test_sapporo_dog_child_day_with_tables_as_divs_is_not_zero():
    html = _tables_to_divs(_fx("w006_city_sapporo-3_child_wb20260518.html"))
    assert not _zero(_run("city_sapporo-3", html))


def test_sapporo_dog_child_day_with_h2_as_h3_is_not_zero():
    html = re.sub(r"<(/?)h2\b", r"<\1h3", _fx("w006_city_sapporo-3_child_wb20260518.html"))
    assert not _zero(_run("city_sapporo-3", html))


def test_sapporo_dog_today_is_still_zero():
    assert _zero(_run("city_sapporo-3", _fx("w006_city_sapporo-3_20261117.html")))


def test_fukushima_aizu_dog_with_tables_as_divs_is_not_zero():
    for name in ("w006_pref_fukushima-8_20261117.html", "w006_pref_fukushima-8_child_wb20261016.html"):
        assert not _zero(_run("pref_fukushima-8", _tables_to_divs(_fx(name)))), name


def test_fukushima_soso_cat_with_tables_as_divs_is_not_zero():
    assert not _zero(_run("pref_fukushima-9", _tables_to_divs(_fx("w006_pref_fukushima-9_20261117.html"))))


def test_fukushima_zero_days_stay_zero_with_decorative_images():
    # 会津の猫（今日）・相双の犬（今日・Wayback 2025-07-06）は、見出しより前の画像やリンクのアイコンがあっても 0 頭
    for slug, name in (("pref_fukushima-10", "w006_pref_fukushima-10_20261117.html"),
                       ("pref_fukushima-11", "w006_pref_fukushima-11_20261117.html"),
                       ("pref_fukushima-11", "w006_pref_fukushima-11_zero_wb20250706.html")):
        assert _zero(_run(slug, _fx(name))), name
