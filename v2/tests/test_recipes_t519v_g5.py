"""T519v G5（甲府・長野市・松本・岐阜市・静岡市・一宮・奈良県・姫路）: 前任の続きの確かめで直したレシピ（ネットワークなし）。

fixture は 2026-10-07・08 の保存 HTML と、Wayback Machine の保存版（日付はファイル名）。
"""

from dataclasses import replace
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


# 台帳（sources.yaml）に無い slug（city_matsumoto-6〜9）と、台帳がまだ link_only の slug（city_shizuoka-1・pref_nara-1〜3）は、台帳のブロックを入れる前でも
# このテストが通るよう、似た台帳エントリから組み立てる（台帳に入った後は台帳のものを使う）。
_FROM = {"city_matsumoto-6": "city_matsumoto-5", "city_matsumoto-7": "city_matsumoto-5", "city_matsumoto-8": "city_matsumoto-5",
         "city_matsumoto-9": "city_matsumoto-4", "city_shizuoka-1": "city_shizuoka-1",
         "pref_nara-1": "pref_nara-1", "pref_nara-2": "pref_nara-2", "pref_nara-3": "pref_nara-3"}


def _source(slug: str) -> Source:
    sources = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
    if slug in sources and sources[slug].mode == "recipe":
        return sources[slug]
    return replace(sources[_FROM[slug]], slug=slug, mode="recipe", recipe=f"recipes/{slug}.yaml")


def _run(slug: str, name: str, url: str | None = None):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    html = (FIX / name).read_text(encoding="utf-8")
    return build(src, recipe, [Doc(url=url or src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


MATSU_CAT = "t519v_g5_matsumoto5_today.html"


# --- 松本市 猫（1534）: 1 掲載に猫が複数並ぶ表を、列ごとに -5（1 頭目）・-6（2 頭目）・-7（3 頭目）・-8（4 頭目）で読む ---


def test_matsumoto_cats_today_ten_cats_over_five_listings():
    r5, r6, r7, r8 = (_run(f"city_matsumoto-{n}", MATSU_CAT) for n in (5, 6, 7, 8))
    assert [a["management_no"] for a in r5.animals] == ["8-8", "8-7", "8-5", "8-2", "8-1"]
    assert [a["management_no"] for a in r6.animals] == ["8-8", "8-5", "8-2", "8-1"]
    assert [a["management_no"] for a in r7.animals] == ["8-1"]
    # 5 掲載・10 頭（ページの「5 件・猫 10 頭」）。4 頭目の掲載は無い日は 0 頭で確定する（読めなかったにしない）
    assert r8.animals == [] and r8.empty_confirmed is True
    assert sum(len(r.animals) for r in (r5, r6, r7, r8)) == 10


def test_matsumoto_cat_columns_match_photos_and_items():
    # 8-8 は 2 頭（1 頭目: 白・メス・11 歳 / 2 頭目: キジトラ・オス・9 歳）。写真を見て、写真の並び順が列の順と同じことを確かめた
    first = next(a for a in _run("city_matsumoto-5", MATSU_CAT).animals if a["management_no"] == "8-8")
    second = next(a for a in _run("city_matsumoto-6", MATSU_CAT).animals if a["management_no"] == "8-8")
    assert (first["color"], first["sex"], first["age"]) == ("白", "メス", "11歳")
    assert first["image_url"].endswith("/uploaded/image/87085.jpeg")
    assert (second["color"], second["sex"], second["age"]) == ("キジトラ(灰茶)", "オス", "9歳")
    assert second["image_url"].endswith("/uploaded/image/87084.jpeg")
    # 8-1 は 3 頭（黒・オス / 黒白・オス / 白黒・メス）
    third = _run("city_matsumoto-7", MATSU_CAT).animals[0]
    assert (third["color"], third["sex"]) == ("白黒", "メス")
    assert third["image_url"].endswith("/uploaded/image/83994.JPG")
    assert all(a["species"] == "cat" for r in (5, 6, 7) for a in _run(f"city_matsumoto-{r}", MATSU_CAT).animals)


def test_matsumoto_cat_second_slug_has_no_personal_contact():
    for n in (5, 6, 7):
        for a in _run(f"city_matsumoto-{n}", MATSU_CAT).animals:
            blob = " ".join(str(v) for v in a.values() if v)
            assert "090-" not in blob and "連絡先" not in blob


def test_matsumoto_cat_photo_only_when_photo_count_equals_cat_count():
    # 2022-09 の保存版: 複数頭の掲載で写真の数と猫の数が違うものが約半分（2 頭に 1 枚・3 頭に 4 枚 等）。
    # 数が同じ掲載（4-19(2)・4-17 等）だけ列順の写真を付け、違う掲載（4-21・4-20・4-8・4-5）は誤った猫の写真を載せない
    html = "t519v_g5_matsumoto5_20220922.html"
    r6 = _run("city_matsumoto-6", html)
    by = {a["management_no"]: a for a in r6.animals}
    assert len(r6.animals) == 11
    for no in ("4-21", "4-20", "4-8", "4-5"):
        assert no in by and by[no].get("image_url") is None   # 写真が付かなくても動物として載る（掲載漏れにしない）
    for no in ("4-19(2)", "4-17", "4-15", "4-14", "4-12", "4-9"):
        assert by[no]["image_url"]
    # 4 頭並ぶ 4-14 は 4 つの slug が 1 頭ずつ読む
    assert [a["management_no"] for a in _run("city_matsumoto-8", html).animals] == ["4-14"]
    assert len(_run("city_matsumoto-7", html).animals) == 7
    assert len(_run("city_matsumoto-5", html).animals) == 13


def test_matsumoto_cat_total_equals_cats_in_tables_2022_04_and_09():
    # 2022-04 の版は表に「掲載日」が無く（以前は 0 頭で読めなかった）、表の見出し「猫の情報」で動物の表と決める。猫の合計 = 表の列数の合計
    for html, total in (("t519v_g5_matsumoto5_20220423.html", 49), ("t519v_g5_matsumoto5_20220922.html", 32)):
        got = sum(len(_run(f"city_matsumoto-{n}", html).animals) for n in (5, 6, 7, 8))
        assert got == total


# --- 松本市 犬（1529）: 犬が 2 頭並ぶ表（2024-10 の 6-1: 譲渡されました / 募集中です）と、譲渡済みの子 ---


def test_matsumoto_dog_sold_first_column_is_not_listed_and_second_is():
    html = "t519v_g5_matsumoto4_20241007.html"
    r4 = _run("city_matsumoto-4", html)
    assert [a["management_no"] for a in r4.animals] == ["6-4", "5-3"]
    assert all("譲渡されました" not in (a["breed"] or "") for a in r4.animals)
    r9 = _run("city_matsumoto-9", html)
    assert len(r9.animals) == 1
    a = r9.animals[0]
    assert (a["management_no"], a["sex"], a["age"], a["breed"]) == ("6-1", "メス", "10歳", "柴犬(中型犬)")
    assert a["image_url"] is None      # 犬 2 頭に写真 3 枚で、どの写真か決められない
    assert a["species"] == "dog"


def test_matsumoto_dog_second_slug_is_empty_when_no_two_dog_listing():
    for name in ("t519v_g5_matsumoto4_20240304.html", "t519v_g5_matsumoto4_20230202.html"):
        r9 = _run("city_matsumoto-9", name)
        assert r9.animals == [] and r9.empty_confirmed is True


def test_matsumoto_dog_individual_without_caption_date_and_multi_dog_listing():
    r = _run("city_matsumoto-4", "t519v_g5_matsumoto4_20240304.html")
    # 掲載日の無い保健所の犬 No.5-3 と、1 掲載にまとまる「5-2（7頭）」
    assert [a["management_no"][:3] for a in r.animals] == ["5-3", "5-2"]
    assert len(_run("city_matsumoto-4", "t519v_g5_matsumoto4_20230202.html").animals) == 4


# --- 松本市 逸走動物（1524）: 種別は個体の見出しの語で決める ---


def test_matsumoto_lost_species_from_the_animal_heading():
    r = _run("city_matsumoto-3", "t519v_g5_matsumoto3_20230601.html")
    got = {a["management_no"]: a["species"] for a in r.animals}
    # 犬 3・猫 3・鳥 1（逸走鳥No.4-1 は犬猫以外）。見出しに「掲載前削除」が付く逸走猫No.4-11 は載せない
    assert got == {"4-5": "dog", "4-4": "dog", "4-2": "dog", "5-2": "cat", "5-1": "cat", "4-10": "cat", "4-1": "other"}
    r2 = _run("city_matsumoto-3", "t519v_g5_matsumoto3_20240912.html")
    assert {a["management_no"]: a["species"] for a in r2.animals}["5-2"] == "other"     # 逸走動物No.5-2（オカメインコ）


def test_matsumoto_lost_other_animal_under_the_cat_section_is_not_a_cat():
    # 今の作りは「その他の逸走動物」が h4 で、直前の h3「逸走猫」の下に並ぶ。h3 で種別を決めると鳥が猫になる
    html = (FIX / "t519v_g5_matsumoto3_today.html").read_text(encoding="utf-8")
    start = html.index("<h4>　その他の逸走動物</h4>")
    bird = (
        "<h4>逸走鳥No.9-1</h4><p><img src=\"/uploaded/image/9.jpg\"></p><table><caption>掲載日：令和8年10月1日</caption>"
        "<tr><td>逸走日</td><td>令和8年9月30日</td></tr><tr><td>逸走場所</td><td>松本市</td></tr>"
        "<tr><td>種類</td><td>セキセイインコ</td></tr><tr><td>性別</td><td>オス</td></tr></table>"
    )
    src = _source("city_matsumoto-3")
    recipe = Recipe.load(ROOT / "recipes" / "city_matsumoto-3.yaml")
    doc_html = html[: start + len("<h4>　その他の逸走動物</h4>")] + bird + html[start + len("<h4>　その他の逸走動物</h4>"):]
    res = build(src, recipe, [Doc(url=src.url, html=doc_html, soup=BeautifulSoup(doc_html, "lxml"))])
    got = {a["management_no"]: a["species"] for a in res.animals}
    assert got["9-1"] == "other"
    assert [v for k, v in got.items() if k != "9-1"] == ["cat", "cat", "cat", "cat"]


# --- 奈良県: 新ドメイン www.pref.nara.lg.jp/n070/ で recipe に戻した ---


def test_nara_2_matching_dog_is_not_listed_and_a_dog_that_moved_down_is_dropped():
    # 2026-10-07: 2次募集中 3 頭（ジュノ・ドラ美・ズーマー）+ マッチング中のラッタッタ
    r = _run("pref_nara-2", "t519v_g5_pref_nara-2_20261007.html")
    assert [a["name"] for a in r.animals] == ["ジュノ", "ドラ美", "ズーマー"]
    # 2026-10-08: ジュノが「マッチング中」バナーの下（ラッタッタの次）に移った。バナーの下の犬は載せない
    r = _run("pref_nara-2", "t519v_g5_pref_nara-2_20261008.html")
    assert [a["name"] for a in r.animals] == ["ドラ美", "ズーマー"]
    assert all(a["species"] == "dog" and a["image_url"] and "jibosyu" not in a["image_url"] for a in r.animals)


def test_nara_3_and_1_on_the_new_domain():
    r = _run("pref_nara-3", "t519v_g5_pref_nara-3_20261008.html")
    assert [(a["name"], a["sex"]) for a in r.animals] == [("クコ", "♀"), ("ミルタス", "♂"), ("クレ", "♀")]
    r = _run("pref_nara-1", "t519v_g5_pref_nara-1_20261008.html")
    assert r.animals == [] and r.empty_confirmed is True


# --- 長野市: 見出しの階層が日によって違う（h2/h3 と h3/h4）。動物は「登録番号」の見出しで決める ---


def test_nagano_3_reads_every_animal_in_both_heading_layouts_with_species_of_the_section():
    for name, total, other in (("t519v_g5_nagano3_today.html", 22, 5), ("t519v_g5_nagano3_20241107.html", 23, 4)):
        r = _run("city_nagano-3", name)
        assert len(r.animals) == total
        assert sum(a["species"] == "other" for a in r.animals) == other     # 「その他」の節（インコ）は犬猫以外
        assert sum(a["species"] == "dog" for a in r.animals) in (1, 3)
        assert all(a["image_url"] for a in r.animals)
    r = _run("city_nagano-3", "t519v_g5_nagano3_today.html")
    a = next(x for x in r.animals if x["management_no"] == "8-9号")
    assert (a["species"], a["sex"], a["age"], a["size"]) == ("cat", "メス(不妊手術済み)", "4才", "見た目は大きい。体重は軽め。")   # 体格・体重が size に入る


def test_nagano_2_injured_cat_and_stray_dog_and_zero_days():
    a = _run("city_nagano-2", "t519v_g5_nagano2_20250909.html").animals
    assert [(x["management_no"], x["species"], x["breed"]) for x in a] == [("第7号", "dog", "ボーダーコリー")]   # 迷い犬は h3「迷い犬／第7号」の語で犬
    r = _run("city_nagano-2", "t519v_g5_nagano2_20250117_empty.html")
    assert r.animals == [] and r.empty_confirmed is True     # 「保健所で保護している迷い犬・負傷猫などはいません」


def test_nagano_4_zero_day_is_empty():
    r = _run("city_nagano-4", "t519v_g5_nagano4_20230607_empty.html")
    assert r.animals == [] and r.empty_confirmed is True


def test_nagano_7_zero_day_wordings_2023_06_2026_05_and_today():
    for name in ("t519v_g5_nagano7_20230607_empty.html", "t519v_g5_nagano7_20260512_empty.html", "t519v_g5_nagano7_today_empty.html"):
        r = _run("city_nagano-7", name)
        assert r.animals == [] and r.empty_confirmed is True, name


def test_nagano_1_reads_listings_with_several_animals_as_one_each():
    r = _run("city_nagano-1", "t519v_g5_nagano1_20250814.html")
    assert [a["management_no"] for a in r.animals][:2] == ["7-42号", "7-41号"]
    assert all(a["species"] == "cat" for a in r.animals) and len(r.animals) == 7      # 犬譲渡は 0 頭の日（猫譲渡の節の子は猫）
    assert r.animals[0]["breed"] == "雑種37頭"       # 掲載のとおり 1 件（写真は無い）


# --- 甲府市: 表の class（datatable）が付かない版・列の並びが変わる版 ---


def test_kofu_reads_both_tables_by_the_heading_not_by_the_table_class():
    r1 = _run("city_kofu-1", "t519v_g5_kofu_today.html")
    assert [a["management_no"] for a in r1.animals] == ["262059", "262058", "251083"]
    assert [(a["breed"], a["sex"]) for a in r1.animals][:2] == [("雑種", "オス"), ("雑種", "メス")]   # 特徴の欄「雑種 キジトラ オス 4ヶ月齢位」を分ける
    r2 = _run("city_kofu-2", "t519v_g5_kofu_today.html")
    assert len(r2.animals) == 51
    assert r2.animals[0]["name"] == "チビ"        # 名前は「その他の特徴」の「名前は「チビ」」
    r2 = _run("city_kofu-2", "t519v_g5_kofu_20260413.html")      # 表に class が付かない版（2026-04-13）でも 2 つの表を取り違えない
    assert len(r2.animals) == 53
    r1 = _run("city_kofu-1", "t519v_g5_kofu_20260413.html")
    assert [(a["management_no"], a["species"]) for a in r1.animals] == [("252109", "other"), ("251083", "cat")]


# --- 静岡市の迷い犬情報: 0 頭の日の文言が日によって違う（文言なしの日もある）ので、犬の見出し h2 が無いことで 0 頭と確定する ---


def test_shizuoka_reads_the_stray_dog_listings_and_zero_days_in_every_wording():
    for name, breed, sex in (("t519v_g5_shizuoka_20250219.html", "ヨークシャーテリア", "オス"), ("t519v_g5_shizuoka_20240625.html", "雑種", "メス")):
        r = _run("city_shizuoka-1", name)
        assert len(r.animals) == 1
        a = r.animals[0]
        assert (a["breed"], a["sex"], a["species"]) == (breed, sex, "dog")
        assert a["image_url"] and a["shelter_date"]
    for name in ("t519v_g5_shizuoka_20240714_empty.html", "t519v_g5_shizuoka_20260710_empty.html", "t519v_g5_shizuoka_today_empty.html"):
        r = _run("city_shizuoka-1", name)
        assert r.animals == [] and r.empty_confirmed is True, name


def test_matsumoto_4_closed_listing_is_not_listed():
    # Wayback 2025-08-15: 見出し「募集を終了しました」の 7-1 は載せない（T519 ゲート F-03）
    a = _run("city_matsumoto-4", "t519v_g5_matsumoto4_20250815_closed.html").animals
    assert sorted(x["management_no"] for x in a) == ["6-2", "6-3"]
