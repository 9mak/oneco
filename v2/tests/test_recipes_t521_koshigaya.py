"""T521（2026-10-05）越谷市 保護犬・保護猫と、見出し行の表を読む指定 header_row のテスト（ネットワークなし）。

越谷の表は日によって作りが違う（Wayback で確認）:
- 2023-09: 見出し行を tbody の td で書く（label 読みは隣の見出し「収容期限」を収容日に取っていた）
- 2024-09・2025-03: 見出しは thead の th、値は tbody の td（label 読みは値が取れなかった）
- 2025-03 の猫: 動物ごとの h3 が無く、見出しが「収容期日」、動物の表の列順が 種類・性別・毛色・年齢（列の位置では読めない）
- 2026-10（今）: thead に見出しと値の 2 行
- 0 頭の日に番号「000」の空の雛形が残る（中身の無い 1 頭として載っていた）
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(slug: str, fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fields(a: dict) -> tuple:
    return tuple(a.get(k) for k in ("management_no", "shelter_date", "location", "breed", "sex", "age", "color", "size", "note"))


# --- 越谷市の作りごと ------------------------------------------------------------------------
def test_koshigaya_header_row_written_with_td_cells():
    res = _run("city_koshigaya-1", "t521_koshigaya-1_wb20230925.html")
    assert [_fields(a) for a in res.animals] == [
        ("011", "令和5年9月15日", "越谷市大字南荻島地内", "ミニチュア・ダックスフンド", "めす", "高齢", "茶", "小型", "首輪なし")]
    assert res.animals[0]["image_url"].endswith("/dog-011small.jpg")   # 写真が表の後ろにある作り


def test_koshigaya_header_in_thead_and_values_in_tbody():
    res = _run("city_koshigaya-1", "t521_koshigaya-1_wb20240920.html")
    assert [_fields(a) for a in res.animals] == [
        ("001", "令和6年9月2日", "越谷市野島地内", "トイ・プードル", "メス", "中齢", "茶", "中型", "首輪なし マイクロチップなし")]
    assert res.animals[0]["image_url"].endswith("/0902inudog01.jpg")


def test_koshigaya_zero_day_with_leftover_template_000_is_empty():
    res = _run("city_koshigaya-1", "t521_koshigaya-1_wb20250327.html")
    assert res.animals == [] and res.empty_confirmed


def test_koshigaya_without_h3_with_other_heading_word_and_column_order():
    res = _run("city_koshigaya-2", "t521_koshigaya-2_wb20250316.html")
    assert [_fields(a) for a in res.animals] == [
        (None, "令和7年3月13日", "越谷市七左町7丁目地内", "雑種", "おす", "中齢", "キジトラ", "中型", "長尾 短毛 首輪なし")]


def test_koshigaya_current_layout_two_rows_in_thead():
    res = _run("city_koshigaya-2", "t521_koshigaya-2_20261005.html")
    assert [_fields(a) for a in res.animals] == [
        ("R8-52", "令和8年10月2日", "越谷市大間野町3丁目地内", "雑種", "おす", "推定3週齢", "茶トラ", "小型", "長尾 短毛 首輪なし")]
    assert res.animals[0]["image_url"] is None   # 例示イラスト（youreidoubutu）は写真にしない


# --- さいたま市 保護猫（同じく Wayback で見つかったもの） -----------------------------------------------
def test_saitama_injured_placeholder_is_not_a_photo_and_ids_do_not_collide():
    # 負傷の 3 頭が同じ共通画像（「負傷動物のため写真の公開はありません」）。写真から ID を作ると衝突して 1 頭しか載らなかった
    res = _run("city_saitama-2", "t521_saitama-2_wb20240226.html")
    assert [a["management_no"] for a in res.animals] == ["R05-85", "R05-86", "R05-87"]
    assert all(a["image_url"] is None for a in res.animals)
    assert len({a["id"] for a in res.animals}) == 3


def test_saitama_template_only_day_is_empty():
    res = _run("city_saitama-2", "t521_saitama-2_wb20250209.html")   # 雛形カード「管理番号 R06-」だけ
    assert res.animals == [] and res.empty_confirmed


# --- 千葉県（雛形ブロックの番号が年度で変わる） -------------------------------------------------------
def test_chiba_template_block_of_another_year_is_not_an_animal():
    # 2025 年版の雛形「2500000ｰ01」は今年の番号の指定に当たらない。1 ブロックの左右の列に 2 頭（sa250827-01・ks250827-01）が並ぶ日でも両方を取る
    res = _run("pref_chiba-1", "t521_pref_chiba-1_wb20250831.html")
    assert sorted(a["management_no"] for a in res.animals) == ["ks250827-01", "kt250818-01", "sa250827-01", "sa250829-01"]
    assert not any(a.get("breed") == "種類" or a.get("color") == "毛色" for a in res.animals)


def test_nagano_breed_is_never_the_management_number():
    # T521 ゲート F-01: 長野 譲渡猫の Wayback 2023-03 は h3（管理番号）と写真・種類が別の div にあり、種類の欄が見つからない子で
    # regex が行の全文の先頭（管理番号）を品種にしていた
    res = _run("nagano_hello_animal-2", "t521_nagano-2_wb20230322.html")
    got = {a["management_no"]: (a["breed"], a["color"]) for a in res.animals}
    assert got["2022-316"] == ("ミックス", "キジ白、白多め") and got["2022-306"] == ("ミックス", "茶トラ白")
    assert all(b != m for m, (b, _) in got.items())
    assert got["2022-307"] == (None, None)   # 種類が別の div にある作り。誤った値は入れない（取れないのは以前からの制約）


def test_chiba_template_only_day_is_empty():
    res = _run("pref_chiba-2", "t521_pref_chiba-2_wb20250826.html")
    assert res.animals == [] and res.empty_confirmed


# --- header_row（見出し行の表）と label の候補 ----------------------------------------------------
def _src() -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="埼玉県", url="https://x.jp/a/", kind="sheltered", species="cat")


def _one(table_html: str, fields: dict) -> dict:
    html = f"<div class='row'>{table_html}</div>"
    r = Recipe.from_dict({"rows": "div.row", "fields": {"management_no": {"regex": r"(R\d-\d+)"}, **fields}})
    res = build(_src(), r, [Doc(url="https://x.jp/a/", html=html, soup=BeautifulSoup(html, "lxml"))])
    assert len(res.animals) == 1
    return res.animals[0]


SPLIT = ("<table><thead><tr><th>収容場所</th><th>収容日</th><th>収容期限</th></tr></thead>"
         "<tbody><tr><td>越谷市</td><td>令和8年10月2日</td><td>令和8年10月13日</td></tr></tbody></table><p>R8-52</p>")
TD_HEAD = ("<table><tbody><tr><td>収容場所</td><td>収容日</td><td>収容期限</td></tr>"
           "<tr><td>越谷市</td><td>令和8年10月2日</td><td>令和8年10月13日</td></tr></tbody></table><p>R8-52</p>")


def test_header_row_reads_the_next_row_across_thead_and_tbody():
    a = _one(SPLIT, {"location": {"label": "収容場所", "header_row": True}, "shelter_date": {"label": "収容日", "header_row": True}})
    assert (a["location"], a["shelter_date"]) == ("越谷市", "令和8年10月2日")


def test_header_row_does_not_take_the_neighbouring_heading_cell():
    a = _one(TD_HEAD, {"shelter_date": {"label": "収容日", "header_row": True}})
    assert a["shelter_date"] == "令和8年10月2日"


def test_label_list_tries_each_word_in_order():
    html = SPLIT.replace("<th>収容日</th>", "<th>収容期日</th>")
    a = _one(html, {"shelter_date": {"label": ["収容日", "収容期日"], "header_row": True}})
    assert a["shelter_date"] == "令和8年10月2日"


def test_header_row_needs_the_exact_heading_word():
    # 「収容日」は「収容期日」の部分ではない（見出しの語と完全に一致するセルだけを見出しとみなす）
    html = SPLIT.replace("<th>収容日</th>", "<th>収容期日</th>")
    a = _one(html, {"shelter_date": {"label": "収容日", "header_row": True}})
    assert a["shelter_date"] is None


def test_label_list_also_works_without_header_row():
    html = "<table><tr><th>保護日</th><td>10月2日</td></tr></table><p>R8-52</p>"
    a = _one(html, {"shelter_date": {"label": ["収容日", "保護日"]}})
    assert a["shelter_date"] == "10月2日"
