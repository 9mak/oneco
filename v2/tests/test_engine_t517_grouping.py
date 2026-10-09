"""T517 ③④ のエンジン修正のテスト（ネットワークなし。HTML は 2026-10-05 の実ページから必要な部分だけ抜いた）。

③ row_until: rows に当たった要素を 1 頭の始まりとし、後ろの兄弟要素を「次の rows の要素」か
   「row_until に当たる要素」の手前までまとめて 1 行にする（鹿児島市・大分市・千葉市・さいたま市・柏市）
④ image.scope: next_siblings / self_or_next_siblings: 写真が行の後ろの兄弟要素にあるとき（名古屋市 譲渡猫）
"""

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe, extract_rows, field_value, image_url
from collector.registry import Source


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _src(kind: str = "sheltered", species: str = "dog") -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="鹿児島県", url="https://x.jp/a/", kind=kind, species=species)


# --- ③ row_until: 鹿児島市（h2 → 写真入りの p → 項目の p …）------------------------------
KAGOSHIMA = """<div id="tmp_contents">
<h1>保護された犬の情報</h1>
<p align="left"><strong>注意事項</strong></p>
<h2>No.260062</h2>
<p><img alt="260062" src="/joho/images/260062.jpg">保護日：令和8年10月2日（金曜日）</p>
<p>保護期限：令和8年10月14日（水曜日）</p>
<p>保護場所：宇宿3丁目</p>
<p>種類：トイプードル</p>
<p>性別：雄</p>
<p>体格：小</p>
<p>推定年齢：10歳</p>
<h2>No.260058（<span class="txt_green">飼い主のもとに戻りました</span>）</h2>
<p><img alt="260058" src="/joho/images/2026_09140001.jpg">保護日：令和8年9月14日（月曜日）</p>
<p>種類：雑種</p>
<h2>No.260039</h2>
<p>保護日：令和8年8月11日（火曜日）</p>
<p>保護場所：星ヶ峯3丁目</p>
<p>種類：雑種</p>
<p>性別：雄</p>
<p> </p>
</div>"""

KAGOSHIMA_RECIPE = {
    "rows": "#tmp_contents > h2",
    "row_until": "h2",
    "row_filter": {"text_has_any": ["No"], "text_lacks": ["戻りました"]},
    "fields": {
        "management_no": {"selector": "h2", "regex": "No\\.?\\s*(\\d+)"},
        "shelter_date": {"label": "保護日"},
        "location": {"label": "保護場所"},
        "breed": {"label": "種類"},
        "sex": {"label": "性別"},
        "size": {"label": "体格"},
        "age": {"label": "推定年齢"},
    },
}


def test_row_until_groups_flat_siblings_into_one_row():
    recipe = Recipe.from_dict(KAGOSHIMA_RECIPE)
    rows = extract_rows(recipe, _doc(KAGOSHIMA))
    assert len(rows) == 2                                    # 返還済み（見出しに「戻りました」）は 1 頭分まとめて捨てる
    f = {k: field_value(s, rows[0]) for k, s in recipe.fields.items()}
    assert f == {"management_no": "260062", "shelter_date": "令和8年10月2日(金曜日)", "location": "宇宿3丁目",
                 "breed": "トイプードル", "sex": "雄", "size": "小", "age": "10歳"}
    assert image_url(recipe, rows[0])[0] == "https://x.jp/joho/images/260062.jpg"
    assert image_url(recipe, rows[1]) == (None, None)        # 写真の無い子に次の子（返還済み）の写真を付けない
    assert field_value(recipe.fields["breed"], rows[1]) == "雑種"


def test_row_until_rows_go_through_build():
    recipe = Recipe.from_dict(KAGOSHIMA_RECIPE)
    res = build(_src(), recipe, [_doc(KAGOSHIMA)])
    assert [(a["management_no"], a["sex"], a["image_url"]) for a in res.animals] == [
        ("260062", "雄", "https://x.jp/joho/images/260062.jpg"),
        ("260039", "雄", None),
    ]


def test_without_row_until_rows_are_unchanged():
    recipe = Recipe.from_dict({k: v for k, v in KAGOSHIMA_RECIPE.items() if k != "row_until"})
    rows = extract_rows(recipe, _doc(KAGOSHIMA))
    assert [r.text() for r in rows] == ["No.260062", "No.260039"]   # 既存レシピ（row_until 無し）は要素 1 つ = 1 行のまま


# --- ③ row_until に当たる要素で止める: 千葉市（h4 番号 → p … → h2 掲載日 → h4 …）------------
CHIBA = """<div id="contents_editable">
<h1>市民等が保護している猫の情報</h1>
<h4>猫は逃がさないように飼いましょう。</h4>
<h2>2026年９月25日掲載</h2>
<h4>A-6035</h4>
<p><img alt="6035" src="/images/6035.jpg"></p>
<p>保護日：令和８年9月24日</p>
<p>性別：不明</p>
<p> </p>
<h2>2026年9月7日掲載</h2>
<h4>A-6028</h4>
<p>保護日：令和８年9月5日</p>
<p>性別：メス</p>
<h4>A-6027</h4>
<p>保護日：令和８年9月5日</p>
<p>性別：メス</p>
</div>"""


def test_row_until_stops_before_the_until_element():
    recipe = Recipe.from_dict({"rows": "div#contents_editable h4", "row_until": "h2",
                               "row_filter": {"text_has_any": ["保護日"]}})
    rows = extract_rows(recipe, _doc(CHIBA))
    assert [r.text() for r in rows] == [
        "A-6035 保護日：令和８年9月24日 性別：不明",          # 次の「2026年9月7日掲載」の h2 は入れない
        "A-6028 保護日：令和８年9月5日 性別：メス",
        "A-6027 保護日：令和８年9月5日 性別：メス",
    ]


def test_from_heading_in_grouped_row_uses_original_position():
    """まとめた行は複製なので文書上の位置を持たない。from: heading は元の始まり要素を基準にする。"""
    recipe = Recipe.from_dict({"rows": "div#contents_editable h4", "row_until": "h2",
                               "row_filter": {"text_has_any": ["保護日"]},
                               "fields": {"note": {"from": "heading", "selector": "h2"}}})
    rows = extract_rows(recipe, _doc(CHIBA))
    assert [field_value(recipe.fields["note"], r) for r in rows] == ["2026年9月25日掲載", "2026年9月7日掲載", "2026年9月7日掲載"]


def test_from_heading_on_the_start_heading_itself_points_to_the_previous_one():
    """始まりの要素が見出しそのもの（rows: h4）のとき、from: heading の h4 は「前の子の見出し」になる。
    自分の見出しは selector で取る（RECIPE.md に明記）。"""
    recipe = Recipe.from_dict({"rows": "div#contents_editable h4", "row_until": "h2",
                               "row_filter": {"text_has_any": ["保護日"]},
                               "fields": {"by_heading": {"from": "heading", "selector": "h4"},
                                          "by_selector": {"selector": "h4"}}})
    rows = extract_rows(recipe, _doc(CHIBA))
    assert field_value(recipe.fields["by_heading"], rows[2]) == "A-6028"
    assert field_value(recipe.fields["by_selector"], rows[2]) == "A-6027"


# --- ③ 次の始まりを中に含む兄弟でも止める: さいたま市（1 頭目は平ら、2 頭目は div に包まれている）-------
SAITAMA = """<div class="wysiwyg_area">
<h2>迷子の犬を保護しています</h2>
<p>管理番号 R08-8</p>
<p><img alt="R8-8" src="./img/292_s.jpg"></p>
<ul><li><strong>収容日：令和8年9月26日</strong></li><li><strong>性別：オス</strong></li></ul>
<div><p>管理番号 R08-9</p><p><img alt="R8-9" src="./img/295_s.jpg"></p>
<ul><li><strong>収容日：令和8年9月29日</strong></li><li><strong>性別：メス</strong></li></ul></div>
<h2>返還申請について</h2>
<p>飼い主様は、動物愛護ふれあいセンターまで早急に連絡をしてください。</p>
</div>"""


def test_grouping_stops_at_a_sibling_that_contains_the_next_start():
    recipe = Recipe.from_dict({"rows": "div.wysiwyg_area p:-soup-contains('管理番号')", "row_until": "h2",
                               "fields": {"sex": {"label": "性別"}, "shelter_date": {"label": "収容日"}}})
    rows = extract_rows(recipe, _doc(SAITAMA))
    assert len(rows) == 2
    assert [field_value(recipe.fields["sex"], r) for r in rows] == ["オス", "メス"]
    assert [image_url(recipe, r)[0] for r in rows] == ["https://x.jp/a/img/292_s.jpg", "https://x.jp/a/img/295_s.jpg"]
    assert "返還申請" not in rows[1].text()


# --- ③ species: {from: heading} も元の位置で: 柏市（h3 猫/犬 → div 写真 → p 名前 … → hr）------------
KASHIWA = """<div id="tmp_contents">
<h3><a id="cat" name="cat">猫</a></h3>
<div class="col2_sp2_wrap"><p><img alt="ぽぽ" src="/images/s-popo.jpg"></p></div>
<p><b>ぽぽ</b>（070201）</p>
<p>オス(去勢手術済み)　2010年生(推定)</p>
<hr/>
<h3><a id="dog" name="dog">犬</a></h3>
<div class="col2_sp2_wrap"><p><img alt="コロ" src="/images/koro.jpg"></p></div>
<p><b>コロ</b>（070301）</p>
<p>メス(不妊手術済み)　2020年生(推定)</p>
<hr/>
</div>"""


def test_species_from_heading_in_grouped_row():
    recipe = Recipe.from_dict({"rows": "div.col2_sp2_wrap", "row_until": "hr",
                               "species": {"from": "heading", "selector": "h3", "map": {"猫": "cat", "犬": "dog"}},
                               "fields": {"management_no": {"regex": "[（(](\\d{4,6})[）)]"}}})
    res = build(_src(kind="adoption", species="mixed"), recipe, [_doc(KASHIWA)])
    assert [(a["management_no"], a["species"], a["image_url"]) for a in res.animals] == [
        ("070201", "cat", "https://x.jp/images/s-popo.jpg"),
        ("070301", "dog", "https://x.jp/images/koro.jpg"),
    ]


def test_prev_siblings_in_grouped_row_walks_from_the_original_start():
    """写真が始まりの要素より前にあるとき（川崎市: 写真の div → 表の div）。まとめた行でも元の位置から遡る。"""
    html = """<div class="c"><div class="img"><img src="/p1.jpg"></div><div class="tbl">管理番号 R8-161</div><p>備考：なし</p>
<div class="img"><img src="/p2.jpg"></div><div class="tbl">管理番号 R8-162</div><p>備考：なし</p></div>"""
    recipe = Recipe.from_dict({"rows": "div.tbl", "row_until": "div.img",
                               "image": {"selector": "img@src", "scope": "prev_siblings", "stop_at": "row"}})
    rows = extract_rows(recipe, _doc(html))
    assert [r.text() for r in rows] == ["管理番号 R8-161 備考：なし", "管理番号 R8-162 備考：なし"]
    assert [image_url(recipe, r)[0] for r in rows] == ["https://x.jp/p1.jpg", "https://x.jp/p2.jpg"]


# --- ④ image.scope: next_siblings: 名古屋市 譲渡猫（h2 → 写真の p が後ろに 1〜2 枚）-------------
NAGOYA = """<article id="content"><div>
<h2>飼主募集中の猫の情報コーナー</h2>
<p>このコーナーでは、長期にわたり…</p>
<h2>センター名：ネプ（06-0286）</h2>
<p class="imagecenter"><img alt="写真：飼主募集中猫ネプの紹介ポスターです。" src="../_res/804/nepu.jpeg"></p>
<p class="imagecenter"><img alt="写真：飼主募集中猫ネプの健康状態の説明です。" src="../_res/804/nepu2.jpeg"></p>
<h2>センター名：クロ（06-0999）</h2>
<h2>センター名：なぎさ（07-0301）</h2>
<p class="imagecenter"><img alt="なぎさの紹介カード" src="../_res/804/nagisa.jpeg"></p>
<div id="reference"><h2>お問い合わせ</h2><img src="/mail.gif"></div>
</div></article>"""


def test_next_siblings_takes_the_first_photo_after_the_row():
    recipe = Recipe.from_dict({"rows": "article#content h2", "row_filter": {"text_has_any": ["センター名："]},
                               "image": {"selector": "p.imagecenter img@src", "scope": "next_siblings"}})
    rows = extract_rows(recipe, _doc(NAGOYA, url="https://x.jp/k/p/1017804.html"))
    assert [image_url(recipe, r)[0] for r in rows] == [
        "https://x.jp/k/_res/804/nepu.jpeg",
        None,                                    # 写真の無い子に次の子の写真を付けない（次の h2 で止まる）
        "https://x.jp/k/_res/804/nagisa.jpeg",
    ]


def test_next_siblings_ignores_images_inside_the_row_and_self_or_next_prefers_them():
    html = """<div><p class="r">名前：タロ <img src="/in.jpg"></p><p class="ph"><img src="/after1.jpg"></p>
<p class="r">名前：ハナ</p><p class="ph"><img src="/after2.jpg"></p></div>"""
    nxt = Recipe.from_dict({"rows": "p.r", "image": {"selector": "img@src", "scope": "next_siblings", "stop_at": "row"}})
    rows = extract_rows(nxt, _doc(html))
    assert [image_url(nxt, r)[0] for r in rows] == ["https://x.jp/after1.jpg", "https://x.jp/after2.jpg"]
    both = Recipe.from_dict({"rows": "p.r", "image": {"selector": "img@src", "scope": "self_or_next_siblings", "stop_at": "row"}})
    assert [image_url(both, r)[0] for r in rows] == ["https://x.jp/in.jpg", "https://x.jp/after2.jpg"]


def test_next_siblings_default_stops_at_same_tag_and_stop_at_row_walks_past_it():
    """行も写真も p のとき、既定（同じタグ名で止める）は写真の p で止まる。stop_at: row なら次の行まで進む。"""
    html = """<div><p>名前：タロ</p><p class="ph"><img src="/a.jpg"></p><p>名前：ハナ</p></div>"""
    default = Recipe.from_dict({"rows": "p:-soup-contains('名前')", "image": {"selector": "p.ph img@src", "scope": "next_siblings"}})
    rows = extract_rows(default, _doc(html))
    assert [image_url(default, r)[0] for r in rows] == [None, None]
    by_row = Recipe.from_dict({"rows": "p:-soup-contains('名前')",
                               "image": {"selector": "p.ph img@src", "scope": "next_siblings", "stop_at": "row"}})
    assert [image_url(by_row, r)[0] for r in rows] == ["https://x.jp/a.jpg", None]
