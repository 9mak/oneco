"""T519 G1（函館市・小樽市・青森市・八戸市・盛岡市）のレシピを、2026-10-05 の実ページから抜いた HTML に当てる（ネットワークなし）。

- 青森市の譲渡一覧: 「新しい飼い主さんが決まりました」の子は載せない。0 頭の日は猫の節の文言で 0 頭と分かる
- 八戸市の迷子動物: 犬猫以外（カメ）は other、雑種（猫）は猫。写真が無くても保護日で動物として通る
- 盛岡市の譲渡情報: h2 から次の h2 までが 1 頭。末尾の「【FIV感染について】」の節は動物にしない
- 函館市の迷子: 写真置き場の空の div は動物にならず、0 頭の文言で 0 頭と分かる
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent


def _build(slug: str, html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


AOMORI = """<article id="content"><div id="voice"><h1>新しい飼い主さんを募集中の動物たち</h1>
<h2>犬</h2><h3>青森市保健所からの譲渡</h3><p>現在、募集中の動物はいません。</p>
<h3>ワンニャン里親探しポスト</h3><p>現在、募集中の動物はいません。</p>
<h2>猫</h2><h3>青森市保健所からの譲渡</h3>
<div class="img3lows"><ul class="clearfix">
<li class="imglows clear"> <img alt="にんにん写真" src="/_res/p/ninnin-top.png"/>
<p><span class="imgtitle">R8-43「にんにん」</span><br/>🐾新しい飼い主さんが決まりました。<br/>MIX、グレートラ白、オス<br/>令和8年8月生まれ</p>
<ul class="objectlink"><li class="png"><a href="/_res/p/ninnin-sheet.png">詳細情報（にんにん）</a></li></ul></li>
<li class="imglows"> <img alt="ベル写真" src="/_res/p/beru-top.png"/>
<p><span class="imgtitle">R8-47「ベル」</span><br/>MIX、キジトラ白、メス<br/>令和8年8月生まれ</p>
<ul class="objectlink"><li class="png"><a href="/_res/p/beru-sheet.png">詳細情報（ベル）</a></li></ul></li></ul></div>
<h3>ワンニャン里親探しポスト</h3><p>現在、募集中の動物はいません。</p>
<h2>犬猫以外の動物</h2><p>現在、募集中の動物はいません。</p></div></article>"""

AOMORI_EMPTY = AOMORI[: AOMORI.index('<div class="img3lows">')] + "<p>現在、募集中の動物はいません。</p>" + AOMORI[AOMORI.index("<h3>ワンニャン里親探しポスト</h3><p>現在、募集中の動物はいません。</p>\n<h2>犬猫以外"):]


def test_aomori_adoption_skips_decided_cats_and_reads_the_open_one():
    res = _build("city_aomori-1", AOMORI)
    assert [a["name"] for a in res.animals] == ["ベル"]
    a = res.animals[0]
    assert a["species"] == "cat"
    assert a["management_no"] == "R8-47"
    assert (a["breed"], a["color"], a["sex"], a["age"]) == ("MIX", "キジトラ白", "メス", "令和8年8月生まれ")
    assert a["image_url"].endswith("/_res/p/beru-top.png")


def test_aomori_adoption_zero_day_is_confirmed_by_the_cat_section_text():
    res = _build("city_aomori-1", AOMORI_EMPTY)
    assert res.animals == [] and res.empty_confirmed


def _hachinohe_table(no: str, kind: str, color: str, sex: str, place: str, day: str) -> str:
    return f"""<table><caption>捕獲・保護されている犬、ねこ等の情報</caption><tbody>
<tr><td>番号</td><td>{no}</td></tr><tr><td>種類</td><td>{kind}</td></tr><tr><td>毛色</td><td>{color}</td></tr>
<tr><td>体格</td><td>中</td></tr><tr><td>性別</td><td>{sex}</td></tr><tr><td>特徴</td><td> </td></tr>
<tr><td>捕獲・保護した場所</td><td>{place}</td></tr><tr><td>捕獲・保護した日</td><td>{day}</td></tr>
<tr><td>画像</td><td><a href="//x.jp/a.pdf">収容動物画像(PDFファイル:190.1KB)</a></td></tr>
<tr><td>抑留の場所</td><td>八戸市保健所分室</td></tr></tbody></table>"""


def test_hachinohe_stray_reads_cat_and_other_without_photo():
    html = "<article><h2>迷子動物</h2>" + _hachinohe_table("1", "カメ", "こげ茶", "不明", "八戸市大字湊町", "令和8年9月8日") + _hachinohe_table("3", "雑種（猫）", "キジトラ", "オス", "八戸市大字尻内町", "令和8年10月2日") + "<p>注意事項</p></article>"
    res = _build("city_hachinohe-1", html)
    assert [(a["management_no"], a["species"]) for a in res.animals] == [("1", "other"), ("3", "cat")]
    cat = res.animals[1]
    assert cat["sex"] == "オス" and cat["color"] == "キジトラ" and cat["shelter_date"] == "令和8年10月2日"
    assert cat["location"] == "八戸市大字尻内町" and not cat.get("image_url")


def _morioka(no: str, name: str, img: str) -> str:
    return f"""<h2>【新しい飼い主を探しています】（{no}）</h2>
<p class="imagecenter"><img alt="写真1" src="/_res/{img}1.jpg"/></p><p class="imagecenter"><img alt="写真2" src="/_res/{img}2.jpg"/></p>
<p>【猫（{no}）の情報】<br/>仮名：{name}<br/>種類：雑種<br/>毛色：茶白<br/>性別：オス（去勢手術済み）<br/>年齢：令和7年11月頃生まれ<br/>特徴：</p>
<p>事故により保護されました。</p><p>≪預かりボランティアさんからのメッセージ≫</p><p>元気です。</p>"""


def test_morioka_adoption_groups_each_h2_and_stops_before_the_fiv_section():
    html = ('<article id="content"><div id="voice"><p>現在、新しい飼い主を待っている動物は、次のとおりです。</p>'
            + _morioka("5－H", "ドラ", "dora") + _morioka("7－O", "ローリー", "rori")
            + "<h2>【FIV感染について】</h2><p>主に猫同士のケンカによる咬傷で感染します。</p></div></article>")
    res = _build("city_morioka-1", html)
    assert [(a["name"], a["management_no"]) for a in res.animals] == [("ドラ", "5-H"), ("ローリー", "7-O")]
    a = res.animals[0]
    assert a["species"] == "cat" and a["image_url"].endswith("/_res/dora1.jpg")
    assert (a["breed"], a["color"], a["sex"], a["age"]) == ("雑種", "茶白", "オス", "令和7年11月頃生まれ")
    assert a["note"] == "事故により保護されました。"


def test_morioka_stray_zero_day_is_confirmed():
    html = '<article id="content"><div id="voice"><p>現在、盛岡市保健所で、元の飼い主を待っている動物はいません。</p><h2>犬の返還に必要なもの</h2><p>返還手数料：3000円</p><h2>注意事項</h2></div></article>'
    res = _build("city_morioka-2", html)
    assert res.animals == [] and res.empty_confirmed


def test_hakodate_stray_empty_placeholder_is_not_an_animal_and_zero_day_is_confirmed():
    html = ('<article><div class="body"><div class="text-beginning"><div class="body"><h2>収容（行方不明）犬・猫情報</h2>'
            '<h2>【犬】</h2><p>現在，該当する犬はおりません。</p><div class="temp1 clearfix"><div class="thumb"> </div></div>'
            '<h2>【猫】</h2><p>現在，該当する猫はおりません。</p><div></div><h2>注意事項</h2></div></div></div></article>')
    res = _build("city_hakodate-1", html)
    assert res.animals == [] and res.empty_confirmed


def test_otaru_stray_zero_day_is_confirmed():
    html = ('<div class="susanoo-editable-field"><div><p>迷い犬の情報です。</p></div><h2>収容犬について</h2>'
            "<div><p>現在、収容犬はいません。</p><p>M7-1のチワワ系雑種は飼い主のもとに戻りました。</p></div></div>")
    res = _build("city_otaru-1", html)
    assert res.animals == [] and res.empty_confirmed
