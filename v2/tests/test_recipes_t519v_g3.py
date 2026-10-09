"""T519 検証 g3: 郡山市・いわき市・新潟市・いくとぴあ・富山市・金沢市・福井県動物愛護センター（fapscsite）のレシピ（ネットワークなし）。

fixture は実ページ（2026-10-07 の取得と、Wayback Machine の保存）の本文の部分だけを抜いたもの。
どの fixture も、直す前のレシピで動物の取りこぼし・偽の動物・別の写真・0 頭の判定の失敗が起きた日のもの。
"""

from dataclasses import replace
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str) -> Source:
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    if slug == "fapscsite-3":    # link_only をやめて読む（台帳の差し替えブロックを当てた後と同じ状態にしておく）
        src = replace(src, mode="recipe", recipe="recipes/fapscsite-3.yaml")
    return src


def _run(slug: str, fixture: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    html = (FIX / f"t519v_g3_{fixture}.html").read_text(encoding="utf-8")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _imgs(res) -> list[str]:
    return [(a["image_url"] or "").rsplit("/", 1)[-1] for a in res.animals]


# --- 郡山市 -------------------------------------------------------------------
def test_koriyama1_today_reads_the_dog_with_its_photo():
    res = _run("city_koriyama-1", "koriyama1_today")
    assert len(res.animals) == 1 and res.rows == 2     # 後ろの空の雛形の表は捨てる
    a = res.animals[0]
    assert (a["species"], a["breed"], a["color"], a["sex"], a["shelter_date"], a["location"]) == (
        "dog", "柴", "赤", "雌", "令和8年9月18日", "富田町字上ノ台")
    assert _imgs(res) == ["57144.jpg"]


def test_koriyama1_skips_the_dog_that_went_back_to_the_owner():
    # 2025-02: 3 頭目は特記事項が「飼い主へ返還」。載せると返した子を保護中として見せる
    res = _run("city_koriyama-1", "koriyama1_202502")
    assert [a["management_no"] for a in res.animals] == ["16", "17"]
    assert [a["sex"] for a in res.animals] == ["雄", "メス"]


def test_koriyama1_zero_dogs_is_confirmed_by_the_zero_count_heading():
    res = _run("city_koriyama-1", "koriyama1_202606_zero")
    assert res.animals == [] and res.empty_confirmed


def test_koriyama1_broken_dog_table_is_failed_not_zero():
    # 猫の節の「現在保護情報はありません」は犬がいる日にも出る。犬の表が読めなくなった日を 0 頭に見せない
    src = _source("city_koriyama-1")
    recipe = Recipe.load(ROOT / "recipes" / "city_koriyama-1.yaml")
    html = (FIX / "t519v_g3_koriyama1_today.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    for t in soup.select("table"):
        t.decompose()
    assert "現在保護情報はありません" in soup.get_text()
    res = build(src, recipe, [Doc(url=src.url, html=str(soup), soup=soup)])
    assert res.animals == [] and not res.empty_confirmed


def test_koriyama2_today_reads_the_dog_in_the_new_layout():
    res = _run("city_koriyama-2", "koriyama2_today")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["breed"], a["color"], a["sex"], a["size"], a["management_no"]) == ("dog", "雑種", "茶白", "雄", "中", None)
    assert _imgs(res) == ["57257.jpg"]


def test_koriyama2_reads_the_table_whose_summary_is_not_the_blank_template_one():
    # 2025-01: 動物の表の summary は「犬の情報の表」（空の雛形だけ「飼い主募集」）。管理番号は表の見出し行（th の隣の th）にある
    res = _run("city_koriyama-2", "koriyama2_202501")
    assert [(a["species"], a["management_no"], a["breed"], a["color"]) for a in res.animals] == [("dog", "11", "雑種", "茶白")]
    assert _imgs(res) == ["41042.jpg"]


def test_koriyama2_adopted_dog_is_not_listed_and_the_day_is_zero():
    res = _run("city_koriyama-2", "koriyama2_202312_adopted")
    assert res.animals == [] and res.empty_confirmed


def test_koriyama2_zero_dogs_text_is_confirmed():
    res = _run("city_koriyama-2", "koriyama2_202212_zero")
    assert res.animals == [] and res.empty_confirmed


# --- 新潟市（迷子）-----------------------------------------------------------------
def test_niigata_stray_cats_read_every_animal_whatever_the_heading_level():
    # 2025-05: 1 頭目は h2bg、2〜4 頭目は h3bg。写真は見出しの後にある子と、無い子（1 頭目）がいる
    res = _run("city_niigata-2", "niigata2_202505")
    assert [(a["shelter_date"], a["breed"], a["sex"], a["color"], a["location"]) for a in res.animals] == [
        ("令和7年3月19日", "ミックス", "オス(去勢)", "白黒", "秋葉区矢代田"),
        ("令和7年4月22日", "ミックス", "メス", "サビ(麦わら)", "中央区二葉町2丁目"),
        ("令和7年4月30日", "ミックス", "オス", "キジトラ", "北区濁川"),
        ("令和7年5月22日", "ミックス", "メス", "キジトラ", "東区東中島"),
    ]
    assert all(a["species"] == "cat" and a["kind"] == "stray" for a in res.animals)
    assert _imgs(res) == ["", "R7-9.jpg", "R7.4.30.jpg", "ID47.jpg"]
    assert [a["age"] for a in res.animals] == ["推定15才前後", "推定5才前後", "推定4才前後", "推定15才前後"]


def test_niigata_stray_cat_takes_the_management_number_from_the_heading():
    res = _run("city_niigata-2", "niigata2_202608")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["management_no"], a["shelter_date"], a["location"], a["age"]) == ("R8-140", "令和8年7月20日", "中央区出来島", "推定2-3才前後")
    assert _imgs(res) == ["R8-140.jpg"]
    assert "迷彩柄" in a["note"] and "保護している場所" not in a["note"]


def test_niigata_stray_dog_in_both_layouts():
    res = _run("city_niigata-1", "niigata1_202412")     # 写真 → 表（ul）の並び
    assert [(a["breed"], a["color"], a["sex"], a["shelter_date"], a["location"]) for a in res.animals] == [("ミックス", "茶黒", "オス", "令和6年8月15日", "南区清水")]
    assert _imgs(res) == ["R6.8.15-1.jpg"] and "保護している場所" not in res.animals[0]["note"]
    res = _run("city_niigata-1", "niigata1_202306")     # 写真と ul が 1 つの div.img-area-l の中
    assert [(a["breed"], a["color"], a["sex"], a["shelter_date"]) for a in res.animals] == [("柴", "茶", "めす", "令和5年5月22日")]
    assert _imgs(res) == ["230522siba.jpg"]


def test_niigata_stray_zero_days_are_confirmed():
    for slug, fx in (("city_niigata-1", "niigata1_today_zero"), ("city_niigata-2", "niigata2_today_zero")):
        res = _run(slug, fx)
        assert res.animals == [] and res.empty_confirmed, slug


def test_niigata_stray_page_that_loses_its_animals_is_failed_not_zero():
    # 動物がいるのに見出しの作りが変わって読めなくなった日（h2bg を別の名前にした）は 0 頭に見せない
    src = _source("city_niigata-2")
    recipe = Recipe.load(ROOT / "recipes" / "city_niigata-2.yaml")
    html = (FIX / "t519v_g3_niigata2_202505.html").read_text(encoding="utf-8").replace("h2bg", "hhbg").replace("h3bg", "hhbg")
    res = build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])
    assert res.animals == [] and not res.empty_confirmed


# --- 新潟市（譲渡）-----------------------------------------------------------------
def test_niigata_adoption_dog_zero_day_wordings_are_confirmed():
    for fx in ("niigata3_202411_zero", "niigata3_202302_zero"):
        res = _run("city_niigata-3", fx)
        assert res.animals == [] and res.empty_confirmed, fx


# --- 金沢市 -------------------------------------------------------------------
def test_kanazawa_adoption_dog_blank_template_with_illustration_is_zero_not_a_fake_animal():
    # 0 頭の日（2024-11）は項目が空の雛形の表が残り、前の兄弟の「最初の 1 枚」が本文冒頭の犬のイラスト（pet_inu.jpg）で、中身が空の「動物 1 頭」になっていた
    res = _run("city_kanazawa-5", "kanazawa5_202411_blank")
    assert res.animals == [] and res.empty_confirmed


def test_kanazawa_adoption_dog_keeps_its_own_photo_not_the_illustration():
    # 2024-04: 1 頭目の写真がイラスト（pet_inu.jpg）になっていた
    res = _run("city_kanazawa-5", "kanazawa5_202404")
    assert [(a["management_no"], a["breed"], a["sex"], a["age"]) for a in res.animals] == [("D050808", "雑種", "雄", "9歳程度")]
    assert _imgs(res) == ["D050808.png"]


def test_kanazawa_adoption_dogs_today():
    res = _run("city_kanazawa-5", "kanazawa5_today")
    assert [(a["management_no"], a["name"], a["breed"], a["color"], a["sex"], a["age"]) for a in res.animals] == [
        ("D070822", "ぽんぽん", "雑種", "茶", "オス", "14歳"),
        ("D080615", "松ぼっくり", "屋久島犬", "茶", "オス", "17歳"),
        ("D080710", "かいかい", "トイプードル", "レッド", "オス", "14歳"),
    ]
    assert _imgs(res) == ["1010.JPG", "777.jpg", "260929.jpg"]


def test_kanazawa_adoption_cats_today_and_in_the_2025_layout():
    res = _run("city_kanazawa-6", "kanazawa6_today")
    assert [(a["management_no"], a["name"]) for a in res.animals] == [
        ("C060926", "キングくん"), ("C080703", "もみじ"), ("C07102102", "四郎"), ("C080626", "カキくん")]
    assert _imgs(res) == ["555.jpg", "17171.jpg", "1313.JPG", "4444.jpg"]
    # 2025-01: h3「動物番号 C060209」→ 写真だけの div → 表の div。動物番号が表の外にあるので row_filter を動物番号にしていた版は 0 件で failed だった
    res = _run("city_kanazawa-6", "kanazawa6_202501")
    assert [(a["name"], a["breed"], a["color"], a["sex"], a["age"], a["size"]) for a in res.animals] == [("ぶぅー", "雑種", "キジ白", "オス", "10歳", "大")]
    assert _imgs(res) == ["C06020901.jpg"]
    assert [a["management_no"] for a in res.animals] == ["C060209"]    # この作りは動物番号が表の外の h3 にある


def test_kanazawa_sheltered_cats_first_animal_is_not_given_the_illustration():
    # 2024-08: 本文冒頭に猫のイラスト（pet_doubutu_*.jpg）の figure があり、1 頭目の写真になっていた。管理番号は見出し h3
    res = _run("city_kanazawa-2", "kanazawa2_202408")
    assert [(a["management_no"], a["breed"], a["shelter_date"]) for a in res.animals] == [
        ("C24051401", "雑種", "令和6年5月3日"), ("C24050801", "ノルウェージャンフォレストキャット", "令和6年5月8日")]
    assert _imgs(res) == ["C24051401.png", "C050801.JPG"]


def test_kanazawa_sheltered_zero_day_wordings_are_confirmed():
    # 読点の有無・「収容されている／している」の違いで 0 頭の日が failed になっていた。雛形の表が残る日も 0 頭
    for slug, fx in (("city_kanazawa-2", "kanazawa2_202510_zero"), ("city_kanazawa-2", "kanazawa2_today_zero"),
                     ("city_kanazawa-1", "kanazawa1_202407_zero"), ("city_kanazawa-1", "kanazawa1_today_zero")):
        res = _run(slug, fx)
        assert res.animals == [] and res.empty_confirmed, (slug, fx)


def test_kanazawa_lost_board_reads_both_layouts_and_zero_days():
    res = _run("city_kanazawa-4", "kanazawa4_today")
    assert [(a["name"], a["species"], a["kind"], a["shelter_date"]) for a in res.animals] == [
        ("ぽんこ", "cat", "lost", "令和8年9月16日"), ("しっぽな", "cat", "lost", "令和8年9月4日"),
        ("リズ", "cat", "lost", "令和8年8月11日"), ("もなか", "cat", "lost", "令和8年6月21日")]
    assert _imgs(res) == ["85030425.jpeg", "ミズブチ.jpeg", "0812.jpeg", "76.jpg"]
    for fx in ("kanazawa4_202505_blank", "kanazawa4_202305_zero"):
        res = _run("city_kanazawa-4", fx)
        assert res.animals == [] and res.empty_confirmed, fx


# --- 2026-10-08 追加（前任の直しの確かめ直し。fixture は Wayback の保存と 2026-10-07 の取得）-----------------
def test_koriyama1_zero_dog_wording_without_count_heading_is_confirmed():
    # 2025-05: 見出しに件数が無く「現在保護されている犬はおりません。」＋空の雛形の表 3 つ。件数の語だけ見る版は failed だった
    res = _run("city_koriyama-1", "koriyama1_202505_zero")
    assert res.animals == [] and res.empty_confirmed


def test_koriyama1_reads_two_dogs_of_2025_12():
    res = _run("city_koriyama-1", "koriyama1_202512")
    assert [(a["management_no"], a["breed"], a["sex"], a["shelter_date"]) for a in res.animals] == [
        ("12", "ポメラニアン", "雄", "令和7年11月6日"), ("13", "Mix", "雄", "令和7年11月25日")]
    assert _imgs(res) == ["49717.jpg", "50252.jpg"]


def test_koriyama2_zero_dog_wording_with_blank_templates_is_confirmed():
    # 2024-07: 「現在飼い主募集の犬はおりません」＋空の雛形の表（「いません」だけを見る版は failed だった）
    res = _run("city_koriyama-2", "koriyama2_202407_zero")
    assert res.animals == [] and res.empty_confirmed


def test_niigata_stray_dog_in_the_2025_11_layout():
    # 2025-11: h2bg「迷子犬情報」→ h3bg「犬ID R7-54」→ img-area → p（保護日：…<br>場所：…<br>犬種：…）。収容年月日の語が無いので row_filter が全部落としていた
    res = _run("city_niigata-1", "niigata1_202511")
    assert [(a["management_no"], a["shelter_date"], a["location"], a["breed"], a["color"], a["sex"], a["age"]) for a in res.animals] == [
        ("R7-54", "令和7年11月13日", "中央区清五郎 新潟県スポーツ公園", "柴犬", "茶色", "メス", "推定5歳")]
    assert _imgs(res) == ["R7-54.jpg"]


def test_niigata_stray_cat_zero_wording_without_ga_is_confirmed():
    # 2023-06: 「…保護している猫はいません。」（今日は「猫がいません」）
    res = _run("city_niigata-2", "niigata2_202306_zero")
    assert res.animals == [] and res.empty_confirmed


def test_kanazawa_sheltered_dog_table_directly_under_the_article():
    # 2024-10: 犬が載った日。caption「収容中の犬の詳細」の表が本文の直下（写真は表の前の figure）
    res = _run("city_kanazawa-1", "kanazawa1_202410_dog")
    assert [(a["species"], a["breed"], a["sex"], a["age"], a["size"], a["shelter_date"], a["location"]) for a in res.animals] == [
        ("dog", "トイプードル", "オス", "7歳", "小型", "令和6年9月22日", "金沢市田上本町4丁目204番地1 ゲンキー金沢田上店")]
    assert _imgs(res) == ["24092401.jpg"]


def test_kanazawa_sheltered_cat_zero_wording_with_chuu_is_confirmed():
    res = _run("city_kanazawa-2", "kanazawa2_202502_zero")     # 「現在収容中の猫は、いません。」
    assert res.animals == [] and res.empty_confirmed


def test_iwaki_adoption_age_without_the_nenrei_label_and_adopted_cat_is_dropped():
    # とーこは特徴に「年齢：」が無く「推定３～５歳」だけ。ケンは●譲渡済なので載せない
    res = _run("city_iwaki-2", "iwaki2_today")
    assert [(a["name"], a["age"]) for a in res.animals] == [("ポンちゃん", "推定2~3歳"), ("とーこ", "推定3~5歳")]
    # 猫: せなは「R7.6.7生」だけ。●譲渡済・●譲渡決定（手続き待ち）の子は載せない
    res = _run("city_iwaki-3", "iwaki3_today")
    assert [(a["name"], a["age"]) for a in res.animals] == [("せな", "R7.6.7生まれ")]


def test_toyama_cat_age_keeps_the_whole_range():
    res = _run("city_toyama-1", "toyama1_202606")
    assert [(a["name"], a["sex"], a["age"]) for a in res.animals] == [
        ("イチロー", "オス", "3-5歳(譲渡会時点)"), ("ジャイアン", "オス", "6歳(譲渡会時点)")]


def test_fapscsite_lost_location_joins_area_and_place():
    res = _run("fapscsite-1", "fapscsite1_today")
    assert [(a["management_no"], a["species"], a["location"]) for a in res.animals] == [
        ("HC26409", "cat", "敦賀市 沢"), ("HD26378", "dog", "坂井市 坂井町田島窪"),
        # 一般の方から寄せられた保護情報（article.sender-user）も読む。題が「No.7F-6-2迷い猫を保護しています。」と続いても管理番号は番号の部分だけ。インコは犬猫以外
        ("No.8T-10-4", "cat", "保護主宅(丹南エリア) 問い合わせ先:本所"), ("No.7F-6-2", "cat", "保護主宅(福井エリア) 問い合わせ先:本所"),
        ("No.6S-8-15", "other", "保護主宅(坂井エリア) 問い合わせ先:本所")]


def test_fapscsite_individuals_posts_are_read_not_link_only():
    # 個人の氏名・電話番号は載らず問い合わせ先は本所・支所。全件「新しい飼い主を募集中」。ウサギ等は犬猫以外（other）
    res = _run("fapscsite-3", "fapscsite3_today")
    assert [(a["management_no"], a["species"]) for a in res.animals] == [
        ("No.8T-10-4", "other"), ("No.8O-10-1", "dog"), ("No.8R-9-28", "cat"), ("No.8T-9-26", "cat")]
    assert all(a["kind"] == "adoption" for a in res.animals)
    assert all(a["image_url"] for a in res.animals)
    assert res.animals[1]["location"].startswith("飼い主宅:奥越エリア")


def test_kanazawa_lost_board_reads_the_location_when_the_label_has_a_typo():
    # 2026-06: しろ・ネビの項目名が「いなくなっ？た場所」（掲載者の入力ミス）。場所が空になっていた
    res = _run("city_kanazawa-4", "kanazawa4_202606")
    assert [(a["name"], a["location"]) for a in res.animals] == [
        ("チャロ", "自宅から(金沢市弥生)"), ("しろ", "八田農村公園(白山市八田町)"), ("ネビ", "自宅から(金沢市上辰巳町)")]


def test_iwaki_stray_reads_the_2022_layout_and_the_zero_dog_day():
    # 2022-12: 表が div.edit-item でなく div.html の中にあった旧い作り。犬 4 頭（現在、４頭です）と猫 1 頭
    res = _run("city_iwaki-1", "iwaki1_202212")
    assert [(a["species"], a["management_no"], a["shelter_date"], a["location"]) for a in res.animals] == [
        ("dog", "4-35", "10月24日", "四倉町字西3丁目"), ("dog", "4-34", "10月17日", "内郷白水町上代"),
        ("dog", "4-16", "7月19日", "遠野町上遠野字原前"), ("dog", "4-4", "5月13日", "好間町下好間字鬼越"),
        ("cat", "4-1", "10月31日", "四倉町上仁井田字前原")]
    # 2024-06: 犬の節が「現在、０頭です。」＋項目名だけの雛形の表。猫の節の「０頭です」だけでは 0 頭にしない
    res = _run("city_iwaki-1", "iwaki1_202406_zero")
    assert res.animals == [] and res.empty_confirmed
