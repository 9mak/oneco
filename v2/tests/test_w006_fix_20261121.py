"""T656 直し 2 回目（2026-11-21・ネットワークなし）。agy の全項目の監査の高・中の指摘のうち、実ページで裏取りして本当に誤りだったもの。

fixture は 2026-11-21 に取った実ページ（script・style を落とした）。
"""

from pathlib import Path

from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _animals(c: Collected) -> list[dict]:
    assert c.status == "ok", c.error
    assert c.result is not None
    return c.result.animals


# --- 1. 船橋市 -3・-4: 表に「動物種」列が増えた（列ずれ） ------------------------------------------------------------
FN_FX = "w006_city_funabashi-3_20261121.html"


def test_funabashi_3_reads_columns_by_header_after_the_species_column_was_added():
    animals = _animals(_run("city_funabashi-3", _fx(FN_FX)))
    assert [(a["species"], a.get("breed"), a["color"], a["sex"], a["size"], a["shelter_date"], a["location"]) for a in animals] == [
        ("cat", None, "茶トラ", "オス", "小", "令和8年9月25日", "前貝塚町"),
        ("cat", None, "茶白", "オス", "中", "令和8年9月21日", "東船橋"),
        ("cat", None, "キジ", "メス", "小", "令和8年10月23日", "習志野台")]
    assert animals[1]["note"] == "推定8歳程度去勢済 届出日：令和8年10月19日"
    assert animals[0]["note"] == "届出日：令和8年10月19日"


def test_funabashi_4_reads_columns_by_header_after_the_species_column_was_added():
    animals = _animals(_run("city_funabashi-4", _fx(FN_FX)))
    assert [(a["species"], a.get("breed"), a["color"], a["sex"], a["size"]) for a in animals] == [
        ("cat", None, "白", "メス", "小"),
        ("cat", "ロシアンブルー", "グレー", "メス", "小"),
        ("cat", None, "黒", "メス", "小"),
        ("cat", "ベンガル", "ブラウンレオパード (ロゼット模様 )", "オス", "小"),
        ("cat", "ブリティッシュショートヘアー", "ブラウンティックドタビー", "オス", "小"),
        ("cat", "ペルシャ", "茶", "オス", "小")]
    assert "MC装着" in animals[1]["note"] and animals[1]["note"].endswith("届出日：令和8年11月4日")


# --- 2. 宮崎市 -1: 「令和8年11月15日保護分（猫・雑種）」の猫が dog になっていた ------------------------------------------
MZ_BASE = "https://www.city.miyazaki.miyazaki.jp/life/pet/protection/"
MZ_CATS = ("419466", "419500", "419672")
MZ_DOG = "419730"


def _miyazaki1(overrides: dict[str, str] | None = None) -> Collected:
    ids = (*MZ_CATS, MZ_DOG)
    index = "<html><body><ul>" + "".join(f'<li><a href="/life/pet/protection/{i}.html">記事{i}保護分</a></li>' for i in ids) + "</ul></body></html>"
    pages = {SOURCES["city_miyazaki-1"].url: index}
    for i in ids:
        pages[f"{MZ_BASE}{i}.html"] = (overrides or {}).get(i) or _fx(f"w006_city_miyazaki-1_{i}_20261121.html")
    return collect_one(SOURCES["city_miyazaki-1"], FakeFetcher(pages))


def test_miyazaki_1_reads_cats_as_cats_and_keeps_the_note_after_the_protection_number():
    animals = _animals(_miyazaki1())
    by_no = {a["management_no"]: a for a in animals}
    assert [a["species"] for a in animals] == ["cat", "cat", "cat", "dog"]
    cat = by_no["第2号104"]
    assert (cat["breed"], cat["color"], cat["sex"], cat["note"]) == ("雑種", "キジ白", "メス", "頚部外傷、左半身麻痺")
    assert by_no["第2号105"]["note"] == "頚部外傷" and by_no["第2号107"]["note"] == "外傷、左前肢骨折"
    dog = by_no["第3号58"]
    assert (dog["breed"], dog["color"], dog["note"]) == ("柴犬", "黒茶", None)   # 備考が保護番号だけの犬は note なし（管理番号と二重にしない）


def test_miyazaki_1_a_real_note_before_the_protection_number_is_still_the_note():
    html = _fx(f"w006_city_miyazaki-1_{MZ_DOG}_20261121.html")
    assert "<p>保護番号　第3号58</p>" in html
    swapped = html.replace("<p>保護番号　第3号58</p>", "<p>人なつこい</p>\n<p>保護番号　第3号58</p>")
    animals = _animals(_miyazaki1({MZ_DOG: swapped}))
    dog = next(a for a in animals if a["species"] == "dog")
    assert (dog["management_no"], dog["note"]) == ("第3号58", "人なつこい")


# --- 3. 広島県 -1・-2: 「センター収容日：<日付>。<場所>で<月日>に保護されました。」の書き方 ----------------------------------
HS_FX = "w006_pref_hiroshima-1_20261121.html"
HS_OLD = "センター収容日：令和8年11月10日。尾道市因島土生町で11月９日に保護されました。"


def test_hiroshima_1_location_is_the_place_not_the_sentence_after_it():
    (a,) = _animals(_run("pref_hiroshima-1", _fx(HS_FX)))
    assert (a["management_no"], a["breed"], a["sex"], a["shelter_date"]) == ("1HD20260255", "雑種", "雄", "令和8年11月10日")
    assert a["location"] == "尾道市因島土生町"
    assert a["note"] == "搬入時、首輪とリードが着いていました。"


def test_hiroshima_1_older_forms_still_read_the_place():
    html = _fx(HS_FX)
    assert HS_OLD in html
    for text, place in (
        ("センター収容日：令和8年10月30日に世羅郡世羅町で保護されました。", "世羅郡世羅町"),               # 10/31 の書き方
        ("センターに収容された日：令和8年10月30日<br/>保護された状況：世羅郡世羅町で保護されました。", "世羅郡世羅町"),   # 従来の 2 行
        ("センターに収容された日：令和8年10月30日<br/>保護された状況：令和8年10月29日に世羅郡世羅町で発見されました。", "世羅郡世羅町")):
        (a,) = _animals(_run("pref_hiroshima-1", html.replace(HS_OLD, text)))
        assert a["location"] == place, text


def test_hiroshima_1_a_value_starting_with_hogo_or_hanso_is_not_a_place():
    html = _fx(HS_FX)
    (a,) = _animals(_run("pref_hiroshima-1", html.replace(HS_OLD, "センター収容日：令和8年11月10日に保護されました。")))
    assert a.get("location") is None


def test_hiroshima_2_cat_page_reads_the_same_new_form():
    html = _fx(HS_FX).replace("迷い犬", "迷い猫").replace("雑種、推定12歳、雄", "雑種、推定2歳、雌")
    (a,) = _animals(_run("pref_hiroshima-2", html))
    assert (a["management_no"], a["sex"], a["shelter_date"], a["location"]) == ("1HD20260255", "雌", "令和8年11月10日", "尾道市因島土生町")


# --- 12. 鳥取県 -3: 問合番号 05-04（番号に P が付かない）が載っていない ----------------------------------------------------------
TT_FX = "w006_pref_tottori-3_20261121.html"


def test_tottori_3_reads_the_notice_without_a_p_in_its_number_by_its_section():
    by = {a["management_no"]: a for a in _animals(_run("pref_tottori-3", _fx(TT_FX)))}
    assert list(by) == ["P08-005", "P08-004", "P08-003", "P08-002", "P07-002", "P07-001", "P05-01", "P05-03", "05-04", "P05-06"]
    a = by["05-04"]
    assert a["species"] == "cat" and a["shelter_date"] == "R6年1月7日" and a["location"].startswith("鳥取市青谷町青谷")


def test_tottori_2_lost_does_not_pick_up_the_notice_of_the_sheltered_section():
    animals = _animals(_run("pref_tottori-2", _fx(TT_FX)))
    nos = [a["management_no"] for a in animals]
    assert "05-04" not in nos and not any(n.startswith("P") for n in nos) and len(nos) == 38


# --- 11. 八戸市 -1: クサガメの species が空 ----------------------------------------------------------------------------------
def test_hachinohe_1_a_turtle_is_other():
    (a,) = _animals(_run("city_hachinohe-1", _fx("w006_city_hachinohe-1_20261121.html")))
    assert (a["breed"], a["species"], a["color"]) == ("クサガメ", "other", "黒")


def test_hachinohe_1_cats_dogs_and_other_turtle_words():
    html = _fx("w006_city_hachinohe-1_20261121.html")
    assert "クサガメ" in html
    for word, species in (("猫", "cat"), ("犬", "dog"), ("イシガメ", "other"), ("ミドリガメ", "other"), ("かめ", "other")):
        (a,) = _animals(_run("city_hachinohe-1", html.replace("クサガメ", word)))
        assert a["species"] == species, word


# --- 10. 宮崎市 -4〜-7: 迷子・保護の場所が空になる書き方と、掲載番号の 9 桁 --------------------------------------------------------
def _miyazaki(slug: str, html: str) -> list[dict]:
    return _animals(_run(slug, html))


def test_miyazaki_4_lost_cat_place_after_the_time_and_nine_digit_listing_number():
    animals = _miyazaki("city_miyazaki-4", _fx("w006_city_miyazaki-4_20261121.html"))
    by = {a["management_no"]: a for a in animals}
    assert len(animals) == 34
    assert by["20260719"]["location"] == "本郷北方のちびっこ広場周辺"
    assert "202502212" in by and by["202502212"]["location"] == "宮崎市橘通東5丁目(宮銀本店近く)"   # 9 桁の番号が 8 桁に切れていた（20250221 と同じ番号が 2 頭）
    assert by["20250221"]["location"] == "宮崎市細江"
    assert len({a["id"] for a in animals}) == 34   # 20260524 は掲載元が同じ番号を 2 頭に付けている（別の届け出）。ID は写真から決まり別になる
    assert sum(1 for a in animals if a["management_no"] == "20260524") == 2
    assert [a["location"] for a in animals if not a.get("location")] == []   # 今日の迷子猫に場所が空の子は残らない


def test_miyazaki_5_lost_dog_place_after_a_time_range():
    by = {a["management_no"]: a for a in _miyazaki("city_miyazaki-5", _fx("w006_city_miyazaki-5_20261121.html"))}
    assert by["20250704"]["location"] == "吉村町西田甲"      # 「夕方から夜にかけて、吉村町西田甲より行方不明です」
    assert by["20261006"]["location"] == "宮崎市大字赤江" and by["20261007"]["location"] == "宮崎市大字鏡洲"


def test_miyazaki_6_sheltered_cat_place_before_de_hogo():
    by = {a["management_no"]: a for a in _miyazaki("city_miyazaki-6", _fx("w006_city_miyazaki-6_20261121.html"))}
    assert by["20260107"]["location"] == "宮崎市柳丸町"      # 「令和7年12月23日、宮崎市柳丸町で保護しました」
    assert by["20250804"]["location"] == "清武町木原付近"    # 「令和7年6月上旬から、清武町木原付近で保護してます」
    assert by["20250725"]["location"] == "大島町"           # 「令和7年7月23日から、大島町で保護しています」
    assert by["20261105"]["location"] == "宮崎市清武町今泉甲"   # 従来の「より、…で保護」


def test_miyazaki_7_sheltered_dog_place_before_de_hogo():
    html = ('<html><body><article class="body"><div class="imgRTxtL clearfix"><div><img src="/fs/1/2/3/_/a.jpg"/></div>'
            "<p>犬保護情報20261120</p><p>柴犬、茶、オス、成齢</p><p>令和8年11月18日、宮崎市大字有田で保護しました。</p></div>"
            '<div class="imgRTxtL clearfix"><div><img src="/fs/1/2/3/_/b.jpg"/></div>'
            "<p>犬保護情報202611212</p><p>雑種、白、メス</p><p>令和8年11月20日から、清武町木原付近で保護しています。</p></div></article></body></html>")
    a, b = _miyazaki("city_miyazaki-7", html)
    assert (a["management_no"], a["location"]) == ("20261120", "宮崎市大字有田")
    assert (b["management_no"], b["location"]) == ("202611212", "清武町木原付近")


# --- 9. 倉敷市: note が「特徴」の最初の空白で切れる ----------------------------------------------------------------------
KU_URL = "https://www.city.kurashiki.okayama.jp/kurashi/pet/1013042/1028461.html"
KU_FX = "w006_city_kurashiki_1028461_20261121.html"


def _kurashiki(html: str) -> list[dict]:
    from bs4 import BeautifulSoup
    recipe = Recipe.load(ROOT / "recipes" / "city_kurashiki.yaml")
    docs = [Doc(url=KU_URL, html=html, soup=BeautifulSoup(html, "lxml"))]
    return build(SOURCES["city_kurashiki"], recipe, docs, docs).animals


def test_kurashiki_note_keeps_the_whole_feature_line():
    (a,) = _kurashiki(_fx(KU_FX))
    assert a["note"] == "首輪なし 右後肢負傷"
    assert (a["management_no"], a["species"], a["breed"], a["color"], a["sex"], a["location"]) == ("1028461", "dog", "雑種", "茶", "メス", "児島通生")


def test_kurashiki_place_breed_and_color_with_a_space_are_not_cut():
    html = _fx(KU_FX)
    for old, new in (("<li>保護場所：児島通生</li>", "<li>保護場所：児島 通生　付近</li>"),
                     ("<li>種類：雑種</li>", "<li>種類：雑種（柴　系）</li>"),
                     ("<li>毛色：茶</li>", "<li>毛色：茶　白</li>")):
        assert old in html
        html = html.replace(old, new)
    (a,) = _kurashiki(html)
    assert (a["location"], a["breed"], a["color"]) == ("児島 通生 付近", "雑種(柴 系)", "茶 白")


def test_kurashiki_two_animals_on_one_page_are_still_split():
    html = _fx("w006c_kurashiki_1028185_20261107.html")
    (a,) = _kurashiki(html)
    assert (a["sex"], a["color"]) == ("メス、オス", "白茶、茶色")
    assert a["note"] and a["location"]


# --- 8. 仙台市アニパル -3: K26097 の性別が「白茶」、毛色が「避妊雌」（掲載元の書き間違い） ---------------------------------------------
SD_FX = "w006_city_sendai-3_20261121.html"


def test_sendai_3_swaps_the_sex_and_color_that_the_page_wrote_the_wrong_way_round():
    animals = _run("city_sendai-3", _fx(SD_FX))
    by = {a["management_no"]: a for a in _animals(animals)}
    assert len(by) == 7
    assert (by["K26097"]["sex"], by["K26097"]["color"]) == ("避妊雌", "白茶")
    assert [(a["sex"], a["color"]) for k, a in by.items() if k != "K26097"] == [
        ("去勢雄", "キジ白"), ("去勢雄", "黒白"), ("避妊雌", "サビ"), ("避妊雌", "キジ白"), ("去勢雄", "黒"), ("去勢雄", "キジ白")]


def test_sendai_3_rows_written_the_right_way_round_are_unchanged():
    html = _fx(SD_FX)
    td = '<td style="text-align: center;">'
    assert f"{td}白茶</td>\n{td}避妊雌</td>" in html
    fixed = html.replace(f"{td}白茶</td>\n{td}避妊雌</td>", f"{td}避妊雌</td>\n{td}白茶</td>")
    by = {a["management_no"]: a for a in _animals(_run("city_sendai-3", fixed))}
    assert (by["K26097"]["sex"], by["K26097"]["color"]) == ("避妊雌", "白茶")


# --- 7. 長崎犬猫ネット -1: 里親募集のページなのに sheltered・収容場所が空の子の場所が「問い合わせ先」になる ----------------------------------
NAG = "https://animal-net.pref.nagasaki.jp"


def _nagasaki1(detail: str) -> Collected:
    lst = '<html><body><div class="list-area"><a href="/animal/no-20198/">No.20198</a></div></body></html>'
    none = '<html><body><div class="list-area"><p>投稿がありません</p></div></body></html>'
    pages = {f"{NAG}/syuuyou/?animal-type=dog": lst, f"{NAG}/syuuyou/?animal-type=cat": none,
             f"{NAG}/syuuyou/?animal-type=others": none, f"{NAG}/animal/no-20198/": detail}
    return collect_one(SOURCES["animal_net_nagasaki-1"], FakeFetcher(pages))


def test_nagasaki_1_is_an_adoption_list_and_an_empty_place_is_not_the_contact_heading():
    s = SOURCES["animal_net_nagasaki-1"]
    assert s.kind == "adoption" and "募集中一覧" in s.name and "保健所収容" in s.name
    (a,) = _animals(_nagasaki1(_fx("w006_animal_net_nagasaki-1_no20198_20261121.html")))
    assert (a["management_no"], a["species"], a["breed"], a["sex"], a["color"], a["size"]) == ("20198", "dog", "ミックス(雑種)", "オス", "白黒", "小")
    assert a.get("location") is None and a.get("shelter_date") is None   # 収容場所・収容日は空欄。「問い合わせ先」を場所にしない


def test_nagasaki_1_a_real_place_is_still_read():
    html = _fx("w006_animal_net_nagasaki-1_no20198_20261121.html")
    assert "<p>収容場所</p>\n<p></p>" in html
    (a,) = _animals(_nagasaki1(html.replace("<p>収容場所</p>\n<p></p>", "<p>収容場所</p>\n<p>長崎市</p>")))
    assert a["location"] == "長崎市"


# --- 6. 鹿児島県 -2・-8・-9・-10: 「※新しい飼い主さんが決まりました」の 26D0219 が載っていた ------------------------------------
KG_FX = "w006_pref_kagoshima-9_20261121.html"   # 保健所・動物管理所の譲渡対象犬（1 ページ目）。-2・-8・-10 も同じ行の作り


def _kagoshima(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    from bs4 import BeautifulSoup
    return build(SOURCES[slug], recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))]).animals


def test_kagoshima_drops_the_dog_whose_new_owner_is_decided():
    html = _fx(KG_FX)
    assert "※新しい飼い主さんが決まりました" in html
    for slug in ("pref_kagoshima-2", "pref_kagoshima-8", "pref_kagoshima-9", "pref_kagoshima-10"):
        nos = [a["management_no"] for a in _kagoshima(slug, html)]
        assert "26D0219" not in nos and len(nos) >= 5, slug
    assert "26D0219" in [a["management_no"] for a in _kagoshima("pref_kagoshima-9", html.replace("※新しい飼い主さんが決まりました", "※"))]


def test_kagoshima_keeps_rows_that_only_say_a_new_owner_will_be_decided_later():
    html = _fx(KG_FX)
    kept = _kagoshima("pref_kagoshima-9", html.replace("※新しい飼い主さんが決まりました", "※里親さんが決まりましたら、掲載を終了します"))
    assert "26D0219" in [a["management_no"] for a in kept]
    kept = _kagoshima("pref_kagoshima-9", html.replace("※新しい飼い主さんが決まりました", "※譲渡が決まりましたら掲載を終了します"))
    assert "26D0219" in [a["management_no"] for a in kept]


# --- 5. 茨城県 PDF -2・-3: 「おうちに帰れたワン！」の返還済みの子（26-0835）が載っていた ----------------------------------------
IB_PDF = "https://www.pref.ibaraki.jp/hokenfukushi/doshise/hogo/documents/kouhyou1111.pdf"


def _ibaraki(slug: str, text: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(SOURCES[slug], recipe, [Doc(url=IB_PDF, pdf_text=text, pdf_tables=[])]).animals


def test_ibaraki_pdf_drops_the_returned_dog_whose_banner_text_is_broken():
    text = _fx("w006_pref_ibaraki_pdf-2_returned_wb20261119.txt")   # 11/19 の公表 PDF（掲載元にはもう無い）。バナーの文字が「雑種帰れた犬ワ猫種ン！」と崩れる
    assert "26-0835" in text and "帰れた犬ワ猫種ン" in text and "帰れたワン" not in text
    for slug in ("pref_ibaraki_pdf-2", "pref_ibaraki_pdf-3"):   # -3 は同じ形式の PDF（子犬・子猫）。同じ本文で確かめる
        animals = _ibaraki(slug, text)
        assert [a["management_no"] for a in animals] == ["26-0834"], slug
        assert (animals[0]["species"], animals[0]["breed"], animals[0]["location"]) == ("dog", "雑種", "笠間市平町")


def test_ibaraki_pdf_keeps_a_dog_without_the_banner():
    text = _fx("w006_pref_ibaraki_pdf-2_returned_wb20261119.txt").replace("雑種帰れた犬ワ猫種ン！", "雑種 犬猫種")
    assert [a["management_no"] for a in _ibaraki("pref_ibaraki_pdf-2", text)] == ["26-0834", "26-0835"]


# --- 4. 一宮市 -1: PDF の保護場所が折り返す（「一宮市」/「今伊勢町」/「宮後」の 3 行）と、品種・毛色・性別が空になる ---------------------
IC_PDF = "https://www.city.ichinomiya.aichi.jp/_res/projects/default_project/_page_/001/036/506/1109sagasicyuu.pdf"
IC_HEAD = "番号 写 真 保護日 保護場所 種類 毛色 性別 成犬・子犬 首輪等\n"


def _ichinomiya(text: str):
    recipe = Recipe.load(ROOT / "recipes" / "city_ichinomiya-1.yaml")
    return build(SOURCES["city_ichinomiya-1"], recipe, [Doc(url=IC_PDF, pdf_text=text, pdf_tables=[])]).animals


def test_ichinomiya_1_joins_the_wrapped_place_and_reads_breed_color_sex_from_the_sex_word():
    (a,) = _ichinomiya(_fx("w006_city_ichinomiya-1_pdf_20261109.txt"))
    assert {k: a.get(k) for k in ("species", "management_no", "shelter_date", "location", "breed", "color", "sex", "age", "note")} == {
        "species": "dog", "management_no": "1 2026.11.9", "shelter_date": "2026.11.9", "location": "今伊勢町宮後",
        "breed": "シー・ズー", "color": "白・薄茶", "sex": "めす", "age": "成犬", "note": "なし"}


def test_ichinomiya_1_the_place_split_before_and_after_the_number_line_is_joined():
    # Wayback 2022-05 の PDF の折り返し（日付の行の前に「浅井町小日比」、後ろに「野」）を再現した合成。日付の行に場所の語が無い
    text = IC_HEAD + "浅井町小日比\n1 2022.5.9 雑種 キジ白 オス 成猫 無\n野\n飼い主の方を探しています。\nご連絡ください。"
    (a,) = _ichinomiya(text)
    assert (a["location"], a["breed"], a["color"], a["sex"], a["species"]) == ("浅井町小日比野", "雑種", "キジ白", "オス", "cat")


def test_ichinomiya_1_two_rows_each_take_their_own_wrapped_lines():
    text = (IC_HEAD + "一宮市\n1 2026.11.9 今伊勢町 シー・ズー 白・薄茶 めす 成犬 なし\n宮後\n"
            "一宮市\n2 2026.11.9 浅井町 雑種 黒 おす 成犬 青首輪\n小日比野\n飼い主の方を探しています。\nお心当たりのある方は一宮市動物愛護事務所まで\nご連絡ください。")
    a, b = _ichinomiya(text)
    assert (a["location"], a["breed"], a["management_no"]) == ("今伊勢町宮後", "シー・ズー", "1 2026.11.9")
    assert (b["location"], b["breed"], b["color"], b["sex"], b["management_no"]) == ("浅井町小日比野", "雑種", "黒", "おす", "2 2026.11.9")


def test_ichinomiya_1_a_row_without_a_wrapped_line_does_not_take_the_page_notice_as_its_place():
    text = IC_HEAD + "1 2026.11.9 今伊勢町 シー・ズー 白・薄茶 めす 成犬 なし\n飼い主の方を探しています。\nご連絡ください。"
    (a,) = _ichinomiya(text)
    assert a["location"] == "今伊勢町"
