"""T519 検証 G2（秋田市・秋田県・山形市・宮城県・わんにゃんむすび宮城・福島市）のレシピのテスト（ネットワークなし）。

今日（2026-10-07）の保存と、Wayback Machine の別の日の作りの保存を当てる。2026-10-08 の検証で見つかった、
別の日の作りで項目が空になる・別の列の値が入る・動物の行が読めない・0 頭の文言が違うものを直した。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(slug: str, fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _by(res, key="management_no"):
    return {a[key]: a for a in res.animals}


# --- 秋田市 収容中の犬猫（city_akita-1） ------------------------------------------------------------
def test_akita1_today_dog_and_empty_cat_table():
    res = _run("city_akita-1", "t519v_g2_city_akita-1_today.html")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["management_no"], a["species"], a["breed"], a["sex"], a["age"], a["color"], a["size"]) == (
        "3", "dog", "秋田犬", "オス", "推定2歳", "茶白", "大")
    assert a["shelter_date"] == "9月20日" and a["location"] == "上北手古野字四枚田"


def test_akita1_cat_and_dog_in_old_layouts():
    cat = _run("city_akita-1", "t519v_g2_city_akita-1_wb20221202.html").animals
    assert len(cat) == 1 and cat[0]["species"] == "cat" and cat[0]["breed"] == "雑種" and cat[0]["sex"] == "メス"
    assert (cat[0]["shelter_date"], cat[0]["location"], cat[0]["color"], cat[0]["size"]) == ("12月1日", "山王中島町", "黒白", "中型")
    dog = _run("city_akita-1", "t519v_g2_city_akita-1_wb20251015.html").animals
    assert len(dog) == 1 and dog[0]["management_no"] == "3" and dog[0]["image_url"].endswith("/3-1.jpg")
    # 2020 年は「捕獲日時」（月日ではない）
    old = _run("city_akita-1", "t519v_g2_city_akita-1_wb20200518.html").animals
    assert len(old) == 1 and old[0]["shelter_date"] == "5月18日" and old[0]["location"] == "千秋明徳町"


def test_akita1_zero_day_texts():
    res = _run("city_akita-1", "t519v_g2_city_akita-1_wb20260508.html")
    assert res.animals == [] and res.empty_confirmed


# --- 秋田市 飼い主が探している迷子（city_akita-2） --------------------------------------------------
def test_akita2_today():
    res = _run("city_akita-2", "t519v_g2_city_akita-2_today.html")
    assert len(res.animals) == 7
    a = _by(res)
    assert a["R8-34"]["image_url"].endswith("/r08-34.jpeg") and a["R8-34"]["color"] == "白(白キジ)"
    assert a["R8-2"]["species"] == "dog" and a["R8-2"]["breed"] == "雑種(柴犬系)" and a["R8-2"]["age"] == "15歳"


def test_akita2_label_variants_do_not_leak_row_text():
    res = _run("city_akita-2", "t519v_g2_city_akita-2_wb20221202.html")
    a = _by(res)
    assert len(a) == 9 and a["R4-5"]["name"] == "ユカ" and a["R4-5"]["breed"] == "柴犬" and a["R4-5"]["size"] == "小型"
    assert a["R4-58"]["color"] == "白黒のキジトラで背中がボールのように丸く白い" and a["R4-58"]["size"] == "大型"
    res = _run("city_akita-2", "t519v_g2_city_akita-2_wb20251112.html")
    assert len(res.animals) == 9
    assert all(not (v or "").startswith("届出番号") for a in res.animals for v in a.values() if isinstance(v, str))


# --- 秋田市 市民が保護している犬猫（city_akita-3） ---------------------------------------------------
def test_akita3_today():
    res = _run("city_akita-3", "t519v_g2_city_akita-3_today.html")
    a = _by(res)
    assert len(a) == 5 and a["R8-9"]["size"] == "小型" and a["R8-9"]["color"] == "黒(四肢白、腹白)"
    assert a["R8-6"]["size"] == "大型(5kgくらい)" and a["R8-6"]["color"] == "キジ白" and a["R8-6"]["age"] == "推定3歳"
    assert a["R8-4"]["breed"] == "雑種" and a["R8-4"]["sex"] == "オス" and a["R8-4"]["note"] == "怪我あり(右目、背中)"


def test_akita3_old_layouts_read_by_label():
    a = _by(_run("city_akita-3", "t519v_g2_city_akita-3_wb20220626.html"))
    assert len(a) == 7
    assert (a["R4-1"]["breed"], a["R4-1"]["sex"], a["R4-1"]["age"], a["R4-1"]["size"], a["R4-1"]["color"]) == (
        "雑種", "オス", "3歳", "中", "グレー・茶")
    a = _by(_run("city_akita-3", "t519v_g2_city_akita-3_wb20251114.html"))
    assert len(a) == 5
    assert (a["R7-2"]["sex"], a["R7-2"]["age"], a["R7-2"]["size"], a["R7-2"]["color"]) == ("メス", "推定7から8歳位", "中", "白、薄茶")
    assert (a["R7-7"]["size"], a["R7-7"]["color"]) == ("小さい", "さば白")


def test_akita3_dog_zero_text_alone_is_not_zero():
    # 犬の「保護されている犬の情報はありません」は猫がいる日にも出る。猫の表が読めなくなった日を 0 頭にしない
    src_html = (FIX / "t519v_g2_city_akita-3_today.html").read_text(encoding="utf-8")
    broken = src_html.replace("<h3>", "<h4>").replace("</h3>", "</h4>")
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "city_akita-3")
    res = build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=broken, soup=BeautifulSoup(broken, "lxml"))])
    assert res.animals == [] and not res.empty_confirmed


# --- 宮城県 動物愛護センター（pref_miyagi-1） --------------------------------------------------------
def test_miyagi1_today_empty():
    res = _run("pref_miyagi-1", "t519v_g2_pref_miyagi-1_today.html")
    assert res.animals == [] and res.empty_confirmed


# --- 仙南保健所（pref_miyagi-2） --------------------------------------------------------------------
def test_miyagi2_today_dog():
    res = _run("pref_miyagi-2", "t519v_g2_pref_miyagi-2_today.html")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["breed"], a["color"], a["sex"], a["size"], a["location"]) == (
        "dog", "雑種", "白(薄茶)", "オス", "中型", "柴田町松ケ越1丁目")


def test_miyagi2_cat_rows_and_dead_cat_not_listed():
    res = _run("pref_miyagi-2", "t519v_g2_pref_miyagi-2_wb20220529.html")
    assert len(res.animals) == 4 and sum(a["species"] == "cat" for a in res.animals) == 3
    assert not any("死亡" in (a["note"] or "") for a in res.animals)


def test_miyagi2_2021_columns_and_zero_day_with_fullwidth_comma():
    res = _run("pref_miyagi-2", "t519v_g2_pref_miyagi-2_wb20210118.html")
    dog, cat = res.animals
    assert (dog["breed"], dog["color"], dog["sex"], dog["size"]) == ("秋田犬", "白(薄茶)", "オス", "大型")
    assert dog["image_url"].endswith("/676153.JPG") and (cat["species"], cat["breed"], cat["note"]) == ("cat", "雑種", "衰弱")
    res = _run("pref_miyagi-2", "t519v_g2_pref_miyagi-2_wb20210412.html")
    assert res.animals == [] and res.empty_confirmed


# --- 岩沼支所（pref_miyagi-3） ----------------------------------------------------------------------
def test_miyagi3_today_empty():
    res = _run("pref_miyagi-3", "t519v_g2_pref_miyagi-3_today.html")
    assert res.animals == [] and res.empty_confirmed


def test_miyagi3_animal_row_written_in_th_cells():
    res = _run("pref_miyagi-3", "t519v_g2_pref_miyagi-3_wb20221012.html")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["management_no"], a["breed"], a["sex"], a["color"], a["shelter_date"]) == (
        "dog", "ID16306", "ハスキー系", "オス", "白黒", "令和4年10月11日")
    assert a["note"] == "赤色の首輪,切れたワイヤー。脱毛あり,高齢" and a["image_url"].endswith("/dsc_0243.jpg")


def test_miyagi3_dead_cat_not_listed_in_old_layout():
    res = _run("pref_miyagi-3", "t519v_g2_pref_miyagi-3_wb20221001.html")
    assert "ID16212" not in {a["management_no"] for a in res.animals} and len(res.animals) == 3


# --- 大崎保健所（pref_miyagi-4） --------------------------------------------------------------------
def test_miyagi4_today_three_dogs():
    res = _run("pref_miyagi-4", "t519v_g2_pref_miyagi-4_today.html")
    assert [a["management_no"] for a in res.animals] == ["1", "2", "3"]
    assert [a["species"] for a in res.animals] == ["dog", None, "dog"]


def test_miyagi4_dog_row_in_th_cells_and_cat_rows():
    res = _run("pref_miyagi-4", "t519v_g2_pref_miyagi-4_wb20220927.html")
    assert len(res.animals) == 1 and res.animals[0]["breed"] == "ミニチュアダックス" and res.animals[0]["species"] == "dog"
    res = _run("pref_miyagi-4", "t519v_g2_pref_miyagi-4_wb20240413.html")
    assert len(res.animals) == 3 and res.animals[0]["species"] == "cat"


def test_miyagi4_zero_day_wording_without_comma():
    res = _run("pref_miyagi-4", "t519v_g2_pref_miyagi-4_wb20240222.html")
    assert res.animals == [] and res.empty_confirmed


# --- 石巻保健所（pref_miyagi-5） --------------------------------------------------------------------
def test_miyagi5_today_joins_split_paragraphs():
    res = _run("pref_miyagi-5", "t519v_g2_pref_miyagi-5_today.html")
    assert len(res.animals) == 2
    a, b = res.animals
    assert (a["shelter_date"], a["location"]) == ("9月24日", "石巻市広渕字女形")
    assert (b["shelter_date"], b["location"]) == ("10月5日", "登米市登米町小島西針田")
    assert (b["breed"], b["color"], b["sex"], b["size"]) == ("雑種", "白薄茶", "メス", "小")


def test_miyagi5_old_layouts():
    res = _run("pref_miyagi-5", "t519v_g2_pref_miyagi-5_wb20221109.html")
    assert len(res.animals) == 1 and res.animals[0]["location"] == "東松島市赤井字川前二番"
    res = _run("pref_miyagi-5", "t519v_g2_pref_miyagi-5_wb20211019.html")
    assert res.animals == [] and res.empty_confirmed


# --- 山形市 譲渡対象（city_yamagata-2） --------------------------------------------------------------
def test_yamagata2_today():
    res = _run("city_yamagata-2", "t519v_g2_city_yamagata-2_today.html")
    assert len(res.animals) == 13 and {a["species"] for a in res.animals} == {"cat"}
    by = {a["name"]: a for a in res.animals}
    assert by["ひとみ"]["note"] == "不妊済" and by["ぎんた"]["note"] is None


def test_yamagata2_old_two_column_layout_and_trial_mark():
    res = _run("city_yamagata-2", "t519v_g2_city_yamagata-2_wb20241111.html")
    assert len(res.animals) == 16 and "ふみや" in {a["name"] for a in res.animals}
    res = _run("city_yamagata-2", "t519v_g2_city_yamagata-2_wb20260511.html")
    by = {a["name"]: a for a in res.animals}
    assert len(by) == 9 and by["たろ"]["note"] == "トライアル中。去勢済" and by["けぃ"]["note"] == "トライアル中。不妊済"
    assert by["チョコ"]["note"] == "去勢済"


# --- 石巻 管理番号（pref_miyagi-5）。p が割れても ID がつながる -----------------------------------------
def test_miyagi5_management_no_joins_split_id():
    res = _run("pref_miyagi-5", "t519v_g2_pref_miyagi-5_today.html")
    assert [a["management_no"] for a in res.animals] == ["ID13359", "ID13392"]
    assert [a["management_no"] for a in _run("pref_miyagi-5", "t519v_g2_pref_miyagi-5_wb20221109.html").animals] == ["ID16338"]


# --- 気仙沼保健所（pref_miyagi-6） -------------------------------------------------------------------
def test_miyagi6_today_and_slash_dates_and_zero_day_with_fullwidth_comma():
    res = _run("pref_miyagi-6", "t519v_g2_pref_miyagi-6_today.html")
    assert [a["species"] for a in res.animals] == ["dog", "cat", "cat"] and res.animals[0]["shelter_date"] == "9月2日"
    res = _run("pref_miyagi-6", "t519v_g2_pref_miyagi-6_wb20221001.html")
    assert len(res.animals) == 1 and res.animals[0]["shelter_date"] == "9/26" and res.animals[0]["species"] == "cat"
    res = _run("pref_miyagi-6", "t519v_g2_pref_miyagi-6_wb20220524.html")
    assert res.animals == [] and res.empty_confirmed


# --- みやぎわんにゃん家族むすび（wannyan_musubi_miyagi-1・2） ----------------------------------------
def test_wannyan_musubi_cats_exclude_center_and_keep_health_center_cards():
    res = _run("wannyan_musubi_miyagi-1", "t519v_g2_wannyan_musubi_miyagi-1_today.html")
    assert len(res.animals) == 16 and {a["species"] for a in res.animals} == {"cat"}
    assert res.animals[0]["location"] == "石巻保健所" and res.animals[0]["source_url"].endswith("/animal/399")
    # 絞り込み前の一覧（Wayback 2026-06-07）でも、センターの子は除かれ、保健所の子と個人・団体の投稿は同じ作りで読める
    res = _run("wannyan_musubi_miyagi-1", "t519v_g2_wannyan_musubi_miyagi-1_wb20260607all.html")
    assert len(res.animals) == 9 and not any("センタ" in (a["location"] or "") for a in res.animals)


def test_wannyan_musubi_dogs_all_center_is_zero():
    res = _run("wannyan_musubi_miyagi-2", "t519v_g2_wannyan_musubi_miyagi-2_today.html")
    assert res.animals == [] and res.empty_confirmed


# --- 福島市 迷子（保護）の犬猫（city_fukushima-2。link_only から recipe に変えた分） ------------------------
def _fukushima2(fixture: str):
    from collector.registry import Source
    src = Source(slug="city_fukushima-2", name="福島市保健所（迷子（保護）の犬猫）", municipality="福島市保健所", prefecture="福島県",
                 url="https://www.city.fukushima.fukushima.jp/soshiki/9/1046/3/1933.html", kind="stray", species="mixed",
                 mode="recipe", recipe="recipes/city_fukushima-2.yaml")
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_fukushima2_dog_table_on_an_animal_day():
    res = _fukushima2("t519v_g2_city_fukushima-2_wb20250730.html")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["management_no"], a["breed"], a["age"], a["color"], a["sex"], a["size"], a["location"]) == (
        "dog", "R7いー3", "ミックス", "9才", "黒", "めす", "中", "岡部字大蔵")
    assert a["image_url"].endswith("/20250624_153706.jpg") and a["shelter_date"].startswith("令和7年6月24日")


def test_fukushima2_zero_day_is_confirmed_by_having_no_table_but_not_by_wording():
    res = _fukushima2("t519v_g2_city_fukushima-2_today.html")
    assert res.animals == [] and res.empty_confirmed
    # 表が現れたのに行が読めなかった日（作りが変わった日）は 0 頭にしない
    html = (FIX / "t519v_g2_city_fukushima-2_wb20250730.html").read_text(encoding="utf-8").replace("<caption>", "<caption data-x=''>")
    changed = html.replace("捕獲月日", "xx").replace("<table", "<div").replace("</table>", "</div>")
    from collector.registry import Source
    src = Source(slug="city_fukushima-2", name="x", municipality="x", prefecture="福島県", url="https://x.jp/", kind="stray",
                 species="mixed", mode="recipe", recipe="recipes/city_fukushima-2.yaml")
    res = build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=changed, soup=BeautifulSoup(changed, "lxml"))])
    assert res.animals == [] and not res.empty_confirmed


# --- 宮城県 動物愛護センター 譲渡猫（pref_miyagi-7）の見出しの違い -------------------------------------
def test_miyagi7_h3_headings_in_2022_and_typo_heading_in_2026():
    res = _run("pref_miyagi-7", "t519v_g2_pref_miyagi-7_wb20221004.html")
    assert len(res.animals) == 16 and res.animals[0]["management_no"] == "15566" and res.animals[0]["name"] == "ザクロ"
    assert res.animals[0]["sex"] == "メス" and res.animals[0]["age"] == "推定3歳" and res.animals[0]["image_url"].endswith("/img_0352.jpg")
    res = _run("pref_miyagi-7", "t519v_g2_pref_miyagi-7_wb20260211.html")
    assert len(res.animals) == 32
    assert next(a for a in res.animals if a["name"] == "あや")["management_no"] == "12515"


def test_miyagi8_h3_headings_in_2023_and_zero_day_in_2021():
    res = _run("pref_miyagi-8", "t519v_g2_pref_miyagi-8_wb20230325.html")
    assert len(res.animals) == 4 and res.animals[0]["management_no"] == "16341" and res.animals[0]["name"] == "ムック"
    res = _run("pref_miyagi-8", "t519v_g2_pref_miyagi-8_wb20211025.html")
    assert res.animals == [] and res.empty_confirmed


# --- 宮城県 動物愛護センター 譲渡（pref_miyagi-7・8）、福島市 里親募集（city_fukushima-1）------------------
def test_miyagi7_8_and_fukushima1_today_counts():
    res = _run("pref_miyagi-7", "t519v_g2_pref_miyagi-7_today.html")
    assert len(res.animals) == 15 and res.animals[0]["management_no"] == "12915" and res.animals[0]["name"] == "トチ"
    assert len(_run("pref_miyagi-8", "t519v_g2_pref_miyagi-8_today.html").animals) == 2
    res = _run("city_fukushima-1", "t519v_g2_city_fukushima-1_today.html")
    assert len(res.animals) == 10 and res.animals[0]["management_no"] == "R7ねー35" and res.animals[0]["species"] == "cat"
