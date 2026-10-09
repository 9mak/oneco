"""T519 検証 g4a: 川越市・川口市・埼玉県（保健所・動物指導センター）のレシピ（ネットワークなし）。

fixture は Wayback Machine の保存ページ（本文の要素だけ）。2026-10-07 に取得。
- t519v_g4a_kawagoe_hogo_20251021.html: 猫 2 頭（1 頭目は li の中に br で「※負傷のため写真は掲載しません。」が続く）・犬 0 頭
- t519v_g4a_kawagoe_hogo_20260314.html: 犬 1 頭（品種が「品種不明（ポメラニアン風）」）・猫 0 頭。犬の節に PDF リンクだけの 2 つ目の ul が続く
- t519v_g4a_kawaguchi-2_20250504.html: 猫 4 頭（R6-0020・R6-0021 は 1 ブロックに 2 頭、写真だけを並べた管理番号の無いブロックが 2 つ、年齢の書き方が「年齢：推定2歳」）
- t519v_g4a_kawaguchi-2_20260814.html: 犬 2 頭（1 頭はトライアル中で、ブロックの中に h3「※トライアル中です※」）・猫 10 頭
- t519v_g4a_center_honsho_20250328_template.html: 管理番号だけ入った雛形（収容日「2025年月日」）。動物ではない
- t519v_g4a_nanbu_20250719_zero.html / sayama_20260417_zero / honjo_20230306_zero: 0 頭の日の文言違い
2 回目の検証（2026-10-08）で追加（同じく Wayback の保存ページ）:
- t519v_g4a_center_minami_20260908_dead.html: 備考「収容後死亡。」の猫 1 頭だけの日（亡くなった子は載せない）
- t519v_g4a_honjo_20241216_4col.html: 1 行 4 セル「大きさ | 大 | 種類 | 雑種」の作り（品種を列の位置で読むと大きさを取る）
- t519v_g4a_kawaguchi-2_20220309 / 20230531 / 20240528_zero: 旧い作り（h2 の犬猫見出し・「種類：」・「品  種：」・猫の 0 頭の文言）
- t519v_g4a_kawaguchi-1_*: 迷子ページ（入口の 0 頭の日・動物のリンクがある日・犬の子ページ・猫の子ページ）
- t519v_g4a_sakado_20220808_old_layout / 20221203_template / 20211202_zero: 坂戸の旧い作り（「番号 | 6」）・番号欄が空の雛形・文言違い
- t519v_g4a_center_honsho_20240715_zero / higashimatsuyama_20240524_zero: 0 頭の文言違い
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


def _fx(name: str) -> str:
    return (FIX / f"t519v_g4a_{name}.html").read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


# --- 川越市 保護収容 ----------------------------------------------------------------------------------------------
def test_kawagoe_cat_with_injury_note_in_the_same_li_keeps_breed_color_age_and_the_note():
    html = _fx("kawagoe_hogo_20251021")
    cats = _run("city_kawagoe-2", html)
    assert [a["management_no"] for a in cats.animals] == ["R7 No.2", "R7 No.8"]
    assert _pick(cats.animals[0], "shelter_date", "location", "breed", "color", "age", "note", "image_url") == {
        "shelter_date": "8月16日", "location": "広栄町", "breed": "雑種", "color": "黒白茶", "age": "年齢不詳(成猫)",
        "note": "※負傷のため写真は掲載しません。", "image_url": None}
    assert _pick(cats.animals[1], "breed", "color", "age", "note") == {"breed": "雑種", "color": "茶白", "age": "年齢不詳(成猫)", "note": None}
    dogs = _run("city_kawagoe-1", html)
    assert dogs.animals == [] and dogs.empty_confirmed


def test_kawagoe_dog_with_parentheses_in_breed_and_pdf_only_second_ul():
    html = _fx("kawagoe_hogo_20260314")
    dogs = _run("city_kawagoe-1", html)
    assert len(dogs.animals) == 1
    assert _pick(dogs.animals[0], "management_no", "shelter_date", "location", "breed", "color", "age") == {
        "management_no": "No008", "shelter_date": "2月24日", "location": "松郷", "breed": "品種不明(ポメラニアン風)", "color": "黒", "age": "成犬"}
    cats = _run("city_kawagoe-2", html)
    assert cats.animals == [] and cats.empty_confirmed


def test_kawagoe_zero_sentence_of_the_other_section_does_not_confirm_zero():
    # 犬の節の文言だけが 0 頭の印。猫の節に動物がいて（構造が違って読めない日でも）犬の節の文言で猫を 0 頭にしない
    html = _fx("kawagoe_hogo_20251021")
    broken = html.replace("<ul>", "<div>").replace("</ul>", "</div>")   # 猫の節の ul が無くなった（構造が変わった）日
    cats = _run("city_kawagoe-2", broken)
    assert cats.animals == [] and not cats.empty_confirmed


# --- 川越市 譲渡 --------------------------------------------------------------------------------------------------
def test_kawagoe_3_all_decided_is_zero_by_the_exclusion_not_by_a_sentence():
    html = (FIX / "t519_kawagoe-3_20261005.html").read_text(encoding="utf-8")
    recipe = Recipe.load(ROOT / "recipes" / "city_kawagoe-3.yaml")
    assert recipe.empty_text == []
    res = _run("city_kawagoe-3", html)
    assert res.animals == [] and res.empty_confirmed and len(res.dropped) == 4


def test_kawagoe_3_page_without_any_h4_is_failed_not_zero():
    html = (FIX / "t519_kawagoe-3_20261005.html").read_text(encoding="utf-8")
    html = html.replace("<h4>", "<h5>").replace("</h4>", "</h5>")
    res = _run("city_kawagoe-3", html)
    assert res.animals == [] and not res.empty_confirmed


def test_kawagoe_3_new_animal_next_to_decided_ones_is_read():
    html = (FIX / "t519_kawagoe-3_20261005.html").read_text(encoding="utf-8")
    mark = '<p><strong class="red">譲渡が決まりました</strong></p>'
    i = html.find("R5―犬No.12")
    j = html.find(mark, i)
    html = html[:j] + html[j + len(mark):]
    res = _run("city_kawagoe-3", html)
    assert [(a["management_no"], a["species"]) for a in res.animals] == [("R5―犬No.12", "dog")]


# --- 川口市 譲渡 --------------------------------------------------------------------------------------------------
def test_kawaguchi_2_photo_only_gallery_blocks_are_not_animals_and_age_label_variant_is_read():
    res = _run("city_kawaguchi-2", _fx("kawaguchi-2_20250504"))
    assert [a["management_no"] for a in res.animals] == ["R6-0020(右の白猫)", "R6-0026", "R6-0031", "R7-0001"]
    assert all(a["image_url"] and a["sex"] and a["breed"] for a in res.animals)
    by = {a["management_no"]: a for a in res.animals}
    assert by["R6-0026"]["age"] == "推定2歳" and by["R7-0001"]["age"] == "推定2歳"
    assert by["R6-0031"]["age"] == "推定10歳以上"


def test_kawaguchi_2_two_cats_in_one_block_is_a_known_limit_second_cat_lands_in_the_first_note():
    # エンジンは 1 ブロック 1 行。R6-0021 は別の子として出ず、1 頭目の備考に項目が入る（掲載漏れの限界。修正にはエンジン側の対応が要る）
    res = _run("city_kawaguchi-2", _fx("kawaguchi-2_20250504"))
    assert "R6-0021" not in [a["management_no"] for a in res.animals]
    assert "R6-0021" in res.animals[0]["note"]


def test_kawaguchi_2_dogs_cats_and_the_trial_heading_inside_a_block():
    res = _run("city_kawaguchi-2", _fx("kawaguchi-2_20260814"))
    assert [(a["management_no"], a["species"]) for a in res.animals] == [
        ("R8-0013", "dog"), ("R8-0014", "dog"), ("R8-0007", "cat"), ("R8-0009", "cat"), ("R8-0010", "cat"), ("R8-0011", "cat"),
        ("R8-0015", "cat"), ("R8-0016", "cat"), ("R8-0017", "cat"), ("R8-0019", "cat"), ("R8-0020", "cat"), ("R8-0021", "cat")]
    assert all(a["image_url"] for a in res.animals)
    assert res.dropped == []


def test_kawaguchi_2_trial_heading_in_a_cat_block_does_not_blank_the_species_of_the_cats_after_it():
    html = _fx("kawaguchi-2_20260814")
    soup = BeautifulSoup(html, "lxml")
    trial = next(h for h in soup.find_all("h3") if "トライアル中" in h.get_text() and h.find("strong"))
    trial.extract()
    cats = [b for b in soup.select("div.cmstag") if "R8-0009" in b.get_text()]
    cats[0].select_one("div.textAreaHtml").insert(0, trial)    # トライアル中の猫（R8-0009）の後ろに猫が続く日
    res = _run("city_kawaguchi-2", str(soup))
    assert [a["species"] for a in res.animals if a["management_no"] in ("R8-0010", "R8-0011", "R8-0021")] == ["cat", "cat", "cat"]
    assert [a["species"] for a in res.animals if a["management_no"] in ("R8-0013", "R8-0014")] == ["dog", "dog"]


def test_kawaguchi_2_old_layout_zero_sentence_is_zero():
    html = "<html><body><div id='contents-in'><h2>犬</h2><p>現在、譲渡できる犬はいません。（令和5年1月5日時点）</p><h2>猫</h2><p>現在、譲渡できる猫はいません。（令和5年1月5日時点）</p></div></body></html>"
    res = _run("city_kawaguchi-2", html)
    assert res.animals == [] and res.empty_confirmed


# --- 埼玉県 -------------------------------------------------------------------------------------------------------
def test_center_honsho_template_with_only_the_number_filled_is_not_an_animal():
    res = _run("pref_saitama_center_honsho", _fx("center_honsho_20250328_template"))
    assert res.animals == [] and res.empty_confirmed


def test_template_with_the_number_filled_and_the_date_left_as_spaced_year_month_day_is_not_an_animal():
    # 「2025年月日」でなく「2025年 月 日」「2025年　月　日」と空けて書く日があるので、番号だけ入った雛形を同じく動物にしない（2回目の追加。保存ページの雛形を書き換えて確認）
    base = _fx("center_honsho_20250328_template")
    assert "年月日" in base
    for blank in ("年 月 日", "年　月　日"):
        res = _run("pref_saitama_center_honsho", base.replace("年月日", blank))
        assert res.animals == [] and res.empty_confirmed, blank


def test_zero_day_sentences_2021_to_2023_cat_and_dog_wordings():
    # 2回目の追加: 「現在、収容猫情報はありません」（南支所 2021）「現在、収容犬はいません」（本庄 2021）「現在、収容犬の情報は有りません」（本庄 2023）
    for slug, fx in (("pref_saitama_center_minami", "center_minami_20210624_zero"),
                     ("pref_saitama_honjo", "honjo_20210925_zero"), ("pref_saitama_honjo", "honjo_20231130_zero")):
        res = _run(slug, _fx(fx))
        assert res.animals == [] and res.empty_confirmed, fx


def test_management_number_with_a_branch_number_keeps_both_parts_so_two_cats_do_not_share_a_number():
    # 動物指導センター本所 2022-09: 「2022-9-002」「2022-9-001」の 2 頭。番号を「2022-9」で切ると 2 頭とも同じ管理番号になる
    res = _run("pref_saitama_center_honsho", _fx("center_honsho_20220913_two_cats"))
    assert sorted(a["management_no"] for a in res.animals) == ["2022-9-001", "2022-9-002"]
    assert len({a["id"] for a in res.animals}) == 2


def test_zero_day_sentences_vary_by_office_and_period():
    assert _run("pref_saitama_nanbu", _fx("nanbu_20250719_zero")).empty_confirmed        # 「現在、収容犬の情報はありません。」
    assert _run("pref_saitama_sayama", _fx("sayama_20260417_zero")).empty_confirmed      # 「新着情報はありません。」
    assert _run("pref_saitama_honjo", _fx("honjo_20230306_zero")).empty_confirmed        # 見出しが h1 だった 2023 年の作り
    for slug in ("pref_saitama_nanbu", "pref_saitama_sayama", "pref_saitama_honjo"):
        assert _run(slug, _fx({"pref_saitama_nanbu": "nanbu_20250719_zero", "pref_saitama_sayama": "sayama_20260417_zero",
                               "pref_saitama_honjo": "honjo_20230306_zero"}[slug])).animals == []


def test_zero_sentence_gone_and_template_gone_is_failed_not_zero():
    html = _fx("nanbu_20250719_zero").replace("現在、収容犬の情報はありません。", "ただいま調整中です。")
    res = _run("pref_saitama_nanbu", html)
    assert res.animals == [] and not res.empty_confirmed


# --- 埼玉県 動物指導センター・保健所（検証 2 回目の追加） ---------------------------------------------------------
def test_center_minami_cat_that_died_after_intake_is_not_listed_and_the_day_is_zero():
    # 2026-09-08 の南支所: 備考に「収容後死亡。」の子 1 頭だけ。亡くなった子は載せず、field_lacks なので 0 頭と確認される
    res = _run("pref_saitama_center_minami", _fx("center_minami_20260908_dead"))
    assert res.animals == [] and res.empty_confirmed


def test_center_minami_same_page_without_the_death_note_is_read_as_an_animal():
    html = _fx("center_minami_20260908_dead").replace("収容後死亡。", "")
    res = _run("pref_saitama_center_minami", html)
    assert [(a["management_no"], a["species"]) for a in res.animals] == [("2026-072", "cat")]


def test_breed_is_read_from_the_breed_row_not_from_the_animal_kind_row():
    # 朝霞・東松山は行見出しが「動物種類 | 犬」で、label「種類」だと品種が「犬」になる
    def page(kind_label: str) -> str:
        return (f"<html><body><div id='tmp_contents'><h2>新着情報</h2><p>【2026年10月5日更新】「収容犬2026-5」を掲載しています。</p>"
                "<p><img src='/images/1/a.jpg'></p><table><tbody>"
                "<tr><td>管理番号</td><td>2026-5</td></tr><tr><td>収容日</td><td>令和8年10月5日</td></tr>"
                "<tr><td>収容場所</td><td>朝霞市</td></tr>"
                f"<tr><td>{kind_label}</td><td>犬</td></tr><tr><td>大きさ</td><td>中</td></tr><tr><td>種類</td><td>柴</td></tr>"
                "<tr><td>性別</td><td>オス</td></tr><tr><td>毛色</td><td>茶</td></tr><tr><td>備考</td><td></td></tr>"
                "</tbody></table></div></body></html>")
    for slug, kind in (("pref_saitama_asaka", "動物種類"), ("pref_saitama_higashimatsuyama", "動物種類"), ("pref_saitama_nanbu", "動物種別")):
        res = _run(slug, page(kind))
        assert [(a["management_no"], a["breed"], a["sex"], a["color"]) for a in res.animals] == [("2026-5", "柴", "オス", "茶")], slug


def test_honjo_2024_four_cell_rows_keep_size_and_breed_apart():
    # 2024 年の本庄は 1 行 4 セル「大きさ | 大 | 種類 | 雑種」。列の位置で品種を読むと大きさ（大）を取る
    res = _run("pref_saitama_honjo", _fx("honjo_20241216_4col"))
    assert [_pick(a, "management_no", "size", "breed", "sex", "age", "color", "location") for a in res.animals] == [
        {"management_no": "2024-26", "size": "大", "breed": "雑種", "sex": "おす", "age": "8歳以上", "color": "茶白", "location": "本庄市今井"}]


# --- 川口市 譲渡（古い作り） -------------------------------------------------------------------------------------
def test_kawaguchi_2_2023_layout_with_spaced_labels_keeps_breed_sex_color_and_species_from_h2():
    res = _run("city_kawaguchi-2", _fx("kawaguchi-2_20230531"))
    assert [_pick(a, "management_no", "species", "breed", "sex", "color", "age") for a in res.animals] == [
        {"management_no": "R5-0002", "species": "cat", "breed": "雑種", "sex": "オス", "color": "白黒", "age": "10歳以上"},
        {"management_no": "R5-0003", "species": "cat", "breed": "雑種", "sex": "メス", "color": "白黒", "age": "10歳以上"}]


def test_kawaguchi_2_2022_layout_reads_breed_from_the_kind_label_and_dog_from_h2():
    res = _run("city_kawaguchi-2", _fx("kawaguchi-2_20220309"))
    assert [_pick(a, "management_no", "species", "breed", "sex", "age") for a in res.animals] == [
        {"management_no": "R3-0029", "species": "dog", "breed": "チワワ", "sex": "オス(去勢済み)", "age": "15歳(推定)"}]


def test_kawaguchi_2_2024_zero_day_both_h2_sections_say_nobody():
    res = _run("city_kawaguchi-2", _fx("kawaguchi-2_20240528_zero"))
    assert res.animals == [] and res.empty_confirmed


# --- 川口市 迷子・保護動物（link_only → recipe。子ページのリンクを辿る・empty_absent） --------------------------------
def _run_k1(entry_html: str, child_html: str | None):
    src = _source("city_kawaguchi-1")
    recipe = Recipe.load(ROOT / "recipes" / "city_kawaguchi-1.yaml")
    entry = Doc(url=src.url, html=entry_html, soup=BeautifulSoup(entry_html, "lxml"))
    docs = []
    if child_html is not None:
        docs = [Doc(url=src.url.rsplit("/", 1)[0] + "/39606.html", html=child_html, soup=BeautifulSoup(child_html, "lxml"))]
    return build(src, recipe, docs, [entry] + docs)


def test_kawaguchi_1_zero_day_has_only_the_notice_link_and_is_confirmed_by_absence():
    res = _run_k1(_fx("kawaguchi-1_20250605_zero"), None)
    assert res.animals == [] and res.empty_confirmed


def test_kawaguchi_1_day_with_an_animal_link_is_never_zero_even_if_the_child_cannot_be_read():
    res = _run_k1(_fx("kawaguchi-1_20220819_entry"), None)
    assert res.animals == [] and not res.empty_confirmed     # 子ページが読めなければ failed（通知）になり、0 頭には見せない


def test_kawaguchi_1_child_page_is_one_dog_with_species_from_the_h1_and_the_photo_only_block_is_skipped():
    res = _run_k1(_fx("kawaguchi-1_20220819_entry"), _fx("kawaguchi-1_20220819_child"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "species", "shelter_date", "location", "size", "breed", "sex", "color", "note") == {
        "species": "dog", "shelter_date": "令和4年8月19日", "location": "川口市戸塚", "size": "中型", "breed": "雑種", "sex": "オス",
        "color": "白茶", "note": "R4.8.19 武南警察署保護"}
    assert a["image_url"].endswith("2022-1-0008-1.jpg")


def test_kawaguchi_1_page_without_the_heading_is_failed_not_zero():
    html = _fx("kawaguchi-1_20250605_zero").replace("市が保護している動物の情報", "お知らせ")
    res = _run_k1(html, None)
    assert res.animals == [] and not res.empty_confirmed


def test_kawaguchi_1_cat_child_page_without_a_photo_is_still_listed_with_species_from_the_h1():
    res = _run_k1(_fx("kawaguchi-1_20220819_entry"), _fx("kawaguchi-1_20220302_cat_child"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "species", "shelter_date", "location", "breed", "sex", "color", "image_url") == {
        "species": "cat", "shelter_date": "令和4年3月2日", "location": "川口市芝", "breed": "雑種", "sex": "オス", "color": "茶白", "image_url": None}


def test_sakado_2022_old_layout_with_plain_number_row_is_read_as_an_animal():
    # 2022-08〜10 の旧い作り: h1「収容犬No.6」・表の見出しが「番号 | 6」（「管理番号」でない）
    res = _run("pref_saitama_sakado", _fx("sakado_20220808_old_layout"))
    assert [_pick(a, "management_no", "shelter_date", "location", "breed", "sex", "age", "color", "size", "species") for a in res.animals] == [
        {"management_no": "6", "shelter_date": "2022年8月1日", "location": "鳩山町楓ケ丘", "breed": "雑種", "sex": "メス", "age": "5~8才",
         "color": "茶", "size": "中型", "species": "dog"}]
    assert res.animals[0]["image_url"].endswith("img_2562.jpg")


def test_sakado_2022_12_template_with_no_number_is_not_an_animal():
    res = _run("pref_saitama_sakado", _fx("sakado_20221203_template"))
    assert res.animals == [] and res.empty_confirmed


def test_sakado_template_year_only_number_is_not_taken_as_a_three_digit_number():
    # 「2026-」（西暦だけ）から「202」を番号として取らない
    html = ("<html><body><div id='tmp_contents'><h2>新着情報</h2><p>【2026年8月18日更新】「現在収容情報はありません」</p><table><tbody>"
            "<tr><td>管理番号</td><td>2026-</td></tr><tr><td>収容日</td><td></td></tr></tbody></table></div></body></html>")
    res = _run("pref_saitama_sakado", html)
    assert res.animals == [] and res.empty_confirmed


def test_zero_day_sentences_found_in_wayback_2021_to_2024():
    assert _run("pref_saitama_sakado", _fx("sakado_20211202_zero")).empty_confirmed               # 「現在、収容動物情報はありません。」
    assert _run("pref_saitama_center_honsho", _fx("center_honsho_20240715_zero")).empty_confirmed   # 「現在、情報はありません。」
    assert _run("pref_saitama_higashimatsuyama", _fx("higashimatsuyama_20240524_zero")).empty_confirmed   # 「現在収容犬情報は、ありません。」
