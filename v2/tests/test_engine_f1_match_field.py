"""10/5 監査 F1: 写真が本体と別の表にあるページで、行の管理番号を含む写真を文書全体から探す
（image.match_field）。仙台市 譲渡猫は「管理番号/猫の種類/…」の表と「管理番号/写真1/写真2」の表が分かれている。
ネットワークなし。"""

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe, extract_rows, image_url
from collector.registry import Source


def _doc(html: str, url: str = "https://x.jp/joho/neko.html") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _src(url: str = "https://x.jp/joho/neko.html") -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="宮城県", url=url, kind="adoption", species="cat")


SENDAI = """<div id="tmp_contents">
<table class="datatable"><caption>譲渡対象猫の情報</caption>
<tr><th>管理番号</th><th>猫の種類</th><th>性別</th></tr>
<tr><td>C25093</td><td>雑種</td><td>去勢雄</td></tr>
<tr><td>C25103</td><td>雑種</td><td>避妊雌</td></tr>
<tr><td>C25200</td><td>雑種</td><td>避妊雌</td></tr>
</table>
<table class="datatable"><caption>譲渡猫の写真</caption>
<tr><th>管理番号</th><th>写真1</th><th>写真2</th></tr>
<tr><td>C25093</td><td><img alt="譲渡猫情報第C25093号(3)" src="/joho/images/c25093-3.jpg"></td>
<td><img alt="譲渡猫情報第C25093号(4)" src="/joho/images/c25093-4.jpg"></td></tr>
<tr><td>C25103</td><td><img alt="譲渡猫情報第C25103号(3)" src="/joho/images/c25103-3.jpg"></td><td> </td></tr>
</table>
</div>"""

RECIPE = {
    "rows": "table.datatable:nth-of-type(1) tr",
    "image": {"selector": "img@src", "match_field": "management_no"},
    "fields": {
        "management_no": {"selector": "td:nth-of-type(1)"},
        "sex": {"selector": "td:nth-of-type(3)"},
    },
}


def test_match_field_picks_first_photo_whose_src_or_alt_has_the_rows_management_no():
    recipe = Recipe.from_dict(RECIPE)
    res = build(_src(), recipe, [_doc(SENDAI)])
    got = [(a["management_no"], a["image_url"]) for a in res.animals]
    assert got == [
        ("C25093", "https://x.jp/joho/images/c25093-3.jpg"),   # 文書順で先の 1 枚（写真1）
        ("C25103", "https://x.jp/joho/images/c25103-3.jpg"),
        ("C25200", None),                                       # 写真の表に無い子に別の子の写真を付けない
    ]
    assert [d.text[:4] for d in res.dropped] == ["管理番号"]     # 見出し行だけ捨てる


def test_match_field_uses_alt_when_src_has_no_number():
    html = """<table class="a"><tr><td>A12</td></tr><tr><td>A13</td></tr></table>
<p><img alt="第A13号" src="/img/p1.jpg"><img alt="第A12号" src="/img/p2.jpg"></p>"""
    recipe = Recipe.from_dict({
        "rows": "table.a tr",
        "image": {"selector": "img@src", "match_field": "management_no"},
        "fields": {"management_no": {"selector": "td"}},
    })
    doc = _doc(html, "https://x.jp/")
    rows = extract_rows(recipe, doc)
    got = [image_url(recipe, r, {"management_no": n})[0] for r, n in zip(rows, ["A12", "A13"])]
    assert got == ["https://x.jp/img/p2.jpg", "https://x.jp/img/p1.jpg"]


def test_match_field_does_not_match_inside_a_longer_number():
    html = """<table class="a"><tr><td>C2509</td></tr></table>
<p><img alt="第C25093号" src="/img/c25093-3.jpg"><img alt="x" src="/img/c125093.jpg"></p>"""
    recipe = Recipe.from_dict({
        "rows": "table.a tr",
        "image": {"selector": "img@src", "match_field": "management_no"},
        "fields": {"management_no": {"selector": "td"}},
    })
    rows = extract_rows(recipe, _doc(html, "https://x.jp/"))
    assert image_url(recipe, rows[0], {"management_no": "C2509"}) == (None, None)   # C25093 の写真を C2509 に付けない
    assert image_url(recipe, rows[0], {"management_no": "25093"}) == (None, None)   # c125093 にも c25093 にも前後が英数字


def test_match_field_without_value_or_fields_gives_no_photo():
    recipe = Recipe.from_dict(RECIPE)
    rows = extract_rows(recipe, _doc(SENDAI))
    assert image_url(recipe, rows[1], {"management_no": None}) == (None, None)
    assert image_url(recipe, rows[1]) == (None, None)        # 項目を渡さない呼び出し（旧来の形）では探さない


def test_match_field_still_skips_junk_and_excluded_images():
    html = """<table class="a"><tr><td>D100</td></tr></table>
<img alt="D100" src="/common/icon_d100.png"><img alt="D100 ポスター" src="/img/d100_poster.jpg">
<img alt="D100" src="/img/d100.jpg">"""
    recipe = Recipe.from_dict({
        "rows": "table.a tr",
        "image": {"selector": "img@src", "match_field": "management_no", "exclude": ["poster"]},
        "fields": {"management_no": {"selector": "td"}},
    })
    rows = extract_rows(recipe, _doc(html, "https://x.jp/"))
    assert image_url(recipe, rows[0], {"management_no": "D100"})[0] == "https://x.jp/img/d100.jpg"


def test_without_match_field_row_scope_is_unchanged():
    recipe = Recipe.from_dict({**RECIPE, "image": "img@src"})
    res = build(_src(), recipe, [_doc(SENDAI)])
    assert [a["image_url"] for a in res.animals] == [None, None, None]   # 行（本体の表の tr）の中には写真が無い
