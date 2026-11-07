"""W006 全ページ監査 C 組（2026-11-07。ネットワークなし）。

Gemini の 1 次判定（軽い項目の欠け）を実ページで確かめて直したもの。fixture は 2026-11-07 の実ページの保存
（w006c_*）。レシピ本体 v2/recipes/<slug>.yaml をそのまま読む。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build, empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _animals(slug: str, html: str) -> list[dict]:
    c = _single(slug, html)
    assert c.status == "ok", (c.status, c.error)
    return c.result.animals


def _build(slug: str, pages: list[tuple[str, str]]):
    src, recipe = SOURCES[slug], Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    docs = [Doc(url=u, html=h, soup=BeautifulSoup(h, "lxml")) for u, h in pages]
    return build(src, recipe, docs, docs)


# --- 千葉市 city_chiba-1: 見出しが「毛色」から「色」に変わった（2026-11-07） --------------------------------

def test_chiba_lost_dog_reads_color_when_label_is_just_iro():
    (a,) = _animals("city_chiba-1", _fx("w006c_city_chiba-1_20261107.html"))
    assert a["color"] == "うす茶"
    assert (a["management_no"], a["breed"], a["sex"], a["size"]) == ("26110601", "パグ", "オス", "小")


def test_chiba_lost_dog_still_reads_old_label_keamo_iro():
    html = _fx("w006c_city_chiba-1_20261107.html").replace("色：うす茶", "毛色：うす茶")
    (a,) = _animals("city_chiba-1", html)
    assert a["color"] == "うす茶"


# --- 大阪市 city_osaka-3/-4: 体格「小（体重 約6.4kg）」・識別番号と仮名（h3） ---------------------------------

def test_osaka_adoption_dog_size_keeps_the_weight_and_reads_h3_number_and_name():
    animals = _animals("city_osaka-3", _fx("w006c_city_osaka-3_20261107.html"))
    assert len(animals) == 4
    first = animals[0]
    assert first["size"] == "小(体重 約6.4kg)"
    assert first["management_no"] == "8-3-12"
    assert first["name"] == "ジャックくん"
    assert [a["management_no"] for a in animals] == ["8-3-12", "8-3-14", "8-3-15", "8-3-16"]
    assert all(a["size"].startswith("小(体重") and a["size"].endswith("kg)") for a in animals)


# --- 岐阜県 spec_pref_gifu: 管理番号 67-29・毛色（毛の長さと取り違え） --------------------------------------

def test_gifu_management_no_with_hyphen_and_color_not_hair_length():
    res = _build("spec_pref_gifu", [
        ("https://www.pref.gifu.lg.jp/page/5229.html", _fx("w006c_gifu_5229_20261107.html")),
        ("https://www.pref.gifu.lg.jp/page/13689.html", _fx("w006c_gifu_13689_20261107.html")),
    ])
    by_loc = {a["location"]: a for a in res.animals}
    kamo = by_loc["美濃加茂市三和町地内"]
    assert kamo["management_no"] == "67-29"
    assert kamo["color"] == "茶黒白"
    takayama = by_loc["高山市清見町"]
    assert takayama["color"] == "こげ茶"      # 毛の長さ「短」ではない
    assert len(res.animals) == 2


# --- 倉敷市 city_kurashiki: 「性別および毛色：メス（白茶）、オス（茶色）」（2 匹の 1 ページ） ------------------

def test_kurashiki_combined_sex_and_color_line_is_split():
    (a,) = _build("city_kurashiki", [
        ("https://www.city.kurashiki.okayama.jp/kurashi/pet/1013042/1028185.html",
         _fx("w006c_kurashiki_1028185_20261107.html")),
    ]).animals
    assert a["sex"] == "メス、オス"
    assert a["color"] == "白茶、茶色"
    assert a["management_no"] == "1028185"


# --- 町田市 city_machida-3/-4: 「毛色黒と白（足は白）」（コロンなし）・毛色の中にコロン ----------------------

def test_machida_cat_color_without_colon():
    animals = _animals("city_machida-3", _fx("w006c_city_machida-3_20261107.html"))
    colors = {a["color"] for a in animals if a.get("color")}
    assert "黒と白(足は白)" in colors      # 全角の括弧は半角にそろえる（エンジン共通）
    assert "キジトラ(足は白)" in colors
    assert all(a.get("color") for a in animals if "足は白" in (a.get("note") or ""))


def test_machida_other_color_with_inner_colons():
    animals = _animals("city_machida-4", _fx("w006c_city_machida-4_20261107.html"))
    sinamon = [a for a in animals if a.get("breed") == "シナモン文鳥"]
    assert "頭頂部、尾羽:焦げ茶色 体:薄茶色 頬:白色" in [a.get("color") for a in sinamon]


# --- 熊本市 city_kumamoto-1: 保護日（「保護日時」でなく「保護日」） -------------------------------------------

def test_kumamoto_stray_dog_reads_hogobi():
    url = "https://www.city.kumamoto.jp/doubutuaigo/kiji00373472/index.html"
    (a,) = _build("city_kumamoto-1", [(url, _fx("w006c_kumamoto-1_kiji00373472_20261107.html"))]).animals
    assert a["shelter_date"] == "2026年10月21日"
    assert a["location"] == "北区 植木町亀甲"


# --- 横須賀市 yokosuka_doubutu-5/-4/-6: 年齢「推定1か月半齢」 -------------------------------------------------

def test_yokosuka_cat_age_in_months_half():
    url = "https://www.yokosuka-doubutu.com/adopted-animals-cat/26-212/"
    (a,) = _build("yokosuka_doubutu-5", [(url, _fx("w006c_yokosuka-5_26-212_20261107.html"))]).animals
    assert a["age"] == "1か月半齢"


# --- 福島県 pref_fukushima-1/-2: 「その他の特徴等」の値が 3 つ目のセルにある ---------------------------------

def test_fukushima_note_in_third_cell():
    animals = _animals("pref_fukushima-1", _fx("w006c_pref_fukushima-1_20261107.html"))
    assert len(animals) == 2
    first = next(a for a in animals if a["management_no"] == "s-081005-2")
    assert first["note"] == "※オレンジ色のリードはセンターで着用したものです。"
    second = next(a for a in animals if a["management_no"] == "s-081028-1")
    assert "note" not in second or not second["note"]


# --- 青森県 aomori_animal: 見出しが「備考」から「特徴」に変わった -----------------------------------------

def test_aomori_note_under_tokucho_heading():
    (a,) = _animals("aomori_animal", _fx("w006c_aomori_animal_20261107.html"))
    assert a["note"] == "黒色首輪、赤いワイヤーリード付"
    assert (a["breed"], a["color"], a["sex"], a["size"]) == ("雑種", "茶", "雄", "中型")


# --- 和歌山市 city_wakayama-2（迷子保護動物情報。新規） ---------------------------------------------------------

WK2 = "https://www.city.wakayama.wakayama.jp/kurashi/kenko_iryo/1009125/1035775/1034270.html"


def test_wakayama_stray_page_reads_the_small_dog():
    assert "city_wakayama-2" in SOURCES
    s = SOURCES["city_wakayama-2"]
    assert s.url == WK2 and s.kind == "stray" and s.photo == "pending"
    (a,) = _animals("city_wakayama-2", _fx("w006c_city_wakayama-2_20261107.html"))
    assert a["species"] == "dog"
    assert (a["management_no"], a["breed"], a["location"], a["sex"]) == ("2026-10-29-1", "小型犬", "平井", "メス")
    assert a["shelter_date"] == "2026年10月29日"
    assert a["note"] == "人懐っこい"
    assert a["image_url"].endswith("/_page_/001/034/270/2026-10-29-1.png")


def test_wakayama_stray_zero_day_is_empty_and_child_days_never_are():
    # Wayback 2026-07-12 は「現在、迷子動物情報はありません。」で figure が無い 0 頭の日
    c = _single("city_wakayama-2", _fx("w006c_city_wakayama-2_zero_wb20260712.html"))
    assert c.status == "empty" and c.result.animals == []
    recipe = Recipe.load(ROOT / "recipes" / "city_wakayama-2.yaml")
    for name in ("w006c_city_wakayama-2_20261107.html", "w006c_city_wakayama-2_child_wb20240523.html",
                 "w006c_city_wakayama-2_cats_wb20250218.html", "w006c_city_wakayama-2_children_wb20250926.html"):
        html = _fx(name)
        assert empty_hits(recipe, [Doc(url=WK2, html=html, soup=BeautifulSoup(html, "lxml"))]) == [], name


def test_wakayama_stray_past_child_days_read_species_and_fields():
    # Wayback の子がいた日。種類が「犬雑種」「猫雑種」「ヨークシャーテリア風」（犬猫の語なし → breed の語で犬）
    animals = _animals("city_wakayama-2", _fx("w006c_city_wakayama-2_children_wb20250926.html"))
    assert [(a["management_no"], a["species"]) for a in animals] == [
        ("2025-3-10-4", "dog"), ("2025-7-15-1", "dog"), ("2025-9-12-1", "dog"), ("2025-9-12-2", "cat"), ("2025-9-22-1", "dog")]
    (y,) = _animals("city_wakayama-2", _fx("w006c_city_wakayama-2_child_wb20240523.html"))
    assert y["breed"] == "ヨークシャーテリア風" and y["species"] == "dog" and y["note"] == "左目白濁"


def test_wakayama_stray_child_in_changed_markup_is_not_zero():
    # figure でなく p に包まれた写真に作りが変わった日は、0 頭にも 1 頭にもせず「読めなかった」にする
    html = _fx("w006c_city_wakayama-2_20261107.html").replace("<figure", "<div").replace("</figure>", "</div>")
    html = html.replace("<figcaption", "<span").replace("</figcaption>", "</span>")
    c = _single("city_wakayama-2", html)
    assert c.status != "empty"


# --- 奈良市 city_nara-2（飼い主さん募集中！犬・猫の譲渡。新規） --------------------------------------------------

NARA2 = "https://www.city.nara.lg.jp/soshiki/97/10799.html"


def test_nara_adoption_page_reads_photos_only():
    assert "city_nara-2" in SOURCES
    s = SOURCES["city_nara-2"]
    assert s.url == NARA2 and s.kind == "adoption" and s.photo == "pending"
    animals = _animals("city_nara-2", _fx("w006c_city_nara-2_20261107.html"))
    assert len(animals) == 13
    urls = [a["image_url"] for a in animals]
    assert len(set(urls)) == 13
    assert not any("284131" in u for u in urls)           # 愛護フェスティバルの告知画像は子ではない
    assert all(a.get("species") is None for a in animals)   # 種別の文字が無いので決めない
    assert not any(a.get("name") for a in animals)          # alt は「あ」「f」「エイズ」で名前とは限らない


def test_nara_adoption_page_wayback_2026_05_has_no_id_and_17_photos():
    animals = _animals("city_nara-2", _fx("w006c_city_nara-2_wb20260511.html"))
    assert len(animals) == 17
    assert len({a["image_url"] for a in animals}) == 17
