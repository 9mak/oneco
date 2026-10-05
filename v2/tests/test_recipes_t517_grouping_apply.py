"""T517 ③ の適用: row_until を使うようにしたレシピ 7 枚が、実ページの構造から項目と写真を取れること（ネットワークなし）。

tests/fixtures/t517_*.html は 2026-10-05 の実ページから 1 頭分ずつ必要な部分だけを抜いたもの（レシピ本体 v2/recipes/<slug>.yaml をそのまま読む）。
どの slug も、変更前は 管理番号か名前だけ（写真・保護日・場所・性別などが空）だった。
共通の落とし穴: 次の子の項目・写真を前の子に付けないこと、写真の無い子に別の子の写真を付けないこと。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


# --- 柏市 譲渡: div.col2_sp2_wrap（写真）→ p 名前（番号）→ p 性別・生年 → p 性格 → hr ------------------------------
def test_kashiwa_2_groups_photo_name_and_following_paragraphs():
    res = _run("city_kashiwa-2", _fixture("t517_kashiwa-2.html"))
    assert [a["name"] for a in res.animals] == ["ぽぽ", "マヨ", "トロワ"]
    popo, mayo, troi = res.animals
    base = "https://www.city.kashiwa.lg.jp/images/3349/"
    assert _pick(popo, "management_no", "sex", "age", "image_url", "species") == {
        "management_no": "070201", "sex": "オス", "age": "2010年生(推定)", "image_url": base + "s-popo.jpg", "species": "cat"}
    assert _pick(mayo, "management_no", "sex", "age", "image_url") == {
        "management_no": "063001", "sex": "メス", "age": "2025.12月生(推定)", "image_url": base + "s-mayo.jpg"}
    # トロワだけ名前と性別・生年が同じ p にある。性格の文は 2 つの p をまとめて note にする
    assert _pick(troi, "management_no", "sex", "age", "image_url") == {
        "management_no": "031503", "sex": "オス", "age": "2016.4月生(推定)", "image_url": base + "s-pxl_20251122_031738606.jpg"}
    assert troi["note"].startswith("人に触られることに慣れてきて") and "おすすめです" in troi["note"]
    assert popo["note"].startswith("まだ、シャーやウーや猫パンチ")
    assert "小柄で怖がり" not in popo["note"] and "ワクチン" not in popo["note"]   # 次の子（マヨ）・性別の行は入らない
    assert res.dropped == []


# --- 越谷市 個人保護: h3 番号 → p 写真（迷子ポスター）→ p 写真 → p 発見場所 … ----------------------------------------
def test_koshigaya_kojin_groups_siblings_after_h3():
    res = _run("city_koshigaya_kojin", _fixture("t517_koshigaya_kojin.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "management_no", "species", "location", "color", "note") == {
        "management_no": "R8-001", "species": "cat", "location": "越谷市大沢4丁目付近", "color": "キジトラ", "note": "ピンク色の首輪あり"}
    assert a["shelter_date"] == "おおよそ2025年8月ごろ"
    # 1 枚目は文字入りの迷子ポスター（maigo_pos.jpg）。写真は 2 枚目の p の 1 枚目（maigo1_1.jpg）を使う
    assert a["image_url"].endswith("/hogo/images/maigo1_1.jpg")


# --- さいたま市 保護犬: 1 頭目は p 管理番号 → p 写真 → ul が平ら、2 頭目は div に包まれる ---------------------------
def test_saitama_1_reads_the_ul_labels_for_both_layouts():
    res = _run("city_saitama-1", _fixture("t517_saitama-1.html"))
    assert [a["management_no"] for a in res.animals] == ["R8-8", "R8-9"]
    flat, wrapped = res.animals
    base = "https://www.city.saitama.lg.jp/008/004/003/004/p003138_d/img/"
    assert _pick(flat, "shelter_date", "location", "breed", "color", "sex", "size", "age", "note", "image_url") == {
        "shelter_date": "令和8年9月26日", "location": "浦和区三崎", "breed": "パピヨン系雑種", "color": "トライカラー(黒、茶、白)",
        "sex": "オス", "size": "小型", "age": "7-9歳", "note": "なし", "image_url": base + "292_s.jpg"}
    assert _pick(wrapped, "shelter_date", "location", "breed", "sex", "image_url") == {
        "shelter_date": "令和8年9月29日", "location": "岩槻区高曽根", "breed": "雑種", "sex": "オス", "image_url": base + "295_s.jpg"}
    # 空の雛形（管理番号 R08-）は row_filter で捨てる。バナー（動物愛護ふれあいセンター）は行にならない
    assert res.dropped == []


# --- 千葉市 市民保護猫: h2 掲載日 → h4 番号 → p 写真（無い子が多い）→ p 保護日： … ----------------------------------
def test_chiba_5_groups_after_each_h4_until_the_next_h2_or_h4():
    res = _run("city_chiba-5", _fixture("t517_chiba-5.html"))
    assert [a["management_no"] for a in res.animals] == ["A-6035", "A-6028", "A-6027"]   # 先頭の注意書きの h4 は動物ではない
    a35, a28, a27 = res.animals
    assert _pick(a35, "shelter_date", "location", "breed", "color", "sex", "size", "note") == {
        "shelter_date": "令和8年9月24日", "location": "若葉区北谷津町", "breed": "ペルシャ?", "color": "白地にシルバー",
        "sex": "不明", "size": "中", "note": "長毛、尾長"}
    assert a35["image_url"].endswith("/dobutsuhogo/images/6035.jpg")
    assert a28["image_url"] is None and a27["image_url"] is None          # 写真の無い子に別の子の写真を付けない
    assert a28["note"] == "短毛、尾長、病院で「茶トラ、5歳以上、10歳以上の可能性もあり。」と言われた。"   # 空白を含む特徴を途中で切らない
    assert _pick(a27, "shelter_date", "location", "sex", "size") == {"shelter_date": "令和8年9月5日", "location": "稲毛区", "sex": "メス", "size": "小"}


# --- 長野県 譲渡猫: h3 番号 → p 写真 → p 種類 → p 性別 → p 生年月 → p 備考 --------------------------------------
def test_nagano_hello_animal_2_reads_label_paragraphs_after_h3():
    res = _run("nagano_hello_animal-2", _fixture("t517_nagano_hello_animal-2.html"))
    assert [a["management_no"] for a in res.animals] == ["2026-304", "2026-301"]
    first, second = res.animals
    assert _pick(first, "breed", "sex", "age") == {"breed": "ミックス(白灰)", "sex": "オス(去勢済み)", "age": "2024年7月頃生まれ"}
    assert first["image_url"].endswith("/inu-neko/images/304.jpg") and second["image_url"].endswith("/inu-neko/images/2026301.jpg")
    assert first["note"].startswith("右後ろ足のケガで長期治療") and "人馴れ練習中" not in first["note"]
    assert second["note"] == "慎重な性格で、人馴れ練習中です。"


# --- 川崎市 その他動物: h3「=====」の div → 写真 div ×2 → 表の div。写真が表の外 ----------------------------------
def test_kawasaki_3_takes_photos_outside_the_table():
    res = _run("city_kawasaki-3", _fixture("t517_kawasaki-3.html"))
    assert [a["management_no"] for a in res.animals] == ["R8-161", "R8-162"]     # 末尾の区切りだけの塊は動物にならない
    a, b = res.animals
    base = "https://www.city.kawasaki.jp/350/cmsfiles/contents/0000074/74729/"
    assert a["image_url"] == base + "1.jpg" and b["image_url"] == base + "1000006580.jpg"
    assert _pick(a, "breed", "color", "sex", "location", "shelter_date", "species") == {
        "breed": "オカメインコ", "color": "黄・灰・橙", "sex": "不明", "location": "幸区中幸町", "shelter_date": "2026年9月24日", "species": "other"}
    assert b["breed"] == "キンカチョウ" and b["shelter_date"] == "2026年9月27日"
    assert res.dropped == []


# --- 川崎市 収容犬: 今日は 0 頭。-3 と同じ CMS なので同じ作り（区切り → 写真 → 表。写真が表の後ろにある子もいる）---------------
KAWASAKI_1_MODEL = """<div class="main_naka_kiji"><div class="mol_contents">
<div id="index-1-1"><h2>犬の収容（保護）情報</h2></div>
<div id="index-2-3"><h3>=========</h3></div>
<div class="mol_imageblock"><div><img alt="写真1" src="../cmsfiles/contents/0000077/77270/a1.jpg"></div></div>
<div class="mol_imageblock"><div><img alt="写真2" src="../cmsfiles/contents/0000077/77270/a2.jpg"></div></div>
<div class="mol_tableblock"><table class="px550"><caption>R8-170</caption><tr><th>管理番号</th><td>R8-170</td><th>収容場所</th><td>多摩区</td></tr>
<tr><th>収容日</th><td>2026年10月1日</td><th>公開期限</th><td>2026年10月8日</td></tr>
<tr><th>種類</th><td>柴犬</td><th>毛色</th><td>茶</td></tr><tr><th>性別</th><td>オス</td><th>備考</th><td></td></tr></table></div>
<div id="index-2-8"><h3>=========</h3></div>
<div class="mol_tableblock"><table class="px550"><caption>R8-171</caption><tr><th>管理番号</th><td>R8-171</td><th>収容場所</th><td>宮前区</td></tr>
<tr><th>収容日</th><td>2026年10月2日</td><th>公開期限</th><td>2026年10月9日</td></tr>
<tr><th>種類</th><td>雑種</td><th>毛色</th><td>白</td></tr><tr><th>性別</th><td>メス</td><th>備考</th><td></td></tr></table></div>
<div class="mol_imageblock"><div><img alt="写真" src="../cmsfiles/contents/0000077/77270/b1.jpg"></div></div>
<div id="index-2-9"><h3>=========</h3></div>
<div class="mol_tableblock"><table class="px550"><caption>R8-172</caption><tr><th>管理番号</th><td>R8-172</td><th>収容場所</th><td>高津区</td></tr>
<tr><th>収容日</th><td>2026年10月3日</td><th>公開期限</th><td></td></tr>
<tr><th>種類</th><td>雑種</td><th>毛色</th><td>黒</td></tr><tr><th>性別</th><td>オス</td><th>備考</th><td>収容後死亡</td></tr></table></div>
<div id="index-2-10"><h3>=========</h3></div>
</div></div>"""


def test_kawasaki_1_model_page_photos_before_and_after_the_table():
    res = _run("city_kawasaki-1", KAWASAKI_1_MODEL)
    assert [a["management_no"] for a in res.animals] == ["R8-170", "R8-171"]     # 死亡の子（R8-172）は今までどおり捨てる
    first, second = res.animals
    base = "https://www.city.kawasaki.jp/350/cmsfiles/contents/0000077/77270/"
    assert first["image_url"] == base + "a1.jpg"
    assert second["image_url"] == base + "b1.jpg"        # 表の後ろの写真もその子のもの（次の子に取られない）
    assert _pick(first, "breed", "color", "sex", "location", "species") == {"breed": "柴犬", "color": "茶", "sex": "オス", "location": "多摩区", "species": "dog"}


def test_kawasaki_1_empty_page_is_still_confirmed_empty():
    html = """<div class="main_naka_kiji"><div class="mol_contents"><h2>犬の収容（保護）情報</h2>
<div class="mol_textblock"><p>現在、収容（保護）されている犬はいません。</p></div></div></div>"""
    res = _run("city_kawasaki-1", html)
    assert res.animals == [] and res.empty_confirmed is True
