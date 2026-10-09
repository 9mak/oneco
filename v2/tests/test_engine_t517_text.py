"""T517 ⑦: 文字の連結のテスト（ネットワークなし）。

span 等のインライン要素の境目には空白を入れない（佐世保市「<span>令</span>和8年…」が
「令 和8年…」になっていた）。ブロック要素（td・p・br 等）の境目と、元からある空白は今まで通り 1 つの空白。
"""

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe, Row, field_value
from collector.registry import Source


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _row(html: str) -> Row:
    el = BeautifulSoup(html, "lxml").body.contents[0]
    return Row(doc=_doc(html), el=el)


# --- 7. インライン要素の境目に空白を入れない ---------------------------------------------
# 佐世保市（tests/adapters/rule_based/fixtures/city_sasebo.html、2026-03-29 保存の実ページの文字化けを直したもの）の 1 頭分。
# 2026-10-05 の実ページも同じ作り（<span class="space_lft1">犬の返</span>還… のように先頭の数文字だけ span）
SASEBO = """<div id="tmp_contents">
<h2>動物愛護センターで保護している犬です</h2>
<p>写真をクリックすると、詳しい情報が表示されます。</p>
<p><a href="/hokenhukusi/seikat/20260313_dog01.html"><img align="middle" alt="0313" height="150" src="/images/16626/img_4232_1.jpg" width="100"><span class="space_lft1">令</span>和8年3月13日（金曜日）山祇町（雑種、オス）</a></p>
<h2>市民の方が保護している犬です</h2>
<p>～現在、情報はありません～</p>
</div>"""

SASEBO_RECIPE = {
    "rows": "div#tmp_contents p:has(a[href*='_dog'])",
    "fields": {
        "detail": {"selector": "a[href*='_dog']", "attr": "href"},
        "shelter_date": {"regex": "((?:令\\s*和|平\\s*成)?\\s*\\d+年\\d+月\\d+日)"},
        "location": {"regex": "日（[^）]*）\\s*(.+?)（"},
        "breed": {"regex": "（([^（）、]+)、[^（）]*）\\s*$"},
        "sex": {"regex": "、\\s*(オス|メス|雄|雌)"},
    },
}


def test_span_split_characters_are_joined_without_space():
    recipe = Recipe.from_dict(SASEBO_RECIPE)
    src = Source(slug="t", name="t", municipality="佐世保市", prefecture="長崎県", url="https://x.jp/a/", kind="sheltered", species="dog")
    res = build(src, recipe, [_doc(SASEBO)])
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["shelter_date"] == "令和8年3月13日"
    assert a["location"] == "山祇町"
    assert a["breed"] == "雑種"
    assert a["sex"] == "オス"


def test_inline_join_in_selector_and_label_values():
    row = _row("<table><tr><th>収容日</th><td><span>令</span>和8年<b>3</b>月13日</td></tr></table>")
    assert field_value({"label": "収容日"}, row) == "令和8年3月13日"
    assert field_value({"selector": "td"}, row) == "令和8年3月13日"


def test_block_boundaries_and_real_spaces_still_separate_words():
    """「犬 オス」が「犬オス」にならない: セル・改行（br）・元からある空白の境目は空白のまま。"""
    cells = _row("<table><tr><td>犬</td><td>オス</td></tr></table>")
    assert field_value({"selector": "."}, cells) == "犬 オス"
    br = _row("<table><tr><th>特徴</th><td>オス<br>3歳</td></tr></table>")
    assert field_value({"label": "特徴"}, br) == "オス 3歳"
    spaced = _row("<p><span>犬</span> <span>オス</span>\n<em>3歳</em></p>")
    assert field_value({"selector": "."}, spaced) == "犬 オス 3歳"
    para = _row("<div><p>犬</p><p>オス</p></div>")
    assert field_value({"selector": "."}, para) == "犬 オス"
