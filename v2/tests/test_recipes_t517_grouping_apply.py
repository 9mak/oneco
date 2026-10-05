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


# --- 川崎市 収容犬: row_until に切り替えない（2026-10-05 公開前レビュー F-01）---------------------------------------
# 犬が載っていた日の実ページ（Wayback 2019〜2022）は区切りの h3 が div.mol_contents の直下に並び、-3（猫・その他）のように
# 区切りを包む div が無い。-3 と同じ rows: "div.main_naka_kiji div:has(> h3)" にすると mol_contents 全体が 1 行になり、
# 2 頭目以降が消える。レシピは「表 1 つ = 1 頭」（写真なし）のまま。fixture は 2022-01-21 版に 2 頭目を複製したもの
def test_kawasaki_1_keeps_one_animal_per_table_on_the_real_markup():
    res = _run("city_kawasaki-1", _fixture("t517_kawasaki-1_wayback20220121_2dogs.html"))
    assert [a["management_no"] for a in res.animals] == ["R3-354", "R3-355"]


def test_kawasaki_1_empty_page_is_still_confirmed_empty():
    html = """<div class="main_naka_kiji"><div class="mol_contents"><h2>犬の収容（保護）情報</h2>
<div class="mol_textblock"><p>現在、収容（保護）されている犬はいません。</p></div></div></div>"""
    res = _run("city_kawasaki-1", html)
    assert res.animals == [] and res.empty_confirmed is True
