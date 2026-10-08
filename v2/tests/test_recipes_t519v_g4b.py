"""T519 検証 g4b: 埼玉県の個人保護（-2）・譲渡（joto）・高崎市・藤沢市のレシピを、Wayback Machine の別の日の保存ページに当てた確認（ネットワークなし）。

fixture（tests/fixtures/t519v_g4b_*.html）は保存ページの本文だけを抜いたもの（先頭のコメントに保存の時刻）。
- 藤沢市: 動物が載った日（2020-09-24 は 6 頭、2020-11-01 は 1 頭）は表でなく「<strong>収容犬1<img></strong>収容日：…<br>…」の裸の文字。0 頭の日の言い方は 2019〜2023 は「現在、収容犬はありません。」、2024 以降は「【現在、収容犬はありません】」
- 高崎市: 0 頭の日は「見出しの行だけ」（2025-08-05 の一般保護犬）・「見出し + 空欄の th の行」（2024-06-02 の保護犬）・「見出し + 空の p を持つ td の行」（2024-04-14 の保護犬）の 3 通り
- 埼玉県 譲渡: 決まった子の印は「飼い主さんが決まりました!」「飼主さんが 決まりました！」「譲渡されました！」「譲渡になりました！」と時期で変わる。「お見合い中」「マッチング中」「お声がかかりました！（現在募集を停止しています）」の子は決まっていないので載せる
- 埼玉県 個人保護: 0 頭の日の言い方が「現在、保護犬情報はありません」（2019）「新着情報はありません」（本所 2025）「現在、掲載を希望する迷子猫の保護情報はありません」（本所 2023）などに変わる
- 藤沢市（2 回目の検証）: 動物が載った日の作りは 2019〜2022 の保存で 6 通り（裸の文字 / 見出しの p と本文の p / 本文の p だけ / 表 / 見出しの strong と本文の p / 見出しが b）。どれも「収容日：」の p・表・hr の次の strong を起点に読む
- 埼玉県 譲渡（2 回目の検証）: 決まった子の印に「譲渡となりました」もある。見出し（h2）に印が付く日もある（本所の猫 2026-06）。南支所の犬には南支所の問合せ先を付ける
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(slug: str, html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fx(name: str) -> str:
    return (FIX / f"{name}.html").read_text(encoding="utf-8")


# --- 藤沢市 ---------------------------------------------------------------------------
def test_fujisawa_six_dogs_in_bare_text_each_keep_their_own_photo_and_number():
    res = _run("city_fujisawa-1", _fx("t519v_g4b_fujisawa_animals6_20200924"))
    assert [a["name"] for a in res.animals] == [f"収容犬{i}" for i in range(1, 7)]
    assert [a["image_url"].rsplit("/", 1)[1] for a in res.animals] == [f"hp_dogno{i}.jpg" for i in range(1, 7)]
    a = res.animals[0]
    assert (a["species"], a["breed"], a["color"], a["sex"], a["size"], a["shelter_date"], a["location"], a["note"]) == (
        "dog", "トイ・プードル", "茶", "メス", "小", "9月24日", "辻堂西海岸3丁目", "首輪:無し")
    last = res.animals[5]
    assert (last["breed"], last["color"], last["sex"]) == ("チワワ", "茶白", "メス")
    assert len({a["id"] for a in res.animals}) == 6


def test_fujisawa_one_dog_inside_a_paragraph_takes_the_first_photo_not_the_collar_photo():
    res = _run("city_fujisawa-1", _fx("t519v_g4b_fujisawa_animal1_20201101"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["image_url"].endswith("/hp1.jpg")
    assert (a["breed"], a["color"], a["sex"], a["size"], a["shelter_date"], a["location"]) == ("雑種", "茶", "オス", "大", "10月29日", "打戻")


def test_fujisawa_zero_days_old_new_and_today_are_zero_not_failed():
    for name in ("t519v_g4b_fujisawa_zero_old_20190824", "t519v_g4b_fujisawa_zero_2023_20230402", "t519_fujisawa-1_20261006"):
        res = _run("city_fujisawa-1", _fx(name))
        assert res.animals == [] and res.empty_confirmed, name


def test_fujisawa_zero_day_strong_is_not_an_animal_and_unreadable_animal_day_is_failed():
    # 0 頭の日の strong「【現在、収容犬はありません】」は収容日が無いので行にならない。文言も消えて収容日の無い strong だけの日は読めなかった扱い
    html = _fx("t519_fujisawa-1_20261006")
    assert "【現在、収容犬はありません】" in html
    res = _run("city_fujisawa-1", html.replace("【現在、収容犬はありません】", "<strong>収容犬1</strong>調整中"))
    assert res.animals == [] and not res.empty_confirmed


# --- 高崎市 ---------------------------------------------------------------------------
def test_takasaki_zero_days_with_three_different_empty_shapes_are_zero():
    for slug, name in (("city_takasaki-3", "t519v_g4b_takasaki-3_20250805"),      # 見出しの行だけ
                       ("city_takasaki-1", "t519v_g4b_takasaki-1_20240602"),      # 見出し + 空欄の th の行
                       ("city_takasaki-1", "t519v_g4b_takasaki-1_20240414")):     # 見出し + 空の p を持つ td の行
        res = _run(slug, _fx(name))
        assert res.animals == [] and res.empty_confirmed, name


def test_takasaki_header_only_table_with_one_text_row_is_failed_not_zero():
    html = _fx("t519v_g4b_takasaki-3_20250805").replace("</tbody>", "<tr><td>調整中</td></tr></tbody>", 1)
    assert "調整中" in html
    res = _run("city_takasaki-3", html)
    assert res.animals == [] and not res.empty_confirmed


def test_takasaki_lost_cat_with_an_approximate_date_keeps_the_place_and_the_month():
    res = _run("city_takasaki-6", (FIX / "t519_takasaki-6.html").read_text(encoding="utf-8"))
    a = next(x for x in res.animals if x["management_no"] == "2025-107")
    assert a["shelter_date"] == "令和8年3月中旬" and a["location"] == "吉井町下長根"


# --- 埼玉県 譲渡 ----------------------------------------------------------------------
def _names(res):
    return [a["name"] for a in res.animals]


def test_joto_inu_matching_and_paused_recruiting_are_kept_decided_is_dropped():
    # 2023-03: あいちゃん「お見合い中です。」・千代丸「希望者が多数ありましたので、募集を停止します。」は決まっていないので載せる（トライアル中と同じ扱い）
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20230327"))
    assert _names(res) == ["マーブル", "ゆり", "はる", "あいちゃん", "さぬき", "千代丸"]
    # 2026-06: 「マッチング中です！」「マッチング中です！（募集を停止しています）」は載せる。「譲渡になりました！」は載せない
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20260616"))
    assert _names(res) == ["ガリバー", "キャビン", "コロ"]


def test_joto_inu_decided_with_another_wording_is_dropped():
    # 2024-09: 「飼い主さんが決まりました！」（決まった子）。以前の「譲渡されました」だけの除外では載ってしまった
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20240908"))
    assert "カレン" not in _names(res) and len(res.animals) == 5


def test_joto_neko_minami_decided_cats_of_every_wording_are_zero_and_confirmed():
    # 2025-03: 3 頭とも「飼主さんが 決まりました！」+ 管理番号の欄が空の雛形の表 2 つ → 0 頭（以前は決まった 3 頭が募集中として載った）
    res = _run("pref_saitama_joto_neko_minami", _fx("t519v_g4b_saitama_joto_neko_minami_20250327"))
    assert res.animals == [] and res.empty_confirmed
    # 2026-08: 「譲渡されました！」2 頭は載せない。「お声がかかりました！（現在募集を停止しています。）」の 1 頭（仮名: こま）は決まっていないので載せる
    res = _run("pref_saitama_joto_neko_minami", _fx("t519v_g4b_saitama_joto_neko_minami_20260805"))
    assert _names(res) == ["こま"]
    # 全部「譲渡されました！」なら 0 頭
    res = _run("pref_saitama_joto_neko_minami", _fx("t519v_g4b_saitama_joto_neko_minami_20260805").replace("お声がかかりました！", "譲渡されました！"))
    assert res.animals == [] and res.empty_confirmed


def test_joto_neko_minami_one_open_cat_among_decided_ones_is_kept():
    # 2023-02: 4 頭が「飼い主さんが決まりました!」、1 頭（南2022-C35）は印なし = 募集中
    res = _run("pref_saitama_joto_neko_minami", _fx("t519v_g4b_saitama_joto_neko_minami_20230201"))
    assert [a["management_no"] for a in res.animals] == ["南2022-C35"]


def test_joto_cat_with_all_marks_missing_and_structure_broken_is_failed_not_zero():
    # 決まった印だけが残って表の構造が変わった日（管理番号の欄が取れない）は 0 頭に見せない
    html = _fx("t519v_g4b_saitama_joto_neko_minami_20250327").replace("管理番号", "番号")
    res = _run("pref_saitama_joto_neko_minami", html)
    assert res.animals == [] and not res.empty_confirmed


# --- 埼玉県 個人保護 ------------------------------------------------------------------
def test_kojin_dog_zero_day_with_the_2019_wording_is_zero():
    for name, slug in (("t519v_g4b_saitama_chichibu-2_20190823", "pref_saitama_chichibu-2"),   # 現在、保護犬情報はありません。
                       ("t519v_g4b_saitama_kazo-2_20190819", "pref_saitama_kazo-2")):          # 表が無い日
        res = _run(slug, _fx(name))
        assert res.animals == [] and res.empty_confirmed, name


def test_kojin_dog_animal_days_are_read():
    res = _run("pref_saitama_asaka-2", _fx("t519v_g4b_saitama_asaka-2_20191002"))
    a = res.animals[0]
    assert (a["management_no"], a["shelter_date"], a["location"], a["breed"], a["sex"], a["size"], a["color"]) == (
        "2019-58", "2019年9月13日", "富士見市鶴馬", "雑種", "オス", "中", "茶色")
    assert a["image_url"].endswith("/images/2019-58.jpg")
    res = _run("pref_saitama_chichibu-2", _fx("t519v_g4b_saitama_chichibu-2_20200805"))
    assert [a["management_no"] for a in res.animals] == ["2020-3"]
    res = _run("pref_saitama_kumagaya-2", _fx("t519v_g4b_saitama_kumagaya-2_20201020"))
    assert [(a["management_no"], bool(a["image_url"])) for a in res.animals] == [("2020-66", False), ("2020-71", True), ("2020-72", False)]


def test_kojin_cat_center_zero_days_with_the_2023_and_2025_wording_are_zero():
    for name in ("t519v_g4b_saitama_center_honsho-2_20231208", "t519v_g4b_saitama_center_honsho-2_20250209"):
        res = _run("pref_saitama_center_honsho-2", _fx(name))
        assert res.animals == [] and res.empty_confirmed, name


def test_kojin_cat_minami_three_cats_each_have_their_own_photo():
    res = _run("pref_saitama_center_minami-2", _fx("t519v_g4b_saitama_center_minami-2_20240420"))
    assert [a["location"] for a in res.animals] == ["ふじみ野市市沢", "川口市芝新町", "久喜市南栗橋"]
    assert [a["image_url"].rsplit("/", 1)[1] for a in res.animals] == ["huzimino1.jpg", "kawaguti1.jpg", "060221kukihogoneko.jpg"]


def test_kojin_cat_honsho_uses_either_label_for_the_number_and_reads_h_numbers():
    # 2019-03 の本所は番号の欄の見出しが「管理番号」（今は「受付番号」）。4 頭が載っていたのに行が 1 つも取れなかった
    res = _run("pref_saitama_center_honsho-2", _fx("t519v_g4b_saitama_center_honsho-2_20190330"))
    assert [a["management_no"] for a in res.animals] == ["H30-91", "H30-89", "H30-81", "H30-80"]      # 平成 30 年度の番号「H30-91」（年が 2 桁）も読む
    assert [a["location"] for a in res.animals] == ["坂戸市四日市場", "深谷市菅沼", "羽生市砂山", "深谷市新井"]
    # 2021-06: 「H2021-05-001」（年の後ろに 2 つ番号が付く）は途中で切らず全部取る
    res = _run("pref_saitama_center_honsho-2", _fx("t519v_g4b_saitama_center_honsho-2_20210622"))
    assert [a["management_no"] for a in res.animals] == ["H2021-05-001"]


def test_kojin_cat_zero_day_template_footer_phone_number_is_not_a_management_number():
    # 雛形の表の最後の行（問合せ先 電話：048-536-2465）を番号と取り違えて 1 頭と数えない
    res = _run("pref_saitama_center_honsho-2", _fx("t519v_g4b_saitama_center_honsho-2_20231208"))
    assert res.animals == [] and res.empty_confirmed


# --- 2 回目の検証で足した確認 -------------------------------------------------------
def test_fujisawa_every_animal_day_layout_seen_in_wayback_is_read_with_its_photo():
    cases = (
        ("t519v_g4b_fujisawa_p_pair_20191203", "inu.jpg", "アイリッシュ・セター", "11月25日", "辻堂東海岸4丁目"),     # 見出しの p（strong + 写真）→ 本文の p
        ("t519v_g4b_fujisawa_p_20200428", "hpdog.jpg", "ジャック・ラッセル・テリア", "4月28日", "長後"),            # 本文の p の中に写真
        ("t519v_g4b_fujisawa_table_20201201", "1127hpdog.jpg", "雑種", "11月27日", "長後"),                       # 表（1 行 2 列）
        ("t519v_g4b_fujisawa_strong_p_20210124", "hpdog.jpg", "柴犬", "1月20日", "長後"),                         # 見出しの strong（写真）→ 本文の p
        ("t519v_g4b_fujisawa_bold_20220831", "hpdog.jpg", "雑種", "8月30日", "辻堂東海岸4丁目"),                  # 見出しが strong でなく font + b
    )
    for name, photo, breed, date, place in cases:
        res = _run("city_fujisawa-1", _fx(name))
        assert len(res.animals) == 1, name
        a = res.animals[0]
        assert a["image_url"].endswith("/dobutsu/images/" + photo), name
        assert (a["species"], a["breed"], a["shelter_date"], a["location"]) == ("dog", breed, date, place), name


def test_fujisawa_the_bulletin_board_map_is_never_taken_as_a_dogs_photo():
    # 公示の掲示板案内図（.../dobutsu/images/000148492.jpg）は犬の写真ではない。写真の無い犬が前の兄弟を遡って拾わない
    import re
    html = re.sub(r"<img[^>]*hpdog\.jpg[^>]*/>", "", _fx("t519v_g4b_fujisawa_p_20200428"))
    assert "hpdog" not in html and "000148492" in html
    res = _run("city_fujisawa-1", html)
    assert len(res.animals) == 1 and not res.animals[0]["image_url"]


def test_takasaki_2_species_is_decided_by_the_kind_column_only():
    # 特徴欄の「犬に襲われた」で猫を犬にしない。種類の欄に猫・犬の語が無い子は種別なし
    import re
    base = (FIX / "t519_takasaki-2.html").read_text(encoding="utf-8")
    blank = re.search(r"<tr>\s*<td.*?</tr>", base, re.S)
    assert blank
    for kind, memo, want in (("猫・雑種", "犬に襲われた", "cat"), ("犬・柴", "", "dog"), ("雑種", "", None)):
        row = f"<tr><td>2026-1 {memo}</td><td>令和8年10月1日</td><td>{kind}</td><td></td><td>メス</td><td>高崎町</td></tr>"
        res = _run("city_takasaki-2", base.replace(blank.group(0), row, 1))
        assert [a["species"] for a in res.animals] == [want], kind


def test_joto_inu_decided_wording_adopted_by_a_new_owner_is_dropped():
    # 2020-10: 「新しい飼い主さんへ譲渡となりました」の子（ライト）と「飼い主さんが決まりました！」の子 → 0 頭
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20201026"))
    assert res.animals == [] and res.empty_confirmed
    # 2020-06: 「飼い主さんが決まりました」の子（2020-D-001）は載せず、「お見合い中のため募集を一時停止します」の子（ライト）は決まっていないので載せる
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20200608"))
    assert [a["management_no"] for a in res.animals] == ["2020-3-001"]


def test_joto_inu_south_branch_dog_carries_the_south_branch_contact():
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20260616"))
    by = {a["name"]: a for a in res.animals}
    assert by["コロ"]["note"].endswith("問合せ先: 動物指導センター 南支所(さいたま市桜区在家473、電話:048-855-0484)")
    assert by["ガリバー"]["note"].endswith("電話:048-536-2465)")


def test_joto_inu_old_layout_zero_days_are_zero():
    # 2019-09: 表の見出しが「管理 番号」（空白入り）で、「しつけ等の訓練中のためすぐに譲渡できる状況ではありません」と書く日
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20190916"))
    assert res.animals == [] and res.empty_confirmed


def test_joto_neko_honsho_mark_on_the_section_heading_drops_the_cat():
    # 2026-06: 見出し「譲渡用猫情報（センター本所） 新しい飼い主さんが決まりました！」で、表の管理番号の欄には印が無い（フラン）→ 0 頭
    res = _run("pref_saitama_joto_neko_honsho", _fx("t519v_g4b_saitama_joto_neko_honsho_20260711"))
    assert res.animals == [] and res.empty_confirmed
    # 見出しの印が無ければ載る（印は見出しにしか無い）
    res = _run("pref_saitama_joto_neko_honsho", _fx("t519v_g4b_saitama_joto_neko_honsho_20260711").replace('<span class="txt_red">新しい飼い主さんが決まりました！</span>', ""))
    assert [a["name"] for a in res.animals] == ["フラン"]


def test_joto_old_numbers_keep_the_serial_part():
    # 2019〜2020 の「2019-09-001」「南-2020-10-001」は末尾の連番まで取る（途中で切ると 2 頭が同じ番号になる）
    res = _run("pref_saitama_joto_neko_honsho", (FIX / "t519v_g4b_saitama_joto_neko_honsho_20260711.html").read_text(encoding="utf-8")
               .replace('<span class="txt_red">新しい飼い主さんが決まりました！</span>', "").replace("2026-C-001", "2019-09-001"))
    assert [a["management_no"] for a in res.animals] == ["2019-09-001"]


def test_joto_neko_minami_ids_with_a_letter_are_read_not_dropped_as_a_template():
    # 「南2026-C67」のように連番の前に英字が付く番号を、空欄の雛形と取り違えて捨てない
    res = _run("pref_saitama_joto_neko_minami", _fx("t519v_g4b_saitama_joto_neko_minami_20260805").replace("譲渡されました！", "お見合い中です"))
    assert [a["management_no"] for a in res.animals] == ["南2026-C10", "南2026-C11", "南2026-C37"]


def test_kojin_cat_zero_day_wording_of_2020_to_2022_is_zero():
    for slug, name in (("pref_saitama_center_honsho-2", "t519v_g4b_saitama_center_honsho-2_20250209"), ("pref_saitama_center_minami-2", "t519v_g4b_saitama_center_honsho-2_20250209")):
        for wording in ("現在、情報はありません", "現在情報はありません", "現在、掲載情報はありません"):
            res = _run(slug, _fx(name).replace("新着情報はありません", wording))
            assert res.animals == [] and res.empty_confirmed, (slug, wording)


def test_joto_inu_name_is_cut_before_the_status_words_even_without_a_space():
    # 2024-09: 見出しが「きなこ飼い主さん募集中です!」（空白なし）。名前に「飼い主さん募集中です!」を付けない。読み（次元(じげん)）は名前に残す
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20240908"))
    assert "きなこ" in _names(res) and "ポンタ" in _names(res)
    assert not any("募集中" in n or "お見合い" in n for n in _names(res))
    # 2020-06: 「名前:ライト(お見合い中のため募集を一時停止します)」
    res = _run("pref_saitama_joto_inu", _fx("t519v_g4b_saitama_joto_inu_20200608"))
    assert _names(res) == ["ライト"]
