"""レシピ実行エンジンのテスト（ネットワークなし・徳島の実ページを保存したフィクスチャ）。"""

from pathlib import Path

import yaml

from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Executor, Recipe, field_value, Row, parse_sel
from collector.registry import Source, load_sources
from bs4 import BeautifulSoup

FIX = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).resolve().parent.parent

ENTRY = "https://douai-tokushima.com/transfer/doglist"
LIST1 = "https://douai-tokushima.com/animalinfo/list4_1"
LIST2 = "https://douai-tokushima.com/animalinfo/list4_1/index.cgi?Start=10"


def _source() -> Source:
    return Source(slug="douai_tokushima-2", name="徳島県（譲渡犬）", municipality="徳島県", prefecture="徳島県",
                  url=ENTRY, kind="adoption", species="dog", recipe="recipes/douai_tokushima-2.yaml")


def _fetcher() -> FakeFetcher:
    lst = (FIX / "tokushima_list4_1.html").read_text(encoding="utf-8")
    return FakeFetcher({
        ENTRY: (FIX / "tokushima_doglist.html").read_text(encoding="utf-8"),
        LIST1: lst,
        # 2 ページ目: 別の 10 頭（写真名を変える）、「次へ」は無い
        LIST2: lst.replace('href="index.cgi?Start=10"', 'href=""').replace("photo2-", "photo2-p2-"),
    }, redirects={LIST1: LIST1 + "/"})   # 実サイトは末尾 / にリダイレクトし、相対 URL はそこ基準


def test_tokushima_follow_paginate_rows():
    recipe = Recipe.load(ROOT / "recipes/douai_tokushima-2.yaml")
    recipe.encoding = None   # フィクスチャは UTF-8
    ex = Executor(_fetcher(), recipe)
    docs = ex.resolve(ENTRY)
    assert [d.url for d in docs] == [LIST1 + "/", LIST2]
    res = build(_source(), recipe, docs)
    assert res.rows == 20
    assert len(res.animals) == 20 and not res.dropped
    a = res.animals[0]
    assert a["species"] == "dog" and a["kind"] == "adoption"
    assert a["image_url"].startswith("https://douai-tokushima.com/animalinfo/list4_1/photo/")
    assert a["sex"] in ("メス(避妊手術済)", "オス(去勢手術済)")
    assert a["id"] and len(a["id"]) == 12
    assert len({x["id"] for x in res.animals}) == 20   # 同じページを 2 回読んでも ID は写真 URL で決まる → 実運用では重複しない


def test_id_is_stable_across_runs():
    recipe = Recipe.load(ROOT / "recipes/douai_tokushima-2.yaml")
    recipe.encoding = None
    ids1 = [a["id"] for a in build(_source(), recipe, Executor(_fetcher(), recipe).resolve(ENTRY)).animals]
    ids2 = [a["id"] for a in build(_source(), recipe, Executor(_fetcher(), recipe).resolve(ENTRY)).animals]
    assert ids1 == ids2


def test_row_without_photo_or_key_is_dropped():
    html = """<ul class="news">
      <li><table><tr><td class="photo"><img src="p1.jpg"></td><td aria-label="性別">メス</td></tr></table></li>
      <li><table><tr><th>見出し</th><td>案内文です</td></tr></table></li>
      <li><table><tr><td aria-label="管理番号">26-0123</td><td aria-label="性別">オス</td></tr></table></li>
    </ul>"""
    recipe = Recipe(rows="ul.news > li", fields={"sex": {"label": "性別"}, "management_no": {"label": "管理番号"}})
    ex = Executor(FakeFetcher({"https://x.test/": html}), recipe)
    res = build(_source(), recipe, ex.resolve("https://x.test/"))
    assert len(res.animals) == 2
    assert [d.reason for d in res.dropped] == ["写真も管理番号も収容日も無い"]
    assert res.animals[1]["management_no"] == "26-0123" and res.animals[1]["image_url"] is None


def test_empty_text_confirms_zero():
    recipe = Recipe(rows="table tr", empty_text=["現在いません"])
    ex = Executor(FakeFetcher({"https://x.test/": "<p>現在いません</p>"}), recipe)
    res = build(_source(), recipe, ex.resolve("https://x.test/"))
    assert not res.animals and res.empty_confirmed


def test_label_value_variants():
    html = """<div>
      <table><tr><th>性別</th><td>メス</td></tr>
             <tr><th>年齢</th><th>体重</th></tr><tr><td>3歳</td><td>5kg</td></tr></table>
      <p>毛色：白</p></div>"""
    row = Row(doc=None, el=BeautifulSoup(html, "lxml").div)
    assert field_value({"label": "性別"}, row) == "メス"
    assert field_value({"label": "年齢"}, row) == "3歳"
    assert field_value({"label": "体重"}, row) == "5kg"
    assert field_value({"label": "毛色"}, row) == "白"
    assert field_value({"regex": r"(\d)kg"}, row) == "5"


def test_species_from_heading():
    html = "<h3>保護犬情報</h3><table class=a><tr><td><img src=d.jpg></td></tr></table><h3>保護猫情報</h3><table class=a><tr><td><img src=c.jpg></td></tr></table>"
    recipe = Recipe(rows="table.a", species={"from": "heading", "selector": "h3"})
    src = _source()
    src.species = "mixed"
    res = build(src, recipe, Executor(FakeFetcher({"https://x.test/": html}), recipe).resolve("https://x.test/"))
    assert [a["species"] for a in res.animals] == ["dog", "cat"]


def test_parse_sel():
    assert parse_sel("a.x@href") == ("a.x", "href")
    assert parse_sel("iframe#f@src") == ("iframe#f", "src")
    assert parse_sel("a.detail") == ("a.detail", "href")


def test_registry_loads_and_recipes_parse():
    sources = load_sources()
    assert len(sources) >= 200
    for s in sources:
        if s.recipe_path.exists():
            Recipe.load(s.recipe_path)


def test_empty_text_matches_entry_page_when_no_pdf():
    """PDF リンクが 0 本の日でも、入口ページの「現在いません」で empty と判定できる。"""
    recipe = Recipe(steps=[{"pdf_links": "a[href$='.pdf']"}], pdf={"mode": "text"}, rows_regex=r"^No.*$",
                    empty_text=["現在、収容動物情報はありません"])
    ex = Executor(FakeFetcher({"https://x.test/": "<p>現在、収容動物情報はありません。</p>"}), recipe)
    docs = ex.resolve("https://x.test/")
    assert docs == []
    res = build(_source(), recipe, docs, ex.visited)
    assert not res.animals and res.empty_confirmed


def test_recipe_url_overrides_registry_url():
    recipe = Recipe(url="https://x.test/real", rows="li", empty_text=["なし"])
    ex = Executor(FakeFetcher({"https://x.test/real": "<ul><li><img src=a.jpg></li></ul>"}), recipe)
    docs = ex.resolve("https://x.test/registry-url")
    assert docs[0].url == "https://x.test/real"
    assert len(build(_source(), recipe, docs, ex.visited).animals) == 1
