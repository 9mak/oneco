"""T656 直し 1 回目・項目 5（2026-11-20・ネットワークなし）: 上川 新しい飼い主募集のページ（hokkaido_kamikawa-2）を link_only から recipe にする。

11/07 は保健所ごとの件数の表だけだったが、11/20 には「現在、新しい飼い主探しを実施している子達は、次のとおりです！」の表に猫 3 頭が載っていた。
保存ページ: 11/20 の実ページ・Wayback 2025-11-07 と 2026-02-08（表が空欄の行だけの 0 頭の日）・2026-02-06（期限 1/30 を過ぎた子が残る日）・2026-07-22（犬 2 頭）。
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
S = replace(SOURCES["hokkaido_kamikawa-2"], mode="recipe")  # 台帳は #147 で link_only。レシピは許諾が変わったときのため読み続ける
LIVE = "w006_hokkaido_kamikawa-2_20261120.html"
ZERO = ["w006_hokkaido_kamikawa-2_zero_wb20251107.html", "w006_hokkaido_kamikawa-2_zero_wb20260208.html"]
EXPIRED = "w006_hokkaido_kamikawa-2_expired_wb20260206.html"
DOGS = "w006_hokkaido_kamikawa-2_dogs_wb20260722.html"


def _run(fixture: str, mutate=None) -> Collected:
    html = (FIX / fixture).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    return collect_one(S, FakeFetcher({S.url: html}))


def test_registry_is_link_only_with_recipe_kept():
    # #147（北海道の返事）で link_only・photo no。レシピは許諾が変わったときのために残す
    r = SOURCES["hokkaido_kamikawa-2"]
    assert r.mode == "link_only" and r.recipe == "recipes/hokkaido_kamikawa-2.yaml" and r.recipe_path.exists()
    assert r.photo == "no" and r.kind == "adoption" and r.enabled


def test_three_cats_in_the_table():
    c = _run(LIVE)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 3
    for a in c.result.animals:
        assert a["kind"] == "adoption" and a["species"] == "cat" and a["sex"] == "オス" and a["image_url"]
    assert [a["age"] for a in c.result.animals] == ["成猫", "成猫", "2ヶ月程度"]
    assert [a["color"] for a in c.result.animals] == ["茶", "黒", "黒"]
    assert [a["location"] for a in c.result.animals] == ["上川保健所", "環境生活課", "環境生活課"]
    assert len({a["id"] for a in c.result.animals}) == 3
    assert "人が大好き" in c.result.animals[0]["note"]


def test_expired_rows_stay_on_the_page_and_are_read():
    # 保管期限（11/10・11/13）は 11/20 の時点で過ぎているが、ページから消えていない。期限で外さず note に出す
    c = _run(LIVE)
    assert [a["note"].rsplit("保管期限 ", 1)[1] for a in c.result.animals] == ["11月10日", "11月13日", "11月13日"]
    # 2026-02-06 の保存ページも、期限 1/30 を過ぎたあとに 3 頭が残っていた
    old = _run(EXPIRED)
    assert old.status == "ok" and len(old.result.animals) == 3
    assert all(a["note"].endswith("保管期限 1月30日") for a in old.result.animals)
    # 種別の列が犬猫でない版（種別が「雑種」）は決めない
    assert all(a["species"] is None for a in old.result.animals)


def test_dogs_with_breed_in_the_species_column():
    c = _run(DOGS)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 2
    assert [a["species"] for a in c.result.animals] == [None, "dog"]   # 「雑種」は決めない・「柴犬 (推定)」は犬
    assert all(a["location"] == "富良野保健所" for a in c.result.animals)


def test_zero_days_are_zero_on_the_table_not_on_the_sentences():
    for fx in ZERO:
        c = _run(fx)
        assert c.status == "empty", (fx, c.error)
        assert c.result.empty_evidence == "empty_absent"


def test_sentences_that_disagree_with_the_table_do_not_make_zero():
    # 11/20 は文が「猫はいません」「犬は 2 匹」で表は猫 3 頭。表の子を消したら 0 頭、文だけでは 0 頭にしない
    def no_children(h: str) -> str:
        return re.sub(r"<tr>\s*<td>[１２３]</td>.*?</tr>", "<tr>" + "<td>&nbsp;</td>" * 9 + "</tr>", h, flags=re.S)

    assert _run(LIVE, no_children).status == "empty"
    # 文を「いません」に直しても、表に子がいれば 0 頭にならない
    c = _run(LIVE, lambda h: h.replace("犬は2匹います", "犬はいません"))
    assert c.status == "ok" and len(c.result.animals) == 3


def test_structure_change_is_failed_not_zero():
    # 表の見出し（caption）が変わった日は、枠が無いので 0 頭にしない
    c = _run(ZERO[1], lambda h: h.replace("新しい飼い主探しの詳細", "飼い主探し"))
    assert c.status not in {"ok", "empty"}
