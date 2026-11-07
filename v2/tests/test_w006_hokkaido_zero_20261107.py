"""W006 北海道の 0 頭だけ読むレシピ（PR #104 公開ゲート・2026-11-07・ネットワークなし）。

link_only にしていた 0 頭のページを、「0 頭の文（見出し付き）が全部そろった日だけ 0 頭、それ以外は failed」で読む。
子が載った日の作りは多くが未確認なので rows は今のページに無い物を指す（子が載ると failed で通知される）。
fixture は 2026-11-07 に保存した実ページ（Wayback で子のいた版が見つかったページはその版も fixture）。

- 0 頭の日の保存ページ → status empty（animals 0）
- 0 頭の文を 1 つ（節ごと・行ごと）ずつ「子がいる」文に変えると、どれも empty にならない（1 つの節の文を全体の 0 頭にしない）
- 子のいた日の Wayback 版は empty にならない
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup, NavigableString
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

# slug -> 「子がいる」に書き換える（文言, 置き換え）。書き換えた日は、どれも 0 頭にならず failed になる
MUTATIONS: dict[str, list[tuple[str, str]]] = {
    "sorachi-4": [("現在、飼い主さんは募集しておりません", "飼い主さんを募集しています")],
    "shiribeshi-2": [("現在、保護している犬・猫はいません", "現在、猫が1匹います")],
    "iburi-3": [("【犬０匹、猫０匹】", "【犬０匹、猫１匹】")],
    "hidaka-1": [("はおりません", "がおります")],
    "hidaka-2": [("【犬0匹、猫0匹】", "【犬0匹、猫1匹】")],
    "tokachi-2": [("はいません", "がいます")],
    "kushiro-2": [("犬0頭、猫0頭", "犬0頭、猫1頭"), ("犬（0頭）", "犬（1頭）"), ("今はいません", "1頭います")],
    "nemuro-2": [("はいません", "がいます")],
    "oshima-2": [("いません", "います")],
    "oshima-3": [("いません", "います")],
    "hiyama-1": [("犬0頭、猫0頭", "犬0頭、猫1頭")],
    "kamikawa-3": [("犬：計０頭", "犬：計１頭"), ("猫：計０頭", "猫：計１頭")],
    "kamikawa-4": [("今はいません", "1匹います")],
    "souya-1": [("$：0", "：1")],
    "okhotsk-1": [("なし", "あり")],
    "okhotsk-2": [("=0", "1")],
    "okhotsk-3": [("犬０頭", "犬１頭"), ("猫０匹", "猫１匹"), ("現在、迷子の犬猫はいません", "迷子の犬猫がいます")],
    "rumoi-1": [("0匹", "1匹"), ("０匹", "１匹"), ("0 匹", "1 匹"), ("０ 匹", "１ 匹")],
}
# 同じ文が別の節に並び、1 つの節だけ子がいる日を 1 ノードずつ試すページ
EACH = {"hidaka-1", "hiyama-1", "souya-1", "rumoi-1", "okhotsk-2", "kamikawa-4"}
ZERO = sorted(MUTATIONS)
ZERO_ALL = ZERO + ["souya-2"]


def _fx(slug: str) -> str:
    return (FIX / f"w006_hokkaido_zero_{slug}_20261107.html").read_text(encoding="utf-8")


def _run(slug: str, html: str):
    s = SOURCES[f"hokkaido_{slug}"]
    return collect_one(s, FakeFetcher({s.url: html}))


def _is_zero(c) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def _nodes(soup, phrase: str):
    """本文の文字ノードのうち phrase を含むもの（"=x" は全体が x、"$x" は x で終わるもの）。"""
    kind, key = (phrase[0], phrase[1:]) if phrase[0] in "=$" else ("", phrase)

    def hit(t: NavigableString) -> bool:
        if t.parent.name in ("script", "style"):
            return False
        s = str(t).strip()
        return s == key if kind == "=" else s.endswith(key) if kind == "$" else key in s

    return [t for t in soup.body.find_all(string=True) if hit(t)], key, kind


def _mutations(html: str, phrase: str, repl: str, each: bool):
    """phrase を含む本文ノードを書き換えた HTML を返す。each なら 1 ノードずつ（同じ文が別の節に並ぶページ）、そうでなければ全部いっぺんに
    （タイトルやパンくずにも同じ文字が出るので、1 つだけ直しても本文の文が残る）。"""
    n = len(_nodes(BeautifulSoup(html, "lxml"), phrase)[0])
    for i in range(n if each else 1):
        soup = BeautifulSoup(html, "lxml")
        nodes, key, kind = _nodes(soup, phrase)
        for t in nodes[i:i + 1] if each else nodes:
            t.replace_with(NavigableString(repl if kind == "=" else str(t).replace(key, repl)))
        yield str(soup)


def test_registry_is_recipe_for_every_zero_slug():
    for slug in ZERO_ALL:
        s = SOURCES[f"hokkaido_{slug}"]
        assert s.mode == "recipe", slug
        assert s.photo == "pending"


@pytest.mark.parametrize("slug", ZERO_ALL)
def test_zero_day_is_empty(slug):
    assert _is_zero(_run(slug, _fx(slug))), slug


@pytest.mark.parametrize("slug", ZERO)
def test_any_one_section_with_animals_is_not_zero(slug):
    total = 0
    for phrase, repl in MUTATIONS[slug]:
        for html in _mutations(_fx(slug), phrase, repl, slug in EACH):
            total += 1
            c = _run(slug, html)
            assert not _is_zero(c), (slug, phrase)
            assert c.status == "failed", (slug, phrase, c.status)
    assert total >= 1, slug


def test_souya_injury_table_filled_row_is_not_zero():
    # 負傷動物の表: 0 頭の日は見出しの下が全部空欄。1 つでも埋まれば 0 頭にしない（failed で通知）
    h = _fx("souya-2")
    assert _is_zero(_run("souya-2", h))
    soup = BeautifulSoup(h, "lxml")
    td = soup.select("table tr")[1].select("td")[1]
    td.string = "猫"
    c = _run("souya-2", str(soup))
    assert not _is_zero(c) and c.status == "failed"


def test_missing_section_sentence_is_not_zero():
    # 文を消した（作りが変わった）日は 0 頭にしない
    h = _fx("hidaka-1")
    assert "現在、新しい飼い主を募集している犬・猫はおりません。" in h
    c = _run("hidaka-1", h.replace("現在、新しい飼い主を募集している犬・猫はおりません。", ""))
    assert c.status == "failed"
