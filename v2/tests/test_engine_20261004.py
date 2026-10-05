"""2026-10-04 の再監査で足したエンジン修正のテスト（ネットワークなし）。

1. ゴミ画像判定の「search」はファイル名にだけ効かせる（町田市: 写真が search_cat.images/ 配下にあり全部捨てられていた）
2. empty_text は画像の alt も照合する（豊中市: 0 頭のときだけ「現在、掲載する情報はありません」の画像が出る）
3. image.scope: self_or_prev_siblings = 行の中を先に探し、無ければ直前の兄弟要素（岐阜県 西濃保健所だけ写真が表の外）
"""

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe, extract_rows, image_url
from collector.registry import Source


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _src(kind: str = "lost", species: str = "cat") -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="東京都", url="https://x.jp/a/", kind=kind, species=species)


# --- 1. search はファイル名だけ ------------------------------------------------------
MACHIDA = """<div id="contents">
<div class="row"><p><img src="search_cat.images/260930mayoineko369.jpg" alt="猫の写真"></p><p>猫（めす） 種類：雑種 失踪日時：2026年9月30日</p></div>
<div class="row"><p><img src="/img/btn_search.png" alt="検索"><img src="/img/search.gif" alt="検索"></p><p>猫（おす） 種類：雑種 失踪日時：2026年9月1日</p></div>
</div>"""


def test_search_token_only_rejects_file_names_not_directories():
    recipe = Recipe.from_dict({"rows": "div.row", "image": "img@src"})
    rows = extract_rows(recipe, _doc(MACHIDA))
    assert image_url(recipe, rows[0])[0] == "https://x.jp/a/search_cat.images/260930mayoineko369.jpg"
    assert image_url(recipe, rows[1]) == (None, None)        # 検索ボタンの画像は今まで通りゴミ扱い


# --- 2. empty_text は img の alt も見る -----------------------------------------------
TOYONAKA_EMPTY = """<div id="main"><h1>収容動物情報</h1>
<p>情報の更新は原則収容当日ですが、収容する時間帯によっては翌開庁日になることがあります。</p>
<p><img src="/img/no_info.gif" alt="現在、掲載する情報はありません"></p></div>"""


def test_empty_text_matches_image_alt():
    recipe = Recipe.from_dict({"rows": "table.animal tr:has(td)", "empty_text": ["現在、掲載する情報はありません"]})
    res = build(_src(kind="stray", species="dog"), recipe, [_doc(TOYONAKA_EMPTY)])
    assert res.animals == []
    assert res.empty_confirmed is True


def test_empty_text_not_confirmed_without_the_alt():
    html = TOYONAKA_EMPTY.replace('alt="現在、掲載する情報はありません"', 'alt=""')
    recipe = Recipe.from_dict({"rows": "table.animal tr:has(td)", "empty_text": ["現在、掲載する情報はありません"]})
    res = build(_src(kind="stray", species="dog"), recipe, [_doc(html)])
    assert res.empty_confirmed is False                     # 構造が変わって行が取れない日は failed のまま通知される


# --- 3. self_or_prev_siblings --------------------------------------------------------
GIFU = """<div class="detail_free">
<table><tr><td><strong>管理番号</strong></td><td>15</td></tr><tr><td>写真</td><td><img src="/uploaded/image/150001.jpg"></td></tr></table>
<p> </p>
<p><img alt="21-1" src="/uploaded/image/160709.jpg"><img alt="21-1" src="/uploaded/image/160711.jpg"></p>
<table><tr><td><strong>管理番号</strong></td><td>21</td></tr><tr><td><strong>収容日</strong></td><td>令和8年10月2日</td></tr></table>
<p> </p><p> </p>
<table><tr><td><strong>管理番号</strong></td><td> </td></tr><tr><td><strong>収容日</strong></td><td>令和8年月日</td></tr></table>
</div>"""


def test_self_or_prev_siblings_prefers_row_then_previous_siblings():
    recipe = Recipe.from_dict({"rows": "div.detail_free > table", "image": {"selector": "img@src", "scope": "self_or_prev_siblings"}})
    rows = extract_rows(recipe, _doc(GIFU))
    got = [image_url(recipe, r)[0] for r in rows]
    assert got == [
        "https://x.jp/uploaded/image/150001.jpg",   # 表の中の写真（他の保健所）
        "https://x.jp/uploaded/image/160709.jpg",   # 表の直前の p（西濃）
        None,                                       # 雛形の表: 直前の表で止まるので前の子の写真を拾わない
    ]


def test_prev_siblings_still_ignores_images_inside_the_row():
    recipe = Recipe.from_dict({"rows": "div.detail_free > table", "image": {"selector": "img@src", "scope": "prev_siblings"}})
    rows = extract_rows(recipe, _doc(GIFU))
    assert image_url(recipe, rows[0]) == (None, None)        # 既存の prev_siblings（広島市）は挙動を変えない


# --- 3b. prev_siblings の stop_at: row（2026-10-05）-----------------------------------
IWATE = """<div id="voice">
<h2>【譲渡】新しい飼い主さんを募集しています</h2>
<p class="imageright"><img src="/a.jpg" alt="タロ"></p>
<p>名前：タロ 種類：雑種 性別：オス</p>
<p class="imageright"><img src="/b.jpg" alt="ハナ"></p>
<p>名前：ハナ 種類：雑種 性別：メス</p>
<p>名前：ソラ 種類：雑種 性別：メス（写真なし）</p>
</div>"""


def test_prev_siblings_stop_at_row_walks_past_same_tag_photo_paragraphs():
    """岩手県: 行も写真も p。既定（同じタグ名で止まる）だと写真の p で止まって写真が付かない。
    stop_at: row なら「前の行（rows に当たる要素）」まで遡る。写真の無い子に前の子の写真を付けない。"""
    recipe = Recipe.from_dict({"rows": "div#voice p:-soup-contains('名前')",
                               "image": {"selector": "p.imageright img@src", "scope": "prev_siblings", "stop_at": "row"}})
    rows = extract_rows(recipe, _doc(IWATE))
    assert [image_url(recipe, r)[0] for r in rows] == ["https://x.jp/a.jpg", "https://x.jp/b.jpg", None]


def test_prev_siblings_default_still_stops_at_same_tag():
    recipe = Recipe.from_dict({"rows": "div#voice p:-soup-contains('名前')",
                               "image": {"selector": "p.imageright img@src", "scope": "prev_siblings"}})
    rows = extract_rows(recipe, _doc(IWATE))
    assert [image_url(recipe, r)[0] for r in rows] == [None, None, None]      # 既存のレシピ（広島市・明石・岐阜）の挙動は変えない


# --- 4. row_filter.field_has_any（field_lacks の逆）---------------------------------
def test_field_has_any_keeps_only_owner_searching_notices():
    """旭川市あにまある: 同じ一覧の「探しています」だけを 4 区分目 lost の別 slug で拾う（-7/-8 は field_lacks で除外のまま）。"""
    menu = "<nav>ペット探しています/保護しています</nav>"

    def page(title: str, img: str) -> Doc:
        html = f"{menu}<h2>{title}</h2><img class='p' src='/{img}.png'><table><tr><th>不明日</th><td>2026/09/21</td></tr></table>"
        return Doc(url=f"https://x.jp/{img}", html=html, soup=BeautifulSoup(html, "lxml"))

    recipe = Recipe.from_dict({"rows": "body", "image": "img.p@src",
                               "row_filter": {"field_has_any": {"name": ["探しています", "探してます"]}},
                               "fields": {"name": "h2", "shelter_date": {"label": "不明日"}}})
    res = build(_src(kind="lost", species="dog"), recipe, [page("犬 探しています(フルサワ)", "a"), page("犬を保護しています(サトウ)", "b")])
    assert [a["name"] for a in res.animals] == ["犬 探しています(フルサワ)"]
    assert [d.reason for d in res.dropped] == ["対象語なし（name）"]
    res2 = build(_src(kind="lost", species="dog"), recipe, [page("犬を保護しています(サトウ)", "b")])
    assert res2.animals == [] and res2.empty_confirmed        # 対象外だけの日は failed でなく empty
