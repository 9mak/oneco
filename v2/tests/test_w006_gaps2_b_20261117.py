"""W006 T640 掲載漏れ 2 回目 B: 市民の掲示板のうち迷子（2026-11-17・ネットワークなし）。

おまえさん決定: 飼い主が探している迷子（lost）と、市民が保護している迷子（sheltered）は載せる。飼えなくなった飼い主からの譲渡（新しい飼い主さがし・出会い広場など）は載せない。
- 写真: lost は飼い主が届けた写真なので photo: no（町田の前例）。sheltered は千葉市・旭川の前例どおりホストの規約で決める（無断転載禁止だけなら ok・事前相談が要るホストは pending）。
- 前橋市（行方不明一覧 lost・市民保護一覧 sheltered）・鳥取県（捜しています lost・保護しています sheltered）・船橋市（個人等で保護している動物 sheltered と、同じページの迷子動物 lost）・
  宮崎市（迷子の猫・犬を探しています lost・迷子の猫・犬を保護しています sheltered）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def _by_species(c: Collected) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in c.result.animals:
        out[a["species"]] = out.get(a["species"], 0) + 1
    return out


# --- 前橋市 ---------------------------------------------------------------
MB_LOST, MB_SHELTERED = "city_maebashi-2", "city_maebashi-3"


def test_maebashi_registry():
    s = SOURCES[MB_LOST]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, "lost", "mixed", "群馬県")
    assert s.photo == "no" and s.phone == "027-220-5777" and s.recipe_path.exists()  # 飼い主が届けた写真は出さない
    s = SOURCES[MB_SHELTERED]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, "sheltered", "mixed", "群馬県")
    assert s.photo == "pending" and s.phone == "027-220-5777" and s.recipe_path.exists()  # 前橋市の規約は転載要申請（事前相談の要るホスト）


def test_maebashi_lost_today_reads_6_dogs_27_cats_and_3_birds():
    html = _fx("w006_city_maebashi-2_20261117.html")
    c = _run(MB_LOST, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 36 and _by_species(c) == {"dog": 6, "cat": 27, "other": 3}
    assert len({a["id"] for a in animals}) == 36
    first = animals[0]
    assert (first["management_no"], first["shelter_date"], first["location"], first["breed"], first["sex"], first["age"], first["color"]) == (
        "YD2026-10-01", "2026年9月26日", "小坂子町", "雑種(柴犬系)", "オス", "10歳", "茶")
    assert "尻尾の毛がない" in first["note"] and "革製青色" in first["note"]
    by = {a["management_no"]: a for a in animals}
    # 行方不明の日時に時刻・午前午後・朝などが付いても、場所だけを取る
    assert by["YD2026-09-04"]["location"] == "吉岡町漆原" and by["YD2026-09-02"]["location"] == "伊勢崎市下植木町"
    assert by["Y2026-11-07"]["location"] == "青柳町" and by["Y2026-10-13"]["location"] == "柏倉町"
    assert by["Y2026-11-09"]["species"] == "other" and by["Y2026-11-10"]["species"] == "cat"


def test_maebashi_lost_other_day_in_wayback():
    c = _run(MB_LOST, _fx("w006_city_maebashi-2_child_wb20260616.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 13 and _by_species(c) == {"dog": 4, "cat": 9}


def test_maebashi_sheltered_today_reads_8_cats_1_dog_and_drops_the_lizard_nobody_keeps():
    html = _fx("w006_city_maebashi-3_20261117.html")
    assert "保護はしていない" in html   # トカゲ（A2026-08-02）は見かけただけで、誰も保護していない
    c = _run(MB_SHELTERED, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 9 and _by_species(c) == {"cat": 8, "dog": 1}
    first = animals[0]
    assert (first["management_no"], first["shelter_date"], first["location"], first["breed"], first["sex"], first["age"]) == (
        "A2026-11-02", "2026年10月中旬", "天川原町2丁目", "雑種(シャム系)", "オス", "成猫")
    # kind が sheltered（保護中）なので、「保護はしていない」と書かれた行は載せない（#130 reviewer F-02）
    assert all(a["management_no"] != "A2026-08-02" for a in animals)
    assert sum(1 for a in animals if a["image_url"]) == 2  # 写真があるのは 2 件


def test_maebashi_sheltered_other_day_in_wayback():
    c = _run(MB_SHELTERED, _fx("w006_city_maebashi-3_child_wb20250206.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 5 and _by_species(c) == {"cat": 4, "dog": 1}


def test_maebashi_zero_only_when_the_frame_is_there_and_no_row_is():
    # 0 頭の日の版は Wayback に見つからない。今日の保存ページから動物の行・写真を消して再現する
    for slug, name in ((MB_LOST, "w006_city_maebashi-2_20261117.html"), (MB_SHELTERED, "w006_city_maebashi-3_20261117.html")):
        soup = BeautifulSoup(_fx(name), "lxml")
        for tr in soup.select("table tbody tr"):
            if tr.select("td"):
                tr.decompose()
        zero = str(soup)
        assert _zero(_run(slug, zero)), slug
        # 受付番号の書き方が変わった日（行は読める）は 0 頭にしない
        assert not _zero(_run(slug, _fx(name).replace("(Y", "（Y").replace("(A", "（A"))), slug
        # 枠の見出しが変わった日も 0 頭にしない
        assert not _zero(_run(slug, zero.replace("一覧】", "】")))


# --- 船橋市 ---------------------------------------------------------------
FN_SHELTERED, FN_LOST = "city_funabashi-3", "city_funabashi-4"
FN_FX = "w006_city_funabashi-3_20261117.html"   # 1 つのページに保護動物（個人等が保護）と迷子動物（飼い主が探している）の 2 つの表がある


def test_funabashi_registry():
    s = SOURCES[FN_SHELTERED]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, "sheltered", "mixed", "千葉県")
    assert s.photo == "ok" and s.phone == "047-435-3916" and "潮見町" in s.address and s.recipe_path.exists()  # CC BY・無断転載禁止
    s = SOURCES[FN_LOST]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, "lost", "mixed", "千葉県")
    assert s.photo == "no" and s.phone == "047-435-3916" and s.url == SOURCES[FN_SHELTERED].url and s.recipe_path.exists()


def test_funabashi_sheltered_today_reads_the_3_cats_kept_by_private_people():
    html = _fx(FN_FX)
    assert "これらの動物は動物愛護指導センターに収容されている動物ではありません" in html
    c = _run(FN_SHELTERED, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["species"], a["shelter_date"], a["location"], a["color"], a["sex"], a["size"]) for a in animals] == [
        ("cat", "令和8年9月25日", "前貝塚町", "茶トラ", "オス", "小"),
        ("cat", "令和8年9月21日", "東船橋", "茶白", "オス", "中"),
        ("cat", "令和8年10月23日", "習志野台", "キジ", "メス", "小")]
    assert "推定8歳程度去勢済" in animals[1]["note"] and "尾が長く" in animals[2]["note"]
    assert [bool(a["image_url"]) for a in animals] == [True, False, True] and len({a["id"] for a in animals}) == 3


def test_funabashi_lost_today_reads_the_3_cats_their_owners_are_looking_for():
    c = _run(FN_LOST, _fx(FN_FX))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["species"], a["shelter_date"], a["location"], a["color"]) for a in animals] == [
        ("cat", "令和8年10月14日", "習志野市新栄", "白"),
        ("cat", "令和8年10月25日", "小室町", "グレー"),
        ("cat", "令和8年10月8日", "新高根", "黒")]
    assert "ロシアンブルー" in animals[1]["note"] and "MC装着" in animals[1]["note"]


def test_funabashi_other_days_in_wayback():
    c = _run(FN_SHELTERED, _fx("w006_city_funabashi-3_child_wb20250716.html"))
    assert c.status == "ok" and len(c.result.animals) == 1, c.error
    c = _run(FN_LOST, _fx("w006_city_funabashi-3_child_wb20250716.html"))
    assert c.status == "ok" and len(c.result.animals) == 6 and all(a["species"] == "cat" for a in c.result.animals), c.error
    c = _run(FN_LOST, _fx("w006_city_funabashi-3_child_wb20260526.html"))
    assert c.status == "ok" and len(c.result.animals) == 8, c.error
    assert [a["species"] for a in c.result.animals].count("other") == 4   # オカメインコ 2・セキセイインコ 2 は犬猫以外
    assert "本郷町" in [a["location"] for a in c.result.animals]   # 「令和8年5月9日本郷町」のように日付と場所の間に空白が無くても場所を取る


def test_funabashi_zero_only_when_the_table_is_there_and_has_no_animal_row():
    # 0 頭の日の版は Wayback に見つからない。今日の保存ページから表の動物の行を消して再現する
    for slug, caption in ((FN_SHELTERED, "保護動物一覧"), (FN_LOST, "迷子動物一覧")):
        soup = BeautifulSoup(_fx(FN_FX), "lxml")
        for t in soup.select("table"):
            if caption in t.get_text():
                for tr in t.select("tr"):
                    if tr.select("td"):
                        tr.decompose()
        assert _zero(_run(slug, str(soup))), slug
        # 表の見出し（caption）が変わった日は 0 頭にしない
        changed = _fx(FN_FX).replace(caption, caption.replace("一覧", "リスト"))
        assert not _zero(_run(slug, changed)), slug


# --- 鳥取県 ペットを「捜しています」・「保護しています」 --------------------------------
TT_LOST, TT_SHELTERED = "pref_tottori-2", "pref_tottori-3"
TT_FX = "w006_pref_tottori-2_20261117.html"   # 1 つのページに「捜しています」と「保護しています」が年度ごとに並ぶ


def test_tottori_registry():
    s = SOURCES[TT_LOST]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture, s.contact_scope) == ("recipe", True, "lost", "mixed", "鳥取県", "operator")
    assert s.photo == "no" and s.phone == "0857-26-7593" and s.address and s.url == "https://www.pref.tottori.lg.jp/243905.htm" and s.recipe_path.exists()
    s = SOURCES[TT_SHELTERED]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture, s.contact_scope) == ("recipe", True, "sheltered", "mixed", "鳥取県", "operator")
    assert s.photo == "pending" and s.phone == "0857-26-7593" and s.url == SOURCES[TT_LOST].url and s.recipe_path.exists()  # 鳥取県の規約は転載要申請


def _tt_numbers(html: str, head: str) -> list[str]:
    """fixture の届け出の見出し（h4「問合番号M08-015」）から、頭が head の番号をページの順に拾う（レシピとは別に数える）。"""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for h in soup.select("div.BrowserItemList h4"):
        t = h.get_text(" ", strip=True)
        if t.startswith("問合番号" + head):
            out.append(t.removeprefix("問合番号").strip())
    return out


def test_tottori_lost_reads_every_notice_the_prefecture_still_lists():
    # おまえさん決定（2026-11-18）: 年度で絞らず、県が載せている届け出は全部出す（こちらで期間を決めない）
    html = _fx(TT_FX)
    c = _run(TT_LOST, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    want = _tt_numbers(html, "M")
    assert len(want) == 38 and "M07-001" in want and "M06-01" in want and "M32-07" in want
    assert [a["management_no"] for a in animals] == want
    assert {a["species"] for a in animals} <= {"cat", "dog", "other"}
    first = animals[0]
    assert first["management_no"] == "M08-015"
    assert first["shelter_date"] == "令和8年10月17日" and first["location"].startswith("ラム") and "全体的にグレー" in first["note"]
    assert animals[3]["location"] == "博労町駅付近" and "みーちゃん" in animals[3]["note"]


def test_tottori_sheltered_reads_every_notice_with_a_p_number():
    html = _fx(TT_FX)
    c = _run(TT_SHELTERED, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"] for a in animals] == ["P08-005", "P08-004", "P08-003", "P08-002", "P07-002", "P07-001", "P05-01", "P05-03", "P05-06"]
    # 令和5年度以前の「問合番号05-04」は頭に P が無く、捜している（M）か保護している（P）かを番号で決められないので読まない（1 件だけ）
    assert "問合番号05-04" in html and all(a["management_no"] != "05-04" for a in animals)
    assert animals[0]["location"] == "米子市米原" and animals[0]["shelter_date"] == "令和8年10月5日" and "1才くらい" in animals[0]["note"].replace("１", "1")


def test_tottori_older_versions_read_the_same_way():
    for name in ("w006_pref_tottori-2_child_wb20260215.html", "w006_pref_tottori-2_child_wb20251112.html"):
        html = _fx(name)
        c = _run(TT_LOST, html)
        assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == _tt_numbers(html, "M"), (name, c.error)
        c = _run(TT_SHELTERED, html)
        assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == _tt_numbers(html, "P"), (name, c.error)
    # 2025-11 の版は令和7年度の最初の 5 件が「問合番号07-018」のように M が付かない。番号で区分を決められないので読まない
    assert "問合番号07-018" in _fx("w006_pref_tottori-2_child_wb20251112.html")


def test_tottori_zero_only_when_every_section_says_there_is_no_notice():
    soup = BeautifulSoup(_fx(TT_FX), "lxml")
    for h4 in soup.select("div.BrowserItemList h4"):
        if "問合番号" in h4.get_text():
            h4.decompose()
    assert "現在、掲載情報はありません" in str(soup)
    for slug in (TT_LOST, TT_SHELTERED):
        assert _zero(_run(slug, str(soup))), slug
        # 節の見出しが無い日（作りが変わった）は 0 頭と言い切らない
        assert not _zero(_run(slug, str(soup).replace("しています（", "掲載（"))), slug
        # 問合番号の書き方が変わった日（届け出は残る）は 0 頭にしない
        assert not _zero(_run(slug, _fx(TT_FX).replace("問合番号", "問合 "))), slug


# --- 宮崎市 ---------------------------------------------------------------
MZ_LOST_CAT, MZ_LOST_DOG, MZ_SHELT_CAT, MZ_SHELT_DOG = "city_miyazaki-4", "city_miyazaki-5", "city_miyazaki-6", "city_miyazaki-7"


def test_miyazaki_registry():
    for slug, kind, species, photo in ((MZ_LOST_CAT, "lost", "cat", "no"), (MZ_LOST_DOG, "lost", "dog", "no"),
                                       (MZ_SHELT_CAT, "sheltered", "cat", "ok"), (MZ_SHELT_DOG, "sheltered", "dog", "ok")):
        s = SOURCES[slug]
        assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, kind, species, "宮崎県"), slug
        assert s.photo == photo and s.phone == "0985-85-6011" and s.recipe_path.exists(), slug  # 宮崎市の規約は無断転載禁止のみ。lost の写真は出さない
    assert SOURCES[MZ_LOST_CAT].url.endswith("/protection/109681.html") and SOURCES[MZ_LOST_DOG].url.endswith("/protection/57782.html")
    assert SOURCES[MZ_SHELT_CAT].url.endswith("/protection/109685.html") and SOURCES[MZ_SHELT_DOG].url.endswith("/protection/51360.html")


def _mz_numbers(html: str) -> list[str]:
    """fixture の届け出の先頭（「迷子猫情報:20261111」等）から掲載番号を拾う（レシピとは別に数える）。"""
    import re
    soup = BeautifulSoup(html, "lxml")
    out = []
    for d in soup.select("article.body div.imgRTxtL, article.body div.imgTxtL"):
        m = re.search(r"(?:迷子猫情報|迷子犬情報|猫保護情報|犬保護情報)\s*[:：]?\s*(\d{8})", d.get_text(" ", strip=True))
        if m:
            out.append(m.group(1))
    return out


def test_miyazaki_lost_cats_today_read_every_notice_the_city_still_lists():
    # おまえさん決定（2026-11-18）: 掲載の年で絞らず、市が載せている届け出は全部出す（ページは最長 6 か月と書くが 2024 年の掲載も残る）
    html = _fx("w006_city_miyazaki-4_20261117.html")
    assert "迷子猫情報:20250117" in html
    c = _run(MZ_LOST_CAT, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"][:8] for a in animals] == _mz_numbers(html) and len(animals) == 34
    assert all(a["species"] == "cat" for a in animals) and "20250117" in [a["management_no"] for a in animals]
    first = animals[0]
    assert (first["management_no"], first["breed"], first["sex"], first["age"], first["shelter_date"], first["location"]) == (
        "20261111", "雑種", "メス", "老齢", "令和8年11月10日", "船塚2丁目")
    assert "首輪なし、名前はジジ" in first["note"] and "温和な性格です" in first["note"]
    assert animals[2]["location"] == "大字小松にある「ハートフルケア小松」付近"
    assert len({a["id"] for a in animals}) == 34
    # 2 段落目が「種類＋毛色」、3 段落目が「性別＋年齢」の届け出もある（#130 reviewer F-06）
    gray = next(a for a in animals if a["management_no"] == "20260719")
    assert (gray["sex"], gray["breed"]) == ("オス", "雑種")
    # 掲載番号と種類が同じ段落にある届け出も、種類に番号を混ぜない
    assert next(a for a in animals if a["management_no"] == "20260609")["breed"] == "雑種"
    assert all(not a["breed"] or "情報" not in a["breed"] for a in animals)


def test_miyazaki_lost_dogs_today_read_the_notice_from_2025_too():
    html = _fx("w006_city_miyazaki-5_20261117.html")
    assert "迷子犬情報 20250704" in html
    c = _run(MZ_LOST_DOG, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    # ページの「迷子の犬を探している方へお願い」の枠は届け出ではないので読まない
    assert [a["management_no"] for a in animals] == ["20261106", "20261007", "20261006", "20250704"] and all(a["species"] == "dog" for a in animals)
    assert (animals[0]["breed"], animals[0]["sex"], animals[0]["age"], animals[0]["location"]) == (
        "トイ・プードル", "オス", "老齢", "宮崎市佐土原町下田島の「宮崎国際ゴルフ倶楽部」付近")
    assert animals[1]["shelter_date"] == "令和8年8月30日" and animals[2]["breed"] == "豆柴"


def test_miyazaki_sheltered_cats_today_read_this_years_ones_and_keep_the_wording_of_a_citizen_keeping_it():
    c = _run(MZ_SHELT_CAT, _fx("w006_city_miyazaki-6_20261117.html"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    html = _fx("w006_city_miyazaki-6_20261117.html")
    assert [(a["management_no"] or "")[:8] for a in animals] == _mz_numbers(html) and len(animals) == 12
    # 1 つの届け出の 2 枚目の写真だけが入った枠（20260302 の 202603022.jpg）は 1 頭として読まない
    assert "202603022.jpg" in html and all(a["management_no"] for a in animals)
    assert [a["management_no"] for a in animals][:8] == ["20261105", "20260916", "20260820", "20260518", "20260306-2", "20260306-1", "20260302", "20260107"]
    assert all(a["species"] == "cat" for a in animals)
    first = animals[0]
    assert (first["sex"], first["age"], first["shelter_date"], first["location"]) == ("メス", "老齢", "令和8年11月2日", "宮崎市清武町今泉甲")
    assert "とても人懐っこい" in first["note"] and animals[0]["image_url"]


def test_miyazaki_other_days_in_wayback():
    c = _run(MZ_LOST_CAT, _fx("w006_city_miyazaki-4_child_wb20260712.html"))
    assert c.status == "ok", c.error
    html = _fx("w006_city_miyazaki-4_child_wb20260712.html")
    numbered = [a for a in c.result.animals if a["management_no"]]
    assert [a["management_no"][:8] for a in numbered] == _mz_numbers(html)
    assert [a["management_no"] for a in numbered][:7] == ["20260626", "20260605", "20260524", "20260524", "20260518", "20260329", "20260313"]
    # この版は 20260609・20260608 の掲載番号が枠の外にある。番号なしでも中身のある届け出として読む（写真だけの枠は読まない）
    unnumbered = [a for a in c.result.animals if not a["management_no"]]
    assert [(a["sex"], a["shelter_date"]) for a in unnumbered] == [("オス", "令和8年6月6日"), ("メス", "令和8年6月5日")]
    # 先頭に空の段落がある届け出（20260329）も、種類と性別を取る
    calico = next(a for a in c.result.animals if a["management_no"] == "20260329")
    assert (calico["breed"], calico["sex"]) == ("雑種", "メス")
    assert all(not a["breed"] or "情報" not in a["breed"] for a in c.result.animals)
    html = _fx("w006_city_miyazaki-6_child_wb20260513.html")
    c = _run(MZ_SHELT_CAT, html)
    assert c.status == "ok" and [(a["management_no"] or "")[:8] for a in c.result.animals] == _mz_numbers(html), c.error


def test_miyazaki_sheltered_dog_zero_days_in_wayback():
    # 保護している犬のページの 0 頭の日は「現在、掲載情報はありません」（2025-11〜2026-07）・「※現在、掲載する犬の情報はありません」（2024-07。空の枠の div 付き）
    for name in ("w006_city_miyazaki-7_20261117.html", "w006_city_miyazaki-7_zero_wb20251108.html", "w006_city_miyazaki-7_zero_wb20260714.html",
                 "w006_city_miyazaki-7_zero_wb20240713.html"):
        assert _zero(_run(MZ_SHELT_DOG, _fx(name))), name
    # 子のいる日（猫のページ・迷子の犬のページ）にはこの文は出ない
    for name in ("w006_city_miyazaki-6_20261117.html", "w006_city_miyazaki-6_child_wb20260513.html", "w006_city_miyazaki-4_20261117.html",
                 "w006_city_miyazaki-4_child_wb20260712.html", "w006_city_miyazaki-5_20261117.html"):
        body = BeautifulSoup(_fx(name), "lxml").select_one("article.body").get_text(" ", strip=True)
        assert "現在、掲載情報はありません" not in body and "現在、掲載する" not in body, name


def test_miyazaki_zero_sentence_gone_is_not_zero():
    html = _fx("w006_city_miyazaki-7_20261117.html").replace("現在、掲載情報はありません", "掲載状況")
    assert not _zero(_run(MZ_SHELT_DOG, html))


def test_funabashi_real_zero_day_and_a_later_day_in_wayback():
    # 保護動物一覧が見出し行だけで動物の行が無い日（Wayback 2025-02）は 0 頭。同じ日に迷子動物一覧は 5 件ある（別の slug なので影響しない）
    html = _fx("w006_city_funabashi-3_zero_wb20250215.html")
    assert _zero(_run(FN_SHELTERED, html))
    c = _run(FN_LOST, html)
    assert c.status == "ok" and len(c.result.animals) == 5, c.error
    # 種類の欄が「雑種」だけで犬猫が書かれない日（Wayback 2026-08）は、犬猫以外にせず、毛色の語（キジトラ＝猫）で決め、決まらなければ種別なし
    c = _run(FN_SHELTERED, _fx("w006_city_funabashi-3_child_wb20260813.html"))
    assert c.status == "ok", c.error
    assert [(a["species"], a["breed"], a["color"]) for a in c.result.animals] == [("cat", "雑種", "キジトラ"), (None, "雑種", "黒白")]
