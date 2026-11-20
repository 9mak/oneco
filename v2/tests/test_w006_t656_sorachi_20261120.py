"""T656 直し 1 回目・項目 2（2026-11-20・ネットワークなし）: 空知 飼い主募集（hokkaido_sorachi-1）の箇条書きの猫。

滝川保健所の「【令和８年11月16日掲載】」は、写真 1 枚の下に「・まめ　メス　黒」「・みかん　オス　茶白」と 1 行 1 頭で書かれる（仮名・種類などのラベルが無い）。
今までは「猫２頭引取となりました」が「引取となりました」（協力動物病院の猫の決定印）に当たって行ごと外れ、2 頭とも載っていなかった。
row_split でこの 1 行を 1 頭ずつに分け、決定印は「方に引取となりました」に絞る。
"""

import re
from dataclasses import replace
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
LIVE = "w006_hokkaido_sorachi-1_20261120.html"   # 2026-11-20 の実ページ（岩見沢 猫 1・由仁 犬 1・滝川 猫 2・深川 猫 1）
OLD = "w006_hokkaido_sorachi-1_20261107.html"     # 11/07（協力動物病院の猫に「引取となりました」）


def _run(fixture: str, mutate=None) -> Collected:
    html = (FIX / fixture).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    return collect_one(SOURCES["hokkaido_sorachi-1"], FakeFetcher({SOURCES["hokkaido_sorachi-1"].url: html}))


def test_takigawa_two_bullet_cats_are_read_one_each():
    c = _run(LIVE)
    assert c.status == "ok", c.error
    # 岩見沢 猫 2（11/20・9/30）・由仁 犬 1・滝川 猫 2（箇条書き）・深川 猫 1
    assert len(c.result.animals) == 6
    assert [a["species"] for a in c.result.animals] == ["cat", "cat", "dog", "cat", "cat", "cat"]
    by = {a["name"]: a for a in c.result.animals if a["name"]}
    assert set(by) == {"しゅう", "まめ", "みかん", "まる"}
    mame, mikan = by["まめ"], by["みかん"]
    assert (mame["species"], mame["sex"], mame["color"]) == ("cat", "メス", "黒")
    assert (mikan["species"], mikan["sex"], mikan["color"]) == ("cat", "オス", "茶白")
    for a in (mame, mikan):
        assert a["kind"] == "adoption" and a["note"] == "令和8年11月16日掲載"
    assert mame["image_url"] and mame["image_url"] == mikan["image_url"]   # 2 頭が同じ写真（滝川HC猫2頭サムネ）
    assert mame["id"] != mikan["id"]
    assert len({a["id"] for a in c.result.animals}) == 6


def test_iwamizawa_label_with_deng_is_read():
    # 岩見沢の「種類等：猫、雑種、白茶」「性別：メス、不妊済」（11/20 掲載）。犬猫が決まらず種別なしで載っていた
    c = _run(LIVE)
    a = next(a for a in c.result.animals if a["note"] == "令和8年11月20日掲載" and a["age"] == "16歳")
    assert a["species"] == "cat" and a["breed"] == "雑種" and a["sex"].startswith("メス")


def test_bullet_ids_do_not_depend_on_order_or_photo():
    # 1 頭目が譲渡されて消えても、残った子の ID は変わらない
    full = {a["name"]: a["id"] for a in _run(LIVE).result.animals}
    one = _run(LIVE, lambda h: re.sub(r"・まめ.*?(?=・みかん)", "", h, flags=re.S))
    assert one.status == "ok", one.error
    got = {a["name"]: a["id"] for a in one.result.animals}
    assert "まめ" not in got and got["みかん"] == full["みかん"]


def test_fukakawa_sex_label_with_extra_char_is_read():
    # 深川の「性別等：オス、茶白」（ラベルが「性別」でなく「性別等」）
    c = _run(LIVE)
    maru = next(a for a in c.result.animals if a["name"] == "まる")
    assert maru["species"] == "cat" and maru["sex"].startswith("オス") and maru["note"] == "令和8年11月20日掲載"


def test_adopted_hospital_cat_is_still_skipped():
    # 協力動物病院の猫（「治療等についてご協力頂ける方に引取となりました」）は載せない。11/07 の実ページは従来どおり 3 頭
    c = _run(OLD)
    assert c.status == "ok", c.error
    assert [a["species"] for a in c.result.animals] == ["cat", "cat", "dog"]
    assert [a["name"] for a in c.result.animals][:2] == ["しゅう", "りょう"]


def test_zero_still_needs_all_five_sections():
    def none_all(h: str) -> str:
        return h   # 子のいる日は 0 頭にならない（読めた子がいる）

    assert _run(LIVE, none_all).status == "ok"
