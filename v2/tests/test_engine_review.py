"""公開前レビュー（2026-09-30）の指摘に対するエンジンのテスト: PDF の source_url、プレースホルダ画像、detail リンクを持つ行。"""

from bs4 import BeautifulSoup

from collector.extract import build, make_id
from collector.recipe import Doc, Recipe
from collector.registry import Source

ENTRY = "https://www.pref.kagawa.lg.jp/chusanhoken/inu-neko/index.html"


def _src(slug="t", url=ENTRY, species="mixed"):
    return Source(slug=slug, name="t", municipality="t", prefecture="香川県", url=url, kind="stray", species=species)


def _pdf_doc(url: str) -> Doc:
    text = "個体管理番号 26-0001 収容日 2026/9/28 種類 犬\n個体管理番号 26-0002 収容日 2026/9/28 種類 猫"
    return Doc(url=url, pdf_text=text, pdf_tables=[[["個体管理番号", "収容日", "種類"], ["26-0001", "2026/9/28", "犬"], ["26-0002", "2026/9/28", "猫"]]])


def test_pdf_source_url_defaults_to_entry_page():
    """日次で差し替わる PDF（r8-9-28.pdf）の URL は翌日 404 になるので、既定では台帳の入口ページを source_url にする。"""
    recipe = Recipe.from_dict({"pdf": {"mode": "table"}, "fields": {"management_no": {"header": "個体管理番号"}, "shelter_date": {"header": "収容日"}, "species": {"header": "種類"}},
                               "species": {"from": "field", "map": {"犬": "dog", "猫": "cat"}}})
    pdf_url = "https://www.pref.kagawa.lg.jp/documents/375/r8-9-28.pdf"
    res = build(_src(), recipe, [_pdf_doc(pdf_url)])
    assert len(res.animals) == 2
    assert {a["source_url"] for a in res.animals} == {ENTRY}
    # レシピの url:（入口の上書き）があればそちら
    recipe.url = "https://www.pref.kagawa.lg.jp/other/entry.html"
    assert build(_src(), recipe, [_pdf_doc(pdf_url)]).animals[0]["source_url"] == recipe.url
    # source_url: doc で PDF そのものを指すこともできる
    recipe.url = None
    recipe.source_url = "doc"
    assert build(_src(), recipe, [_pdf_doc(pdf_url)]).animals[0]["source_url"] == pdf_url


def test_placeholder_image_is_not_a_photo_but_detail_link_keeps_row():
    """山梨県: 写真なしの子は自治体のプレースホルダ画像 noimage01.jpg を持つ。写真として載せず、個体ページ（detail）がある行は動物として残す。"""
    html = """<div class="menu_item"><img src="/img/noimage01.jpg"><div class="item_link_ttl"><p class="txt"><a href="/detail.php?id=101">甲府市</a></p><p>オス</p><p>茶</p></div></div>
    <div class="menu_item"><img src="/img/noimage_tori.png"><div class="item_link_ttl"><p class="txt"><a href="/detail.php?id=102">笛吹市</a></p><p>メス</p><p>白</p></div></div>
    <div class="menu_item"><img src="/img/noimage01.jpg"><div class="item_link_ttl"><p class="txt">案内文だけの行</p></div></div>"""
    recipe = Recipe.from_dict({"rows": "div.menu_item", "image": "img@src",
                               "fields": {"location": "div.item_link_ttl > p.txt", "sex": "div.item_link_ttl > p:nth-of-type(2)",
                                          "detail": {"selector": "div.item_link_ttl > p.txt a", "attr": "href"}}})
    doc = Doc(url="https://www.pref.yamanashi.jp/cat/", html=html, soup=BeautifulSoup(html, "lxml"))
    res = build(_src(slug="pref_yamanashi-6", url=doc.url, species="cat"), recipe, [doc])
    assert len(res.animals) == 2 and len(res.dropped) == 1      # 個体ページの無い案内文の行は落ちる
    assert all(a["image_url"] is None for a in res.animals)     # プレースホルダは写真ではない
    assert [a["source_url"] for a in res.animals] == ["https://www.pref.yamanashi.jp/detail.php?id=101", "https://www.pref.yamanashi.jp/detail.php?id=102"]
    assert res.animals[0]["id"] != res.animals[1]["id"]          # ID は個体ページの URL で決まる


def test_make_id_prefers_image_then_mgmt_then_detail():
    s = _src()
    assert make_id(s, "a.jpg", {}) == make_id(s, "a.jpg", {"management_no": "1"})
    assert make_id(s, None, {"management_no": "26-0001"}) != make_id(s, None, {"management_no": "26-0002"})
    assert make_id(s, None, {}, detail="/d?id=1") != make_id(s, None, {}, detail="/d?id=2")
    assert make_id(s, None, {"name": "x", "shelter_date": "9月1日"}) == make_id(s, None, {"name": "x", "shelter_date": "9月1日"})
