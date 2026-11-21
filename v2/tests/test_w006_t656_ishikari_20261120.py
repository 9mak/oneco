"""T656 直し 1 回目・項目 3（2026-11-20・ネットワークなし）: 石狩 江別保健所の飼い主募集（hokkaido_ishikari-2）の「決まりました」。

行末に「新しい飼い主さんが決まりました！」（青い太字）が付いた行は決まった子。11/19 は 振興局3158、11/20 は 石狩58-3 に付き、載っていた。
"""

from dataclasses import replace
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
LIVE = "w006_hokkaido_ishikari-12_20261120.html"
STAMP = '<strong style="color:#0000ff;">新しい飼い主さんが決まりました！</strong>'
NEW = '<strong style="color:#ee0000;">NEW!</strong>'


def _run(mutate=None) -> Collected:
    html = (FIX / LIVE).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    s = replace(SOURCES["hokkaido_ishikari-2"], mode="recipe")  # 台帳は #147 で link_only。レシピは読み続ける
    return collect_one(s, FakeFetcher({s.url: html}))


def _nos(c: Collected) -> list[str | None]:
    return [a["management_no"] for a in c.result.animals]


def test_decided_cat_is_not_listed():
    # 11/20 の実ページ: 石狩58-3 に「決まりました」が付いている。残りの 4 頭だけ載せる
    c = _run()
    assert c.status == "ok", c.error
    assert _nos(c) == ["石狩94-3", "江別8-C14", "石狩94-4", "振興局3158"]
    assert all(a["note"] for a in c.result.animals)


def test_stamp_moves_to_another_row_on_another_day():
    # 11/19 夜は 振興局3158 に付いていた。印が付く行は日ごとに変わるので、行でなく印で決める
    def moved(h: str) -> str:
        assert STAMP in h
        h = h.replace(STAMP, "", 1)                      # 石狩58-3 から外す
        i = h.index("振興局3158")
        return h[:i] + h[i:].replace(NEW, STAMP, 1)       # 振興局3158 に付ける

    c = _run(moved)
    assert c.status == "ok", c.error
    assert _nos(c) == ["石狩94-3", "江別8-C14", "石狩94-4", "石狩58-3"]


def test_all_decided_is_not_zero_but_unread():
    # 決まった子しかいない日は「現在はいません」が出ないので、0 頭と言い切らない（読めなかった扱いで通知）
    def all_decided(h: str) -> str:
        i = h.index("<h4>【新しい飼い主を募集している猫】")
        j = h.index("<table>", i)
        body = h[i:j]
        return h[:i] + body.replace("</p>", STAMP + "</p>") + h[j:]

    c = _run(all_decided)
    assert c.status not in {"ok", "empty"}


def test_zero_day_is_still_zero():
    # 猫の見出しの直後が「現在はいません」の日（犬の節と同じ書き方）は 0 頭のまま
    def none(h: str) -> str:
        i = h.index("<h4>【新しい飼い主を募集している猫】")
        e = h.index("</h4>", i) + 5
        j = h.index("<table>", e)
        return h[:e] + "<p>現在はいません</p>" + h[j:]

    c = _run(none)
    assert c.status == "empty", c.error
    assert c.result.empty_evidence == "empty_text_all"
