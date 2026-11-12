"""W006 2026-11-13 0:05 の収集で読めなかった掲載元を直す（ネットワークなし）。

fixture は 2026-11-13 に取得した実ページ（script・style を落とした。熊本の一覧だけは転送の script を残した）。
- 0 頭の新しい文言: 札幌 迷子猫（city_sapporo-2）・神奈川 病院収容の猫（pref_kanagawa-2・PDF）・幸手（pref_saitama_satte）
- 初めて子が載った: 宇都宮（city_utsunomiya。h2 の後ろに 1 項目 1 段落の p）・日高（hokkaido_hidaka-1。募集チラシの画像）・
  釧路 迷子（hokkaido_kushiro-2。日高・釧路は本番の AI 修復の案を元にした）
- 熊本市 迷子猫（city_kumamoto-2）: 記事が 1 件の日は一覧を出さず、script の location.href で記事へ飛ばす。
  follow_all に script_url（インラインの script から URL を拾う正規表現）を足した
- 福岡市の暫定ページ（city_fukuoka_interim-1・-2）: 2026-11-12 から li の入れ子が表と h3 の管理番号に変わった
- 群馬 保護犬（pref_gunma-1）: 一覧に残る 26-134 の個別ページだけ 404
- 岡山県（pref_okayama）: www.pref.okayama.jp → www.pref.okayama.lg.jp
"""

import dataclasses
import json
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from collector.extract import Result, build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Executor, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import Source, load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Result:
    src = SOURCES[slug]
    recipe = Recipe.load(ROOT / src.recipe)
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _collect(slug: str, pages: dict[str, str | bytes], redirects: dict[str, str] | None = None,
             status: dict[str, int] | None = None) -> Collected:
    return collect_one(dataclasses.replace(SOURCES[slug], enabled=True), FakeFetcher(pages, redirects=redirects, status=status))


def _res(c: Collected) -> Result:
    assert c.result is not None, c.error
    return c.result


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def _swap(html: str, old: str, new: str) -> str:
    assert old in html, old
    return html.replace(old, new)


# --- 0 頭の新しい文言 -----------------------------------------------------------------------------------------------
def test_sapporo_cat_new_zero_wording_with_blank_template_tables_is_a_zero_day():
    res = _run("city_sapporo-2", _fx("w006_city_sapporo-2_zero_20261113.html"))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text"


def test_sapporo_cat_child_day_does_not_contain_the_new_zero_wording():
    html = _fx("w006_city_sapporo-2_20261107.html")
    assert "現在迷子の猫は収容されていません" not in html
    assert _run("city_sapporo-2", html).animals


def test_kanagawa_hospital_cat_pdf_new_zero_wording_is_a_zero_day():
    pdf = json.loads(_fx("w006_pref_kanagawa-2_zero_20261113.json"))
    assert "現在、疾病等により収容期間中の猫はいません" in pdf["pdf_text"]
    src = SOURCES["pref_kanagawa-2"]
    res = build(src, Recipe.load(ROOT / src.recipe), [Doc(url=pdf["url"], pdf_text=pdf["pdf_text"], pdf_tables=pdf["pdf_tables"])])
    assert res.animals == [] and res.empty_confirmed


def test_satte_new_zero_wording_with_blank_template_is_a_zero_day():
    res = _run("pref_saitama_satte", _fx("w006_pref_saitama_satte_zero_20261113.html"))
    assert res.animals == [] and res.empty_confirmed


def test_satte_child_day_does_not_contain_the_new_zero_wording():
    html = _fx("t519_saitama_satte.html")
    assert "現在、収容はありません" not in html


# --- 宇都宮: 初めて子が載った日 ------------------------------------------------------------------------------------------
def test_utsunomiya_reads_the_dog_and_the_cat_from_flat_paragraphs():
    res = _run("city_utsunomiya", _fx("w006_city_utsunomiya_20261113.html"))
    got = [_pick(a, "species", "shelter_date", "location", "breed", "color", "sex", "size", "note") for a in res.animals]
    assert got == [
        {"species": "dog", "shelter_date": "令和8年度11月11日", "location": "清原台2丁目", "breed": "ロングコートチワワ",
         "color": "ブラックタン", "sex": "オス", "size": "小", "note": None},
        {"species": "cat", "shelter_date": "令和8年11月6日", "location": "上籠谷町", "breed": "雑種",
         "color": "黒", "sex": "メス", "size": "子猫", "note": None},
    ]
    assert res.animals[0]["image_url"].endswith("/001/005/584/chiwawa.jpeg")
    assert res.animals[1]["image_url"].endswith("/001/005/584/20261106.jpeg")


def test_utsunomiya_other_headings_on_the_page_are_not_animals():
    # 「栃木県動物愛護指導センター」「栃木県警察」等の h2 は掲載期限が無いので行にならない
    res = _run("city_utsunomiya", _fx("w006_city_utsunomiya_20261113.html"))
    assert len(res.animals) == 2
    assert not any("栃木県警察" in d.text for d in res.dropped)


def test_utsunomiya_collar_is_kept_as_note_when_it_is_not_none():
    html = _swap(_fx("w006_city_utsunomiya_20261113.html"), "<p>装着物　　　なし　　　&nbsp; &nbsp;</p>", "<p>装着物　　　赤い首輪</p>")
    assert _run("city_utsunomiya", html).animals[0]["note"] == "赤い首輪"


# --- 北海道 日高・釧路: 初めて子が載った日 ----------------------------------------------------------------------------------
def test_hidaka_reads_one_dog_per_flyer_image():
    res = _run("hokkaido_hidaka-1", _fx("w006_hokkaido_hidaka-1_20261113.html"))
    assert [_pick(a, "species", "location") for a in res.animals] == [{"species": "dog", "location": "静内保健所"}] * 2
    assert [a["image_url"].rsplit("/", 1)[1] for a in res.animals] == ["R8%E7%8A%AC6PPB3b_thumb.png", "R8%E7%8A%AC7P2_thumb.png"]
    assert all(a.get("management_no") is None for a in res.animals)   # alt はファイル名なので管理番号にしない


def test_hidaka_zero_day_is_still_a_zero_day():
    res = _run("hokkaido_hidaka-1", _fx("w006_hokkaido_zero_hidaka-1_20261107.html"))
    assert res.animals == [] and res.empty_confirmed


def test_kushiro_reads_the_dog_and_skips_the_blank_templates():
    res = _run("hokkaido_kushiro-2", _fx("w006_hokkaido_kushiro-2_20261113.html"))
    (a,) = res.animals
    assert _pick(a, "species", "management_no", "breed", "size", "age", "color", "sex", "location", "shelter_date", "note") == {
        "species": "dog", "management_no": "SD11-1", "breed": "雑種", "size": "中型", "age": "推定1~5歳", "color": "白", "sex": "メス",
        "location": "標茶町字中茶安別原野", "shelter_date": "令和8年(2026年)11月10日", "note": "人慣れしていない"}
    assert a["image_url"].endswith("/SD11-1.jpeg")


def test_kushiro_zero_day_needs_all_three_headings():
    res = _run("hokkaido_kushiro-2", _fx("w006_hokkaido_zero_kushiro-2_20261107.html"))
    assert res.animals == [] and res.empty_confirmed
    # 見出しの 1 つ（猫の節）が変わった日は 0 頭にしない（AI 修復の案は「犬0頭、猫0頭」だけでも 0 頭にしていた）
    broken = _swap(_fx("w006_hokkaido_zero_kushiro-2_20261107.html"), "猫(今はいません）", "猫（1頭）")
    assert not _run("hokkaido_kushiro-2", broken).empty_confirmed


# --- 熊本市 迷子猫: 記事が 1 件の日の JS 転送 -------------------------------------------------------------------------------
KUMA_LIST = SOURCES["city_kumamoto-2"].url
KUMA_DETAIL = "https://www.city.kumamoto.jp/dynamic/doubutuaigo/hpkiji/pub/detail.aspx?c_id=3&id=73813&class_set_id=23&class_id=3615"
KUMA_KIJI = "https://www.city.kumamoto.jp/doubutuaigo/kiji00373813/index.html"


def test_kumamoto_cat_single_article_day_follows_the_script_redirect():
    pages = {KUMA_LIST: _fx("w006_city_kumamoto-2_list_redirect_20261113.html"), KUMA_DETAIL: _fx("w006_city_kumamoto-2_kiji00373813_20261113.html")}
    c = _collect("city_kumamoto-2", pages, redirects={KUMA_DETAIL: KUMA_KIJI})
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "sex", "age", "color", "shelter_date", "location") == {
        "species": "cat", "sex": "オス", "age": "1~2歳", "color": "白 三毛色", "shelter_date": "2026年11月7日", "location": "熊本市北区津浦町5番地"}


def test_kumamoto_cat_redirect_page_without_the_target_is_not_zero():
    # 転送先が取れない日は 0 頭にしない（従来どおり failed）
    c = _collect("city_kumamoto-2", {KUMA_LIST: _fx("w006_city_kumamoto-2_list_redirect_20261113.html")}, status={KUMA_DETAIL: 500})
    assert c.status == "failed"


def test_kumamoto_cat_zero_day_and_list_day_are_unchanged():
    assert _run("city_kumamoto-2", _fx("w006_city_kumamoto-2_zero_20261031.html")).empty_confirmed
    for slug in ("city_kumamoto-1", "city_kumamoto-2"):
        step = yaml.safe_load((ROOT / SOURCES[slug].recipe).read_text(encoding="utf-8"))["steps"][0]
        assert "detail\\.aspx" in step["script_url"], slug


# --- follow_all.script_url（エンジン） --------------------------------------------------------------------------------------
def _src() -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="熊本県", url="https://x.jp/list.html", kind="stray", species="cat")


LIST_WITH_REDIRECT = """<html><head><script type="text/javascript">
//<![CDATA[
location.href='https://x.jp/detail.aspx?id=1&c=2';//]]>
</script><script src="https://x.jp/common/js/detail.aspx?id=999"></script></head><body><div id="list"></div></body></html>"""
LIST_WITH_LINKS = """<html><body><div id="list"><a href="/kiji1.html">1</a><a href="/kiji2.html">2</a></div>
<script>location.href='https://x.jp/detail.aspx?id=1&c=2';</script></body></html>"""


def _exec(step: dict, pages: dict[str, str], redirects: dict[str, str] | None = None) -> tuple[Executor, list[Doc]]:
    recipe = Recipe.from_dict({"steps": [step], "rows": "body"})
    ex = Executor(FakeFetcher(pages, redirects=redirects), recipe)
    return ex, ex.resolve(_src().url)


def test_script_url_picks_the_url_from_an_inline_script_only():
    step = {"follow_all": "div#list a@href", "script_url": r"location\.href='([^']*detail\.aspx\?[^']*)'"}
    ex, docs = _exec(step, {_src().url: LIST_WITH_REDIRECT, "https://x.jp/detail.aspx?id=1&c=2": "<body>猫</body>"})
    assert [d.url for d in docs] == ["https://x.jp/detail.aspx?id=1&c=2"]          # script src の URL は拾わない
    assert any("follow_all → 1 件" in t for t in ex.trace)


def test_script_url_adds_to_the_links_and_does_not_duplicate():
    step = {"follow_all": "div#list a@href", "script_url": r"location\.href='([^']*)'"}
    pages = {_src().url: LIST_WITH_LINKS, "https://x.jp/kiji1.html": "<body>1</body>", "https://x.jp/kiji2.html": "<body>2</body>",
             "https://x.jp/detail.aspx?id=1&c=2": "<body>3</body>"}
    _, docs = _exec(step, pages)
    assert [d.url for d in docs] == ["https://x.jp/kiji1.html", "https://x.jp/kiji2.html", "https://x.jp/detail.aspx?id=1&c=2"]


def test_without_script_url_the_redirect_script_is_ignored():
    _, docs = _exec({"follow_all": "div#list a@href"}, {_src().url: LIST_WITH_REDIRECT})
    assert docs == []


def test_script_url_must_be_a_safe_regex_on_the_same_host():
    base = {"rows": "body", "steps": [{"follow_all": "a@href", "script_url": r"location\.href='([^']*)'"}]}
    assert validate_recipe_dict(base, "https://x.jp/list.html") == []
    bad = {"rows": "body", "steps": [{"follow_all": "a@href", "script_url": "(a+)+"}]}
    assert validate_recipe_dict(bad, "https://x.jp/list.html")
    alone = {"rows": "body", "steps": [{"follow": "a@href", "script_url": r"location\.href='([^']*)'"}]}
    assert validate_recipe_dict(alone, "https://x.jp/list.html")    # follow_all 以外に付けたら誤り


def test_script_url_to_another_host_is_not_followed():
    step = {"follow_all": "div#list a@href", "script_url": r"location\.href='([^']*)'"}
    html = LIST_WITH_REDIRECT.replace("https://x.jp/detail.aspx", "https://evil.example/detail.aspx")
    _, docs = _exec(step, {_src().url: html})
    assert docs == []


# --- 福岡市の暫定ページ（2026-11-12 からの作り） -------------------------------------------------------------------------------
FUKUOKA_DOG = SOURCES["city_fukuoka_interim-1"].url
FUKUOKA_CAT = SOURCES["city_fukuoka_interim-2"].url
DOG = "w006_city_fukuoka_doghoused_20261113.html"    # 犬 d1878（状況 返還済）の 1 件だけ
CAT = "w006_city_fukuoka_cathoused_20261113.html"    # 猫 ｃ４９３８（死亡）と ｃ4939（収容中）


def _dog(html: str) -> Collected:
    return _collect("city_fukuoka_interim-1", {FUKUOKA_DOG: html})


def _cat(html: str) -> Collected:
    return _collect("city_fukuoka_interim-2", {FUKUOKA_CAT: html})


def test_fukuoka_real_dog_page_is_zero_because_the_one_dog_was_returned():
    c = _dog(_fx(DOG))
    assert c.status == "empty", c.error
    assert _res(c).empty_evidence == "all_excluded+container"
    assert [d.reason for d in _res(c).dropped] == ["除外語（status: 返還）"]


def test_fukuoka_real_cat_page_lists_the_cat_in_the_shelter_and_not_the_dead_one():
    c = _cat(_fx(CAT))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "management_no", "breed", "color", "sex", "age", "size", "shelter_date", "location", "note", "image_url") == {
        "species": "cat", "management_no": "c4939", "breed": "雑種", "color": "サビ", "sex": "メス", "age": "10歳以上", "size": "中",
        "shelter_date": "令和8年11月9日", "location": "早)賀茂3", "note": "ピンクのノミ取り首輪装着",
        "image_url": "https://www.city.fukuoka.lg.jp/hofuku/dobutsukanri/life/images/PB090002.JPG"}
    assert [d.reason for d in _res(c).dropped] == ["除外語（status: 死亡）"]


def test_fukuoka_cat_without_a_photo_is_listed_by_its_number_when_its_status_is_blank():
    # ｃ４９３８（死亡・「写真の掲載はありません」）の状況だけ空にした合成。管理番号（全角）があれば写真が無くても載る
    c = _cat(_swap(_fx(CAT), "<td>死亡（11月5日）</td>", "<td></td>"))
    assert c.status == "ok", c.error
    first = _res(c).animals[0]
    assert _pick(first, "management_no", "breed", "color", "image_url") == {"management_no": "c4938", "breed": "雑種", "color": "白", "image_url": None}
    assert [a["management_no"] for a in _res(c).animals] == ["c4938", "c4939"]


@pytest.mark.parametrize("status", ["", "収容中", "公示中"])
def test_fukuoka_dog_with_the_status_edited_is_listed(status):
    c = _dog(_swap(_fx(DOG), "<td>返還済</td>", f"<td>{status}</td>"))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "management_no", "breed", "color", "sex", "age", "size", "shelter_date", "location") == {
        "species": "dog", "management_no": "d1878", "breed": "雑種", "color": "クリーム", "sex": "去勢オス", "age": "9歳", "size": "中",
        "shelter_date": "令和8年11月11日", "location": "東)香椎駅東3丁目"}


@pytest.mark.parametrize("closed", ["返還済", "譲渡済", "死亡", "譲渡決定"])
def test_fukuoka_dog_never_lists_a_closed_status(closed):
    c = _dog(_swap(_fx(DOG), "<td>返還済</td>", f"<td>{closed}</td>"))
    assert c.status == "empty" and _res(c).animals == []


def test_fukuoka_dog_with_death_in_the_remarks_is_not_listed():
    html = _swap(_swap(_fx(DOG), "<td>返還済</td>", "<td></td>"), "首輪（赤）、マイクロチップ装着あり", "11/12死亡")
    c = _dog(html)
    assert c.status == "empty" and _res(c).animals == []


def test_fukuoka_status_label_renamed_is_not_read_as_active():
    # 項目名「状況」が変わると返還済・死亡の子を収容中として載せてしまう（fail-open）ので、状況の行が無い子は行にせず failed
    for c in (_dog(_swap(_fx(DOG), "<td>状況</td>", "<td>ステータス</td>")),
              _cat(_fx(CAT).replace("<td>状況</td>", "<td>ステータス</td>"))):
        assert c.status == "failed" and _res(c).animals == []


def test_fukuoka_changed_structure_is_not_zero():
    dog = _fx(DOG)
    for broken in (_swap(dog, "<h3>d1878", "<p>d1878"),                     # 管理番号の見出しが無くなった
                   _swap(dog, '<div class="wb-contents">', "<div>")):        # 本文の器が変わった
        c = _dog(broken)
        assert c.status == "failed" and _res(c).animals == []


def test_fukuoka_zero_sentence_day_is_still_zero():
    c = _dog(_fx("w006_city_fukuoka_doghoused_zero_20261106.html"))
    assert c.status == "empty" and _res(c).empty_evidence == "empty_absent"


# --- 群馬 保護犬: 個別ページだけ消えた子 ---------------------------------------------------------------------------------------
GUNMA = SOURCES["pref_gunma-1"].url


def test_gunma_dog_list_with_only_the_deleted_page_is_a_zero_day():
    html = _fx("w006_pref_gunma-1_list_20261113.html")
    assert "/page/782041.html" in html and "現在、保管期間中の動物はおりません" in html
    c = _collect("pref_gunma-1", {GUNMA: html}, status={"https://www.pref.gunma.jp/page/782041.html": 404})
    assert c.status == "empty", c.error


def test_gunma_dog_other_links_are_still_followed():
    html = _swap(_fx("w006_pref_gunma-1_list_20261113.html"), "/page/782041.html", "/page/790000.html")
    c = _collect("pref_gunma-1", {GUNMA: html}, status={"https://www.pref.gunma.jp/page/790000.html": 404})
    assert c.status == "failed"          # 新しいリンクは辿る（ここでは 404 にしたので全部失敗＝failed）


# --- 岡山県: ドメインの移転 ------------------------------------------------------------------------------------------------
def test_okayama_uses_the_new_domain():
    s = SOURCES["pref_okayama"]
    assert s.url == "https://www.pref.okayama.lg.jp/page/859555.html"
    assert s.verified_phone_url == s.url
