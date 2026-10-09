"""T519 検証（G7: 鳥取市・呉市・下関市・大分県）で直したレシピの確認。fixture は Wayback の保存ページ（日付はファイル名・テスト内）と 2026-10-07 の本文。

- 鳥取市 -2: トライアル中の子も載せる／【譲渡決定】は捨てる／種類・年齢・性別の読み／管理番号がまだ無い子を黙って捨てない
- 下関市 -3: 保護犬の個体ページ（項目名の後にコロンが無い）／-1・-2: 決まった子（飼い主が決まりました）を捨てる・空白を含む年齢
- 大分県 -3: 「保護日時」の語・市の名前だけが入った空の雛形を 0 頭とする
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str):
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _doc(slug: str, html: str) -> Doc:
    return Doc(url=_source(slug).url, html=html, soup=BeautifulSoup(html, "lxml"))


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _build(slug: str, *htmls: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(_source(slug), recipe, [_doc(slug, h) for h in htmls])


# --- 鳥取市 -2 -----------------------------------------------------------------------------------
def test_tottori_2_today_lists_trial_animals_and_reads_every_row():
    # 2026-10-07 の実ページ: 犬 5 + 猫 13 = 18 頭（トライアル中 6 頭を含む）。空の行 1 つだけ捨てる
    res = _build("city_tottori-2", _fixture("t519v_g7_tottori-2_20261007.html"))
    assert len(res.animals) == 18
    by = {a["name"]: a for a in res.animals}
    assert {"アル", "らん", "ひばり", "みつなり", "てれさ", "うめこ"} <= set(by)   # トライアル中の子も載せる
    assert {"ねね", "べんけい"} <= set(by)                                       # 治療のため募集一時停止
    assert by["みゃー"]["breed"] == "雑種" and by["みゃー"]["species"] == "cat"    # 状態の p が無い子
    assert by["すー"]["breed"] is None                                            # 種類の p が無い猫の名前や管理番号を種類にしない
    assert by["ガンジー"]["breed"] == "ミックス (M・ダックス×T・プードル)"
    assert by["チビ"]["management_no"].startswith("R7") and by["チビ"]["age"] == "18歳" and by["チビ"]["species"] == "dog"
    assert all(a["image_url"] for a in res.animals)
    assert len(res.dropped) == 1


def test_tottori_2_adoption_decided_is_dropped_and_age_label_variant_is_read():
    # 2026-07-01 の保存: 【譲渡決定】のチェリーは載せない。年齢の項目名が「年齢」（推定が付かない）の版
    res = _build("city_tottori-2", _fixture("t519v_g7_tottori-2_20260701.html"))
    by = {a["name"]: a for a in res.animals}
    assert "チェリー" not in by
    assert by["りょうま"]["age"] == "1歳" and by["りょうま"]["breed"] == "チワワ×T.プードルのミックス犬"
    assert by["つぶ"]["breed"] is None and by["つぶ"]["species"] == "cat"
    assert by["ラクサ"]["sex"] == "オス"   # 値の末尾の零幅空白を付けない


def test_tottori_2_row_without_management_no_is_not_silently_dropped():
    # 2026-03-25 の版は列の作りが違い（8 列）、管理番号がまだ無い「【New!】トイ・プードル」がいた。以前は管理番号が無いと黙って捨てていた
    res = _build("city_tottori-2", _fixture("t519v_g7_tottori-2_20260325.html"))
    assert any(a["image_url"] and a["image_url"].endswith("11967.jpg") for a in res.animals)


def test_tottori_2_zero_day_with_only_blank_rows_is_zero_not_failed():
    html = ('<div class="detail_free"><table><thead><tr><th>種類</th><th>特徴</th><th>その他</th></tr>'
            '<tr><td>\xa0</td><td>\xa0</td><td>\u200b</td></tr></thead></table></div>')
    res = _build("city_tottori-2", html)
    assert res.animals == [] and res.empty_confirmed


# --- 下関市 --------------------------------------------------------------------------------------
def test_shimonoseki_3_stray_dog_page_without_colons_is_read():
    # 保護犬の個体ページ（Wayback 2025-08-22）は「種類　　　秋田犬系」「保護（捕獲）日　　令和7年（2025年）4月28日」のようにコロンが無い
    res = _build("city_shimonoseki-3", _fixture("t519v_g7_shimonoseki-3_stray_item.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert {k: a.get(k) for k in ("species", "management_no", "breed", "sex", "color", "size", "shelter_date", "location", "note")} == {
        "species": "dog", "management_no": "07-03", "breed": "秋田犬系", "sex": "メス", "color": "茶", "size": "大型",
        "shelter_date": "令和7年(2025年)4月28日", "location": "松屋東町2丁目", "note": "首輪無し"}
    assert a["image_url"].endswith("/64260.JPG")


def test_shimonoseki_1_decided_dog_is_dropped_and_all_decided_is_zero():
    for name in ("t519v_g7_shimonoseki-1_decided_item.html",):
        res = _build("city_shimonoseki-1", _fixture(name))
        assert res.animals == []
        assert res.empty_confirmed   # 捨てた数 = 行数（一覧にはまだ載っているが、決まった子しかいない日）


def test_shimonoseki_1_dog_item_fields():
    res = _build("city_shimonoseki-1", _fixture("t519v_g7_shimonoseki-1_age_only_item.html"))
    a = res.animals[0]
    # 「年齢：若齢」（推定が付かない）。性別に次の項目が混ざらない
    assert (a["name"], a["sex"], a["age"], a["management_no"]) == ("かんたろう", "オス", "若齢", "R05-12")
    res = _build("city_shimonoseki-1", _fixture("t519v_g7_shimonoseki-1_age_space_item.html"))
    a = res.animals[0]
    assert a["age"] and "推定" in a["age"] and a["name"] == "チョコ"   # 「不明(推定 中~高齢)」のように空白を含む年齢を途中で切らない
    assert "\u200b" not in a["name"]


# --- 大分県 -3 -----------------------------------------------------------------------------------
def test_oita_3_dog_listed_with_hogo_nichiji_label_and_placeholder_city_is_zero():
    res = _build("pref_oita-3", _fixture("t519v_g7_oita-3_with_dog.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["shelter_date"], a["location"], a["breed"]) == ("dog", "令和7年1月22日", "豊後高田市松行", "雑種")
    # 空の雛形の保護場所に市の名前だけが入っている日（Wayback 2023-02-01）は、動物がいないので 0 頭
    res = _build("pref_oita-3", _fixture("t519v_g7_oita-3_placeholder_city.html"))
    assert res.animals == [] and res.empty_confirmed


# --- 呉市 迷い犬・猫（-2。link_only から recipe にした） -------------------------------------------
def _build_kure2(html: str):
    import dataclasses

    src = dataclasses.replace(_source("city_kure-2"), kind="stray", mode="recipe", recipe="recipes/city_kure-2.yaml")
    recipe = Recipe.load(ROOT / "recipes" / "city_kure-2.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_kure_2_zero_day_is_confirmed_only_when_no_animal_block_and_no_photo():
    res = _build_kure2(_fixture("t519v_g7_kure-2_20261007_zero.html"))   # 2026-10-07 の実ページ（説明文だけ）
    assert res.animals == [] and res.empty_confirmed
    # 動物の見出しが無くても写真が載った日は 0 頭にしない（読めなかった扱い）
    html = _fixture("t519v_g7_kure-2_20261007_zero.html").replace("</div>", '<p><img src="/uploaded/image/1.jpg"/></p></div>')
    res = _build_kure2(html)
    assert res.animals == [] and not res.empty_confirmed


def test_kure_2_dogs_in_li_layout_2023_and_br_layout_2025():
    res = _build_kure2(_fixture("t519v_g7_kure-2_20230320_two_dogs.html"))   # Wayback 2023-03-20: 迷子犬１・２（ul の li）
    assert len(res.animals) == 2
    a, b = res.animals
    assert (a["species"], a["breed"], a["age"], a["sex"], a["color"], a["size"]) == ("dog", "日本犬", "5才位", "オス", "白", "中")
    assert a["note"].endswith("呉市広末広2丁目1-1付近で保護") and a["image_url"].endswith("/49168.JPG")
    assert (b["age"], b["color"]) == ("8才位", "黒茶白") and b["image_url"].endswith("/49266.JPG")
    res = _build_kure2(_fixture("t519v_g7_kure-2_20250222_one_dog.html"))   # Wayback 2025-02-22: 1 つの p の br 区切り
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["breed"], a["age"], a["sex"], a["color"], a["size"]) == ("dog", "日本犬", "5才", "オス", "茶", "中")
    assert a["image_url"].endswith("/61679.JPG") and "令和7年2月19日" in a["note"]


def test_kure_2_cat_heading_makes_a_cat():
    res = _build_kure2(_fixture("t519v_g7_kure-2_20221209_dogs_and_cat.html"))   # Wayback 2022-12-09: 迷子犬 2 頭 + 迷子猫 1 頭
    assert [a["species"] for a in res.animals] == ["dog", "dog", "cat"]
    cat = res.animals[2]
    assert (cat["breed"], cat["age"], cat["sex"], cat["color"], cat["size"]) == ("日本猫", "10歳位", "メス", "黒", "大")
    assert cat["image_url"].endswith("/47903.JPG")


# --- 大分県 -1・-2（返還済みの語・元号の元年） ----------------------------------------------------
def test_oita_1_all_returned_dogs_with_modoremashita_wording_are_zero():
    # Wayback 2017-04-20: 3 頭とも「飼い主のところへ戻れました」の表（返還済み）。保護中の表は空の雛形。以前は戻れた 3 頭を保護中として載せていた
    res = _build("pref_oita-1", _fixture("t519v_g7_oita-1_20170420_all_returned.html"))
    assert res.animals == [] and res.empty_confirmed


def test_oita_2_reiwa_gannen_date_keeps_the_era_and_year():
    # Wayback 2019-10-14: 保護日時「令和元年10月1日」。元年を数字でないと取りこぼして「10月1日」になっていた
    res = _build("pref_oita-2", _fixture("t519v_g7_oita-2_20191014_reiwa_gannen.html"))
    assert [(a["management_no"], a["shelter_date"]) for a in res.animals] == [("a-533", "令和元年10月1日")]


def test_oita_2_three_dogs_2022_12_read_with_number_and_date():
    res = _build("pref_oita-2", _fixture("t519v_g7_oita-2_20221212_three_dogs.html"))
    assert sorted(a["management_no"] for a in res.animals) == ["a-678", "a-680", "a-682"]
    by = {a["management_no"]: a for a in res.animals}
    assert (by["a-682"]["species"], by["a-682"]["breed"], by["a-682"]["shelter_date"], by["a-682"]["location"]) == ("dog", "トイプードル", "令和4年12月8日", "宇佐市四日市")
    assert all(a["image_url"] for a in res.animals)


def test_tottori_2_decided_after_another_bracket_is_still_dropped():
    # 【New!】【譲渡決定】のように状態の【】が 2 つ並ぶ子（status は最初の【】だけ取る）。決まった子は載せず、隣の募集中の子は載せる
    def row(status, mno, name, img):
        return (f'<tr><td><p>{status}</p><p>ミックス</p><p>{mno}</p><p>{name}</p><p><img src="/uploaded/image/{img}.jpg"/></p></td>'
                '<td><p>毛色：茶 性別：オス</p><p>推定年齢：2歳</p></td><td><p>よろしく</p></td></tr>')
    html = ('<div class="detail_free"><table><caption>【犬】表1</caption><thead><tr><th>種類</th><th>特徴</th><th>その他</th></tr></thead><tbody>'
            + row("<strong>【New!】</strong><strong>【譲渡決定】</strong>", "R8-TD30", "ごん", 1)
            + row("<strong>【里親募集中】</strong>", "R8-TD31", "もん", 2) + '</tbody></table></div>')
    res = _build("city_tottori-2", html)
    assert [a["name"] for a in res.animals] == ["もん"]


# --- 大分県 -2: 返還済みの言い方「飼い主へ返還されました」（T519 ゲート F-02） -------------------------------------
def test_oita_2_returned_animals_in_2020_layout_are_not_listed():
    # Wayback 2020-06-10: a-579・a-576・a-575 の表に「飼い主へ返還されました」。保護中として載せない
    res = _build("pref_oita-2", _fixture("t519v_g7_oita-2_20200610_returned.html"))
    assert {a["management_no"].replace(" ", "") for a in res.animals} == {"a-578", "a-577", "a-574"}
