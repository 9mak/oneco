"""T517 の公開前レビュー（2026-10-05）で見つかったエンジンの弱点のテスト（ネットワークなし）。

1. 「label：値」の最後の読み取りで、値が空欄の項目が次の項目（「性別：不明」）を拾わない（千葉市のまとめた行）
2. visible_text は入れ子が深い HTML でも RecursionError にならない（閉じ忘れの strong が重なるページ）
3. td で見出しが並ぶ行で、label が隣の見出しの末尾と一致しても見出しを値にしない（label「場所」と「収容場所」）
4. row_until: 始まりの間の裸の文字もまとめた行に入れる。区切りが兄弟の中にあればその兄弟の手前で止める
"""

from bs4 import BeautifulSoup

from collector.recipe import Doc, Recipe, extract_rows, field_value, image_url, visible_text


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _row(html: str, rows: str = "div.a", **recipe):
    r = Recipe.from_dict({"rows": rows, **recipe})
    return r, extract_rows(r, _doc(html))


# --- 1. 空欄の項目が次の項目を拾わない ------------------------------------------------
def test_label_fallback_does_not_take_the_next_label_when_value_is_blank():
    _, rows = _row("<div class='a'><p>毛色：</p><p>性別：不明</p><p>発見日：18:30頃</p></div>")
    assert field_value({"label": "毛色"}, rows[0]) is None
    assert field_value({"label": "性別"}, rows[0]) == "不明"
    assert field_value({"label": "発見日"}, rows[0]) == "18:30頃"      # 数字の「18:」は項目名ではない


# --- 2. 深い入れ子 --------------------------------------------------------------------
def test_visible_text_handles_deep_nesting():
    html = "<div class='a'>" + "<strong>" * 3000 + "x" + "</strong>" * 3000 + "<p>y</p></div>"
    el = BeautifulSoup(html, "lxml").select_one("div.a")
    assert visible_text(el) == "x y"


def test_visible_text_still_joins_inline_and_separates_blocks():
    el = BeautifulSoup("<div><p><span>令</span>和8年<br>3月</p><p>犬</p> <b>オス</b></div>", "lxml").div
    assert visible_text(el) == "令和8年 3月 犬 オス"


# --- 3. td の見出し行 -----------------------------------------------------------------
def test_label_in_td_header_row_skips_neighbor_heading_ending_with_label():
    html = "<table><tr><td>保護場所</td><td>収容場所</td></tr><tr><td>府中市</td><td>センター</td></tr></table>"
    _, rows = _row(html, rows="table")
    assert field_value({"label": "場所"}, rows[0]) == "府中市"


def test_label_in_th_td_pair_still_takes_value_containing_label():
    _, rows = _row("<table><tr><th>保健所</th><td>菊池保健所</td></tr></table>", rows="table")
    assert field_value({"label": "保健所"}, rows[0]) == "菊池保健所"


# --- 4. row_until の裸の文字・入れ子の区切り ---------------------------------------------
def test_grouped_rows_keep_bare_text_between_starts():
    html = "<div id='c'><h3>No.1</h3>種類：柴<br>性別：オス<h3>No.2</h3>種類：雑種</div>"
    _, rows = _row(html, rows="#c > h3", row_until="h3")
    assert [field_value({"regex": r"種類[:：]\s*(\S+)"}, r) for r in rows] == ["柴", "雑種"]


def test_grouped_rows_stop_before_sibling_that_contains_a_separator():
    html = ("<div id='c'><h3>No.1</h3><p>種類：柴</p>"
            "<div class='done'><h2>お家が決まりました</h2><p>No.9</p><img src='/9.jpg'></div></div>")
    recipe, rows = _row(html, rows="#c > h3", row_until="h2", image="img@src")
    assert len(rows) == 1
    assert "No.9" not in rows[0].text()
    assert image_url(recipe, rows[0]) == (None, None)       # 写真の無い No.1 に No.9 の写真を付けない
