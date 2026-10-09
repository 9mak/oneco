"""T519v G1・G6 の検証で直したレシピを、今日（2026-10-05〜07）と Wayback の実ページから切り出した HTML（fixtures/t519v_g1g6_*.html）に当てる（ネットワークなし）。

直した点（どれも Wayback で「動物がいた日」に当てて見つけた）:
- 青森市の譲渡一覧: 名前が無い子（ワンニャン里親探しポスト）・「※…お見合い中止」の注記がある子の管理番号・品種・毛色を読む。猫の節が丸ごと空の版の 0 頭
- 青森市の迷い犬・猫等: link_only をやめ、一覧から個別ページ（1 頭 1 ページ）を辿って読む。0 頭の 2 通り（文言／本文が空）
- 八戸市の迷子動物: 0 頭の日の実際の文言。ニワトリなど犬猫以外は other
- 八戸市の譲渡動物: 1 つの表に動物が行で並ぶ。犬猫以外の表（クサガメ）。0 頭の日。「譲渡決まりました」の行は載せない
- 盛岡市の譲渡情報: 見出しの誤字・半角括弧の版・「【譲渡決定】」の終わった子・2 頭まとめの見出しの下の h3・集合写真の h3・1 つの見出しの下に 2 頭続く版
- 盛岡市の迷子情報: 動物が載った日の作り・0 頭の文言の違い・特徴に案内文が混ざらない・「毛色等」
- 函館市: 0 頭の文言を犬・猫の両方に（動物が載った日の新しい作りの保存は無く、旧い作りの表を div.text-beginning に入れた合成の版で読み方を確かめる）
- 小樽市: 2022 年の作り（動物が載った日）の項目、0 頭の旧い文言
- 堺市: 動物がいる日の一覧（stray/dog/list.html）の行
- 寝屋川市: 値の入っていない雛形の表の日は 0 頭
- 西宮市の迷子: 動物が載った日の作り・文言も動物も無い 0 頭の日
- 西宮市の譲渡: class の無い写真の p
- 吹田市の保護情報: 動物が載った日の作り（写真も管理番号も無く、日付・場所・種類と特徴だけ）と 0 頭の 2 通りの文言
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "tests" / "fixtures"


def _fx(name: str) -> str:
    return (FX / f"t519v_g1g6_{name}.html").read_text(encoding="utf-8")


def _build(slug: str, html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


# --- 青森市 -------------------------------------------------------------------------
def test_aomori_reads_unnamed_post_cats_and_the_note_before_breed():
    res = _build("city_aomori-1", _fx("aomori1_20260205"))
    assert len(res.animals) == 12
    tuna = res.animals[0]
    assert (tuna["name"], tuna["management_no"], tuna["breed"], tuna["color"]) == ("ツナ", "R07-62", "MIX", "パステルサビ")
    assert tuna["note"] == "※体調不良のため、譲渡お見合い中止"
    unnamed = res.animals[3]    # ワンニャン里親探しポスト: span.imgtitle が「R7-207」だけ（「」が無い）
    assert unnamed["name"] is None and unnamed["management_no"] == "R7-207"
    assert (unnamed["breed"], unnamed["color"], unnamed["sex"], unnamed["age"]) == ("MIX", "キジトラ", "メス", "令和7年7月生まれ")
    assert all(a["species"] == "cat" and a["image_url"] for a in res.animals)


def test_aomori_collapsed_dog_section_and_decided_cat_today():
    res = _build("city_aomori-1", _fx("aomori1_20260515"))
    assert [a["name"] for a in res.animals] == ["福"]
    res = _build("city_aomori-1", _fx("aomori1_20261005"))
    assert [(a["name"], a["management_no"]) for a in res.animals] == [("ベル", "R8-47")]     # 決まりました の 4 頭は載せない


def test_aomori_zero_day_when_dog_and_cat_sections_are_collapsed():
    html = "<div id='voice'><h2>犬</h2><p>現在、募集中の動物はいません。</p><h2>猫</h2><p>現在、募集中の動物はいません。</p><h2>犬猫以外の動物</h2><p>現在、募集中の動物はいません。</p></div>"
    res = _build("city_aomori-1", html)
    assert res.animals == [] and res.empty_confirmed


# --- 八戸市 -------------------------------------------------------------------------
def test_hachinohe_stray_today_turtles_are_other():
    res = _build("city_hachinohe-1", _fx("hachinohe1_20261005"))
    assert [(a["management_no"], a["species"], a["breed"], a["shelter_date"]) for a in res.animals] == [
        ("1", "other", "カメ", "令和8年9月8日"), ("2", "other", "カメ", "令和8年9月18日")]


def test_hachinohe_stray_chicken_is_other_and_dog_is_dog():
    res = _build("city_hachinohe-1", _fx("hachinohe1_20250815"))
    assert [(a["breed"], a["species"]) for a in res.animals] == [("ニワトリ(品種不明)", "other"), ("カメ", "other"), ("雑種(犬)", "dog")]


def test_hachinohe_stray_zero_day_wording():
    res = _build("city_hachinohe-1", _fx("hachinohe1_20260628_empty"))
    assert res.animals == [] and res.empty_confirmed


def test_hachinohe_adoption_one_table_holds_many_cats_and_decided_kittens_are_dropped():
    res = _build("city_hachinohe-2", _fx("hachinohe2_20250708"))
    # 子猫 4 頭（名前 1〜4）は 3 セル目が「譲渡決まりました。」なので載せない
    assert [a["name"] for a in res.animals] == ["チャ", "クロ", "まめ"]
    assert all(a["species"] == "cat" and a["image_url"] for a in res.animals)
    cha = res.animals[0]
    assert (cha["breed"], cha["color"], cha["sex"], cha["age"]) == ("ミックス", "茶トラ", "オス", "1.5か月位")
    assert cha["note"].startswith("脱走大好き。")


def test_hachinohe_adoption_other_animal_without_name():
    res = _build("city_hachinohe-2", _fx("hachinohe2_20261006"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["breed"], a["size"], a["name"]) == ("other", "クサガメ", "約21センチメートル", None)
    assert a["image_url"].endswith("20261006kusagame.JPG")


def test_hachinohe_adoption_zero_day_even_with_the_site_typo_in_the_cat_section():
    html = _fx("hachinohe2_20260625_empty")     # 猫の節の文言が「現在、譲渡対象の犬はいません。」になっている日
    res = _build("city_hachinohe-2", html)
    assert res.animals == [] and res.empty_confirmed
    phrase = "現在、譲渡対象の犬はいません。"
    second = html.index(phrase, html.index(phrase) + 1)          # 2 つ目（猫の節）を正しい文言に戻した版
    fixed = html[:second] + "現在、譲渡対象の猫はいません。" + html[second + len(phrase):]
    res = _build("city_hachinohe-2", fixed)
    assert res.animals == [] and res.empty_confirmed


def test_hachinohe_adoption_one_empty_section_is_not_a_zero_day():
    # 猫の節だけが空で、犬・犬猫以外の節が空でない日に 0 頭と判定しない（表が読めなかったときは failed で通知に出る）
    html = _fx("hachinohe2_20260625_empty").replace("現在、譲渡対象の動物はいません。", "現在、譲渡対象の動物がいます。")
    res = _build("city_hachinohe-2", html)
    assert res.animals == [] and not res.empty_confirmed


# --- 盛岡市 -------------------------------------------------------------------------
def test_morioka_adoption_today_15_cats_group_photo_h3_is_not_an_animal():
    res = _build("city_morioka-1", _fx("morioka1_20261005"))
    assert len(res.animals) == 15
    by_no = {a["management_no"]: a for a in res.animals}
    # 集合写真の h3（7－P・7－Q・7－R）は動物にならず、3 頭は各自の写真
    assert by_no["7-P"]["image_url"].endswith("tyobita1.jpg") and by_no["7-Q"]["image_url"].endswith("mamekiti1.jpg") and by_no["7-R"]["image_url"].endswith("siratama1.jpg")
    # 預かりボランティアさんのメッセージが無い子の特徴
    assert by_no["8-C"]["name"] == "ライフ" and by_no["8-C"]["note"].startswith("澄んだ青い目が魅力的なシャム猫です。")
    assert by_no["5-H"]["note"].startswith("事故により、左後ろ足の骨がとび出し")
    assert all(a["species"] == "cat" for a in res.animals)


def test_morioka_adoption_two_cats_under_one_heading_with_h3_each():
    res = _build("city_morioka-1", _fx("morioka1_20260516"))
    by_no = {a["management_no"]: a for a in res.animals}
    assert len(res.animals) == 14
    assert (by_no["11-J"]["name"], by_no["11-J"]["image_url"].endswith("11-Jdennbo.jpg")) == ("でんぼ", True)
    assert (by_no["11-G"]["name"], by_no["11-G"]["image_url"].endswith("11-Gkazuma.jpg")) == ("かずま", True)


def test_morioka_adoption_decided_cats_with_tag_in_the_heading_are_not_listed():
    res = _build("city_morioka-1", _fx("morioka1_20240224"))     # 「【譲渡決定】新しい飼い主を探している猫（9－C)」は終わった子
    assert [a["management_no"] for a in res.animals] == ["10-N", "9-B", "6-AF", "7-C", "6-AC"]


def test_morioka_adoption_typo_heading_and_halfwidth_paren():
    res = _build("city_morioka-1", _fx("morioka1_20250120"))     # 「【新し飼い主を探しています】（11－A）」・「（3－E)」
    nos = [a["management_no"] for a in res.animals]
    assert "11-A" in nos and "3-E" in nos and "2-B" in nos and len(nos) == 7


def test_morioka_adoption_second_cat_under_the_same_heading_is_read():
    # 2025-04: 見出し「（3－E）」の下に 3－E と 3－F が続く（3－F は自分の見出しが無く、写真から始まる）
    res = _build("city_morioka-1", _fx("morioka1_20250402"))
    by_no = {a["management_no"]: a for a in res.animals}
    assert len(res.animals) == 10 and by_no["3-F"]["name"] == "らん" and by_no["3-F"]["image_url"].endswith("3-F_run.jpeg")
    # 2023-02: 見出し「（12-F)（12-G）」の下に 12-F ツムギと 12-G イト
    res = _build("city_morioka-1", _fx("morioka1_20230204"))
    by_no = {a["management_no"]: a for a in res.animals}
    assert len(res.animals) == 10 and (by_no["12-F"]["name"], by_no["12-G"]["name"]) == ("ツムギ", "イト")


def test_morioka_stray_reads_the_animal_days_of_three_layouts():
    a = _build("city_morioka-2", _fx("morioka2_20240412")).animals[0]          # 項目名「保護された日：」の p
    assert (a["management_no"], a["species"], a["shelter_date"], a["location"], a["color"]) == ("3-D", "cat", "3月28日", "東新庄一丁目", "白キジ")
    a = _build("city_morioka-2", _fx("morioka2_20260119")).animals[0]          # ul の li に項目が並ぶ・種類の欄が無い
    assert (a["management_no"], a["shelter_date"], a["location"], a["sex"], a["breed"]) == ("12-A", "令和7年12月5日", "永井22地割地内", "オス", None)
    res = _build("city_morioka-2", _fx("morioka2_20211022"))                   # 【保護年月日】…の p・見出しは「もとの飼い主を待っている猫（10-B）」
    assert [(x["management_no"], x["shelter_date"], x["location"]) for x in res.animals][:2] == [("10-B", "令和3年10月2日", "北山一丁目"), ("9-B", "令和3年9月24日", "本宮三丁目")]


def test_morioka_stray_zero_day_two_wordings():
    for name in ("morioka2_20261005_empty", "morioka2_20230331_empty"):      # 「元の飼い主を待っている」「もとの飼い主を待っている…保護施設では」
        res = _build("city_morioka-2", _fx(name))
        assert res.animals == [] and res.empty_confirmed, name


def test_morioka_stray_note_stops_before_the_page_notice_and_color_with_tou():
    res = _build("city_morioka-2", _fx("morioka2_20210930"))        # 最後の子の特徴の後ろに「なお,盛岡市以外で…」「愛護動物の遺棄…」の案内が続く
    assert [a["management_no"] for a in res.animals] == ["9-B", "6-K"]
    assert res.animals[1]["note"].endswith("首輪をしていた痕があります。") and "盛岡市以外" not in res.animals[1]["note"]
    a = _build("city_morioka-2", _fx("morioka2_20251010")).animals[0]   # 「毛色等：白黒（やや長毛）」
    assert (a["management_no"], a["color"], a["shelter_date"]) == ("9-G", "白黒(やや長毛)", "令和7年9月18日")


# --- 青森市（迷い犬・猫等） -----------------------------------------------------------
def test_aomori2_child_page_is_one_animal_and_index_is_not():
    res = _build("city_aomori-2", _fx("aomori2_child_20250513"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["shelter_date"], a["location"], a["breed"], a["sex"], a["color"], a["size"]) == (
        "cat", "5月7日(水曜日)", "安方", "雑種", "オス", "キジ白", "中")
    assert a["image_url"].endswith("0507.jpg")


def test_aomori2_zero_days_two_forms():
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "city_aomori-2")
    recipe = Recipe.load(ROOT / "recipes" / "city_aomori-2.yaml")
    for name in ("aomori2_index_20251006_empty_text", "aomori2_index_20261007_blank"):
        html = _fx(name)       # 一覧にリンクが無い日は子が 0 件（follow_all の結果は空）で、入口だけを見て 0 頭と確定する
        doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
        res = build(src, recipe, [], [doc])
        assert res.animals == [] and res.empty_confirmed, name
    html = _fx("aomori2_index_20250512")      # 動物がいる日は一覧に個別ページへのリンクがあるので 0 頭にしない
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    assert not build(src, recipe, [], [doc]).empty_confirmed


# --- 函館市 -------------------------------------------------------------------------
def test_hakodate_zero_day_needs_both_dog_and_cat_sections():
    res = _build("city_hakodate-1", _fx("hakodate1_20260615_empty"))
    assert res.animals == [] and res.empty_confirmed
    one_missing = _fx("hakodate1_20260615_empty").replace("現在，該当する犬はおりません。", "")
    res = _build("city_hakodate-1", one_missing)     # 犬の節の文言が無い日は 0 頭と確定しない（犬が読めていないかもしれない）
    assert res.animals == [] and not res.empty_confirmed


def test_hakodate_old_cms_zero_day_is_still_zero():
    # 2023-04-11 の Wayback（旧 CMS）: h2 が無く、犬の表と猫の表が見出し行つきで並び、各表の下に文言。base では猫の文言だけで 0 頭にしていた
    res = _build("city_hakodate-1", _fx("hakodate1_20230411_old_cms_empty"))
    assert res.animals == [] and res.empty_confirmed
    res = _build("city_hakodate-1", _fx("hakodate1_20230411_old_cms_empty").replace("現在，該当する犬はおりません。", ""))
    assert res.animals == [] and not res.empty_confirmed


def test_hakodate_old_table_layout_inside_the_new_page_is_read():
    # 合成: 2022-10-05 の Wayback の犬の表（管理番号 30・柴犬）を、新しい作りの【犬】の節に入れた版。新しい CMS で動物が載った日の保存は無い
    res = _build("city_hakodate-1", _fx("hakodate1_synthetic_table_dog"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["management_no"], a["shelter_date"], a["location"], a["breed"], a["color"], a["sex"]) == (
        "dog", "30", "令和4年10月1日", "日吉町4丁目", "柴犬", "茶", "オス")
    assert a["image_url"].endswith("R4-D30.JPG")


# --- 小樽市 -------------------------------------------------------------------------
def test_otaru_2022_animal_day_fields_and_two_zero_day_wordings():
    res = _build("city_otaru-1", _fx("otaru1_20220324"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["management_no"], a["shelter_date"], a["location"], a["breed"], a["sex"], a["size"]) == (
        "M3-2", "令和4年3月18日", "桂岡町2番", "ミニチュアダックスフンド", "おす", "小")
    assert a["note"].startswith("首輪等なし、老犬") and a["image_url"].endswith("M3-2.jpg")
    for name in ("otaru1_20260116_empty", "otaru1_20210326_empty"):      # 「現在、収容犬はいません。」/「現在、迷い犬はいません。…引き取り犬はいません。」
        res = _build("city_otaru-1", _fx(name))
        assert res.animals == [] and res.empty_confirmed, name


# --- 堺市 ---------------------------------------------------------------------------
def test_sakai_list_rows_are_animals_and_header_row_is_not():
    for name, no, species, breed, loc in (("sakai_list_dog_2008", "2008-12-0002", "dog", "ボストン・テリア", "堺市中区 新家町"),
                                           ("sakai_list_cat_2015", "2015-02-0005", "cat", "雑種", "堺市美原区 太井")):
        res = _build("eonet_sakai-1", _fx(name))
        assert len(res.animals) == 1, name
        a = res.animals[0]
        assert (a["management_no"], a["species"], a["breed"], a["location"], a["sex"]) == (no, species, breed, loc, "雄")
        assert a["image_url"].endswith(f"{no}_00.jpg") or a["image_url"].endswith(f"{no}_00.png")
        assert a["source_url"].endswith(f"/{no}.html")      # 個体ページへのリンク（個体ページは辿らない）


def test_sakai_empty_list_page_is_zero():
    html = _fx("sakai_list_dog_2008")
    start = html.index("<tr>", html.index("</tr>") + 5)
    empty = html[:start] + "</table></body></html>"          # 見出し行だけで個体ページへのリンクが無い一覧
    res = _build("eonet_sakai-1", empty)
    assert res.animals == [] and res.empty_confirmed


# --- 寝屋川市 -----------------------------------------------------------------------
def test_neyagawa_blank_template_table_is_a_zero_day():
    res = _build("city_neyagawa-1", _fx("neyagawa1_20230311_template"))
    assert res.animals == [] and res.empty_confirmed
    # 値が入った日は雛形として扱わない（空かどうかは td の p の中身で決める）
    import re
    filled = re.sub(r"<td>\s*<p>(?:&nbsp;|\s)*</p>\s*</td>", "<td><p>寝屋川市池田</p></td>", _fx("neyagawa1_20230311_template"), count=1)
    assert filled != _fx("neyagawa1_20230311_template")
    assert not _build("city_neyagawa-1", filled).empty_confirmed


# --- 西宮市 -------------------------------------------------------------------------
def test_nishinomiya_stray_dog_day_number_species_and_japanese_era_date():
    res = _build("nishi_nishinomiya-1", _fx("nishi1_20240614"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["management_no"], a["species"], a["shelter_date"], a["location"], a["sex"]) == ("553", "dog", "令和6年6月11日", "西宮市松並町", "雄")
    assert a["image_url"].endswith("dog553-1.jpg")


def test_nishinomiya_stray_zero_day_today():
    res = _build("nishi_nishinomiya-1", _fx("nishi1_20261005_empty"))
    assert res.animals == [] and res.empty_confirmed


def test_nishinomiya_stray_zero_day_without_any_wording():
    for name in ("nishi1_20250428_empty", "nishi1_20260310_empty"):      # 枠（h2）だけで文言も動物も無い版
        res = _build("nishi_nishinomiya-1", _fx(name))
        assert res.animals == [] and res.empty_confirmed, name
    res = _build("nishi_nishinomiya-1", _fx("nishi1_20240614"))        # 動物の見出し・表がある日は 0 頭にしない
    assert len(res.animals) == 1 and not res.empty_confirmed


def test_nishinomiya_adoption_photos_in_plain_p_and_trial_cat_included():
    res = _build("nishi_nishinomiya-2", _fx("nishi2_20260512"))
    assert [(a["management_no"], a["species"]) for a in res.animals] == [("625", "cat"), ("626", "cat"), ("580", "cat"), ("621", "cat")]   # 580 は体験飼育が決まった子（載せる）
    assert [a["image_url"].rsplit("/", 1)[-1] for a in res.animals] == ["konnbu.png", "sansyo.png", "download.jpeg", "IMG_3623.png"]


def test_nishinomiya_adoption_today_one_dog():
    res = _build("nishi_nishinomiya-2", _fx("nishi2_20261005"))
    assert [(a["management_no"], a["species"], a["breed"]) for a in res.animals] == [("653", "dog", "ヨークシャーテリア")]
    assert res.animals[0]["image_url"].endswith("youchan.jpeg")


# --- 吹田市 -------------------------------------------------------------------------
def test_suita_animal_day_has_no_photo_or_number():
    res = _build("city_suita-1", _fx("suita1_20250708"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["shelter_date"], a["location"], a["note"]) == ("cat", "令和7年7月7日", "吹田市津雲台1丁目3番付近", "猫、性別不明、茶トラ、子猫")
    assert a["image_url"] is None and a["management_no"] is None


def test_suita_zero_day_two_wordings_and_label_only_template_is_not_an_animal():
    for name in ("suita1_20261005_empty", "suita1_20240612_empty"):     # 「現在保護情報はありません。」「※現在、保護情報はありません。」（見出しの p だけ残る版）
        res = _build("city_suita-1", _fx(name))
        assert res.animals == [] and res.empty_confirmed, name
