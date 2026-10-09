"""T517 ⑥: label 指定の値の取り方のテスト（ネットワークなし）。

隣の値が label の文字を含むだけなら取る（熊本県動愛「保健所 → 菊池保健所」）。
隣のセルが見出しの形（label と同じ文字、label で始まる見出しが並ぶ行）なら今まで通り捨てる。
"""

from bs4 import BeautifulSoup
from collector.recipe import Doc, Row, field_value


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _row(html: str) -> Row:
    el = BeautifulSoup(html, "lxml").body.contents[0]
    return Row(doc=_doc(html), el=el)


# --- 6. label の値が label の文字を含む ---------------------------------------------
# 熊本県動愛の一覧（2026-10-05 実ページ ul.list-4col li の 1 件。空白・改行を詰めた）
KUMAMOTO = """<li><a href="/animals/detail/4936"><figure class="pht"><img alt="" src="/files/cache/a.png"/></figure>
<div class="txt"><dl>
<dt>種類</dt><dd>雑種(ミックス)</dd>
<dt>性別</dt><dd>オス</dd>
<dt>個体管理ナンバー</dt><dd>DC00798</dd>
<dt>保健所</dt><dd>菊池保健所</dd>
<dt>電話番号</dt><dd>0968-25-4135</dd>
</dl></div></a></li>"""


def test_label_value_may_contain_the_label_in_dl():
    row = _row(KUMAMOTO)
    assert field_value({"label": "保健所"}, row) == "菊池保健所"
    # 10/4 にレシピを逃がした selector と同じ値になる（レシピを label に戻しても同じ）
    assert field_value({"selector": "dt:-soup-contains('保健所') + dd"}, row) == "菊池保健所"
    assert field_value({"label": "電話番号"}, row) == "0968-25-4135"


def test_label_value_may_contain_the_label_in_th_td_and_td_td():
    th = _row("<table><tr><th>収容場所</th><td>動物愛護センター収容場所（菊池市）</td></tr></table>")
    assert field_value({"label": "収容場所"}, th) == "動物愛護センター収容場所(菊池市)"   # 値は NFKC で半角括弧になる
    td = _row("<table><tr><td>保健所</td><td>水俣保健所</td></tr></table>")
    assert field_value({"label": "保健所"}, td) == "水俣保健所"


def test_label_skips_neighbour_heading_cells_in_header_rows():
    """見出しが td で横に並ぶ表（収容日｜収容場所 / 値の行）。label「収容」の隣は見出しなので、下の行の同じ列を取る。"""
    row = _row("""<table>
      <tr><td>収容日</td><td>収容場所</td><td>保健所</td></tr>
      <tr><td>9月1日</td><td>菊池市</td><td>菊池保健所</td></tr></table>""")
    assert field_value({"label": "収容"}, row) == "9月1日"
    assert field_value({"label": "保健所"}, row) == "菊池保健所"     # 下の行の値が label を含むだけなら取る


def test_label_skips_neighbour_that_only_repeats_the_label():
    """隣の値が label そのもの（「性別：」のような見出しの繰り返し）なら値とみなさない。"""
    row = _row("<table><tr><td>性別</td><td>性別：</td></tr><tr><td>オス</td><td>メス</td></tr></table>")
    assert field_value({"label": "性別"}, row) == "オス"


def test_label_value_with_inner_label_colon_keeps_the_text_fallback():
    """値のセルの中に「備考: …」と label が書かれているとき（高知県 kochi_apc の個体ページ）は、今まで通り
    セル全体ではなく「備考:」の後ろを取る（A/B で 13 頭の note がセル全体に変わったため、前の挙動を保つ）。"""
    row = _row("""<table><tr><th>備考</th><td>8/10午前8時頃、竹島にて発見されました。<br>収容日（8/10）<br>
      備考: 先住犬がいれば必ずマッチングが必要です<br>希望者の方は直接センターに連絡の上、来所ください。</td></tr></table>""")
    assert field_value({"label": "備考"}, row) == "先住犬がいれば必ずマッチングが必要です"


def test_label_value_containing_the_label_in_th_td_rows():
    """沖縄県 aniwel_okinawa-3（行方不明犬）の年齢: 値「人間の年齢で64歳」が label「年齢」を含むので捨てられ、
    次の候補（値のセル自身）の隣を見て「首輪」を取っていた。th → td の組なので値をそのまま取る。"""
    row = _row("""<table><tr><th>体格</th><td>中</td><th>年齢</th><td>人間の年齢で64歳</td>
      <th>首輪</th><td>有り</td></tr></table>""")
    assert field_value({"label": "年齢"}, row) == "人間の年齢で64歳"
