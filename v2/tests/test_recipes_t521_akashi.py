"""T521（2026-10-07）明石 飼い主募集の猫（city_akashi-3）の note と、項目をつなぐ指定 join のテスト（ネットワークなし）。

note を性格の本文にしたら（T521）、「トライアル中」の印が出なくなった（ゲート judgeA F6）。トライアル中の子も載せる方針なので、
印と性格を両方 note に出す（「トライアル中。<性格>」）。印は 2026 年の作りでは仮名の行、2024-10 の作り（仮名の行が無い）では
品種（年齢）の行にあり、「トライアル予定」もある。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "city_akashi-3")
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_akashi_trial_mark_and_personality_both_in_note_today():
    notes = {a["name"]: a["note"] for a in _run("t521_city_akashi-3_20261005.html").animals}
    assert notes["すいか"] == "トライアル中。人慣れ訓練中の黒白の女の子です。運動神経が抜群です。"
    assert notes["よつば"] == "小柄な白猫の女の子です。人慣れ練習中です。よく鳴いてアピールしてくれます。"
    assert len(notes) == 11 and sum("トライアル" in n for n in notes.values()) == 1


def test_akashi_trial_mark_on_breed_row_in_2024_layout():
    notes = [a["note"] for a in _run("t521_city_akashi-3_wb20241007.html").animals]
    assert len(notes) == 12
    assert "トライアル予定。とても人懐こく、なでられるのがとても大好きです。 遊んだ後はよく無防備な格好で寝ています。" in notes
    assert sum(n.startswith("トライアル中。") for n in notes) == 2
    assert sum("トライアル" in n for n in notes) == 3


def test_join_skips_missing_and_repeated_parts():
    src = Source(slug="t", name="t", municipality="t", prefecture="兵庫県", url="https://x.jp/", kind="adoption", species="cat")
    recipe = Recipe.from_dict({"rows": "table", "image": "img@src", "fields": {
        "name": {"label": "仮名"},
        "note": {"join": [{"label": "仮名", "regex": "(トライアル中)"}, {"label": "品種", "regex": "(トライアル中)"},
                          {"label": "性格"}], "sep": "。"}}})

    def notes(h: str) -> list[str | None]:
        return [a["note"] for a in build(src, recipe, [Doc(url="https://x.jp/", html=h, soup=BeautifulSoup(h, "lxml"))]).animals]

    row = "<table><tr><th>仮名</th><td>{n}</td></tr><tr><th>品種</th><td>{b}</td></tr><tr><th>性格</th><td>{c}</td></tr><tr><td><img src='/a.jpg'></td></tr></table>"
    assert notes(row.format(n="たま トライアル中", b="Mix", c="元気")) == ["トライアル中。元気"]
    assert notes(row.format(n="たま", b="Mix", c="元気")) == ["元気"]
    assert notes(row.format(n="たま", b="Mix", c="")) == [None]
