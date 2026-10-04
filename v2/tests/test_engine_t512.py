"""T512 監査で足したエンジン機能のテスト: 項目を行より前の見出しから取る（from: heading）と、
写真を行の直前の兄弟要素から取る（image.scope: prev_siblings）。ネットワークなし。"""

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe, extract_rows, field_value
from collector.registry import Source


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


# --- 越谷市: 管理番号は表の前の h3 にだけある ------------------------------------
KOSHIGAYA = """<div id="tmp_honbun">
<h3 class="partsstyle_h3">R8-51</h3>
<table><thead><tr><th>収容場所</th><th>収容日</th><th>収容期限</th></tr></thead>
<tbody><tr><td>越谷市七左町6丁目地内</td><td>令和8年9月18日</td><td>令和8年10月1日</td></tr></tbody></table>
<table><tr><th>種類</th><th>性別</th></tr><tr><td>雑種</td><td>めす</td></tr></table>
<h3 class="partsstyle_h3">R8-50</h3>
<table><thead><tr><th>収容場所</th><th>収容日</th><th>収容期限</th></tr></thead>
<tbody><tr><td>越谷市七左町6丁目地内</td><td>令和8年9月18日</td><td>令和8年10月1日</td></tr></tbody></table>
</div>"""


def test_field_from_heading_gives_each_row_its_own_management_no():
    recipe = Recipe.from_dict({
        "rows": "div#tmp_honbun table:has(th:-soup-contains('収容場所')) tr:has(td)",
        "fields": {
            "location": {"selector": "td:nth-of-type(1)"},
            "shelter_date": {"selector": "td:nth-of-type(2)"},
            "management_no": {"from": "heading", "selector": "h3.partsstyle_h3"},
        },
    })
    doc = _doc(KOSHIGAYA)
    rows = extract_rows(recipe, doc)
    assert len(rows) == 2                                   # th だけのヘッダ行は tr:has(td) で外れる
    assert [field_value(recipe.fields["management_no"], r) for r in rows] == ["R8-51", "R8-50"]
    src = Source(slug="t", name="t", municipality="t", prefecture="埼玉県", url=doc.url, kind="sheltered", species="cat")
    res = build(src, recipe, [doc])
    assert [a["management_no"] for a in res.animals] == ["R8-51", "R8-50"]   # 同日同所でも別 ID
    assert [a["location"] for a in res.animals] == ["越谷市七左町6丁目地内"] * 2
    assert res.animals[0]["shelter_date"] == "令和8年9月18日"
    assert res.dropped == []


def test_field_from_heading_regex_applies_to_heading_text():
    html = "<h2>整理番号：8-9-12</h2><dl><dt>種類</dt><dd>雑種</dd></dl><h2>整理番号：</h2><dl><dt>種類</dt><dd></dd></dl>"
    recipe = Recipe.from_dict({
        "rows": "dl",
        "fields": {"management_no": {"from": "heading", "selector": "h2", "regex": "整理番号[:：]\\s*(\\d\\S*)"}},
    })
    rows = extract_rows(recipe, _doc(html))
    assert [field_value(recipe.fields["management_no"], r) for r in rows] == ["8-9-12", None]   # 雛形の空見出しは None


# --- 広島市: 写真は dl の直前の p.imagecenter（兄弟要素）にある --------------------
HIROSHIMA = """<div id="voice">
<h1>飼い主不明猫一覧</h1>
<div class="box"><img src="/_res/images/sns/share.png"></div>
<h2>整理番号：8-9-12</h2>
<p class="imagecenter"><img src="/_res/001/20260924-1.jpeg"></p>
<p class="imagecenter"><img src="/_res/001/20260924-2.jpeg"></p>
<dl><dt>収容月日</dt><dd>令和8年9月24日</dd><dt>種類</dt><dd>雑種</dd><dt>拾得等の場所</dt><dd>安佐北区白木町</dd></dl>
<h2>整理番号：</h2>
<dl><dt>収容月日</dt><dd>&nbsp;</dd><dt>種類</dt><dd>&nbsp;</dd></dl>
<p>広島市動物愛護センターは、土曜・日曜・祝日はお休みです。</p>
</div>"""


def test_image_from_prev_siblings_takes_first_photo_in_document_order():
    recipe = Recipe.from_dict({
        "rows": "div#voice dl",
        "image": {"selector": "p.imagecenter img@src", "scope": "prev_siblings"},
        "fields": {
            "shelter_date": {"label": "収容月日"},
            "location": {"label": "拾得等の場所"},
            "management_no": {"from": "heading", "selector": "h2", "regex": "整理番号[:：]\\s*(\\d\\S*)"},
        },
    })
    doc = _doc(HIROSHIMA)
    src = Source(slug="t", name="t", municipality="t", prefecture="広島県", url=doc.url, kind="stray", species="cat")
    res = build(src, recipe, [doc])
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["image_url"] == "https://x.jp/_res/001/20260924-1.jpeg"      # 2 枚のうち文書順で先の 1 枚
    assert a["management_no"] == "8-9-12"
    assert a["location"] == "安佐北区白木町"
    assert len(res.dropped) == 1                                             # 雛形の dl: 前の兄弟は空の h2 だけ（写真無し）


def test_image_prev_siblings_stops_at_previous_row():
    """2 頭目の dl から遡るとき、1 頭目の dl より前にある写真は取らない。"""
    html = """<div id="voice">
    <h2>整理番号：8-9-12</h2><p class="imagecenter"><img src="/a.jpg"></p><dl><dt>種類</dt><dd>雑種</dd></dl>
    <h2>整理番号：8-9-13</h2><dl><dt>種類</dt><dd>雑種</dd></dl>
    </div>"""
    recipe = Recipe.from_dict({
        "rows": "div#voice dl",
        "image": {"selector": "p.imagecenter img@src", "scope": "prev_siblings"},
        "fields": {"management_no": {"from": "heading", "selector": "h2", "regex": "整理番号[:：]\\s*(\\d\\S*)"}},
    })
    doc = _doc(html)
    src = Source(slug="t", name="t", municipality="t", prefecture="広島県", url=doc.url, kind="stray", species="dog")
    res = build(src, recipe, [doc])
    assert [a["image_url"] for a in res.animals] == ["https://x.jp/a.jpg", None]
    assert [a["management_no"] for a in res.animals] == ["8-9-12", "8-9-13"]
