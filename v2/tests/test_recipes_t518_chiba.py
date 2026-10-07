"""T518 ③: 千葉市 -1/-2/-4/-6 を row_until でまとめる（ネットワークなし）。

fixture は実ページから本文（div#contents_editable）だけを抜いたもの。
- t518_chiba-1.html・t518_chiba-2.html・t518_chiba-4_empty.html・t518_chiba-6.html: 2026-10-05 の取得
- t518_chiba-1_empty_wb*.html・t518_chiba-4_wb20250906.html・t518_chiba-6_wb20250613.html: Wayback Machine の保存
  （-4 は 10/5 が 0 頭のため、犬が載っていた日の同じページで -5 と同じ作りであることを確かめる）
変更前は、-1/-2 が属性の p を行にしていて管理番号と写真が無く、-4/-6 は管理番号だけだった。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
IMG = "https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/images/"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fixture(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


# --- 千葉市 迷子犬: h4 管理番号 → p 写真 → p（収容日：…<br>収容場所：…<br>…特徴：）--------------------------------
def test_chiba_1_takes_number_photo_and_items():
    res = _run("city_chiba-1", _fixture("t518_chiba-1.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "management_no", "image_url", "species", "shelter_date", "location", "breed", "color", "sex", "size", "note") == {
        "management_no": "26093001", "image_url": IMG + "26093001.jpg", "species": "dog", "shelter_date": "令和8年9月30日",
        "location": "若葉区御殿町", "breed": "雑種", "color": "茶黒", "sex": "オス", "size": "中", "note": None}
    assert res.dropped == []


def test_chiba_1_values_with_spaces_stop_at_the_next_label():
    # 項目は 1 つの p に <br> 区切りで並ぶ（文字にすると空白区切り）。空白を含む値は次の「項目名：」の手前まで取る
    html = (_fixture("t518_chiba-1.html")
            .replace("収容場所：若葉区御殿町", "収容場所：若葉区御殿町　公園付近")
            .replace("毛色：茶黒", "毛色：茶　黒")
            .replace("特徴：</p>", "特徴：赤い首輪　人なれしている</p>"))
    a = _run("city_chiba-1", html).animals[0]
    assert _pick(a, "location", "color", "sex", "note") == {
        "location": "若葉区御殿町 公園付近", "color": "茶 黒", "sex": "オス", "note": "赤い首輪 人なれしている"}


def test_chiba_1_empty_days_are_zero_not_failed():
    # 0 頭の日の 2 通りの書き方（Wayback 2025-07-30: h4「現在、対象の動物はいません。」＋空の雛形、2025-11-10: h3「現在、迷い犬の情報はありません。」）
    for name in ("t518_chiba-1_empty_wb20250730.html", "t518_chiba-1_empty_wb20251110.html"):
        res = _run("city_chiba-1", _fixture(name))
        assert res.animals == [], name
        assert res.empty_confirmed, name


# --- 千葉市 迷子猫: -1 と同じ作り。2 頭目は写真が無い。末尾に空の h4 と「子猫の育成ボランティア」のバナー ---------------
def test_chiba_2_second_cat_has_no_photo_and_banner_is_not_an_animal():
    res = _run("city_chiba-2", _fixture("t518_chiba-2.html"))
    assert [a["management_no"] for a in res.animals] == ["26100101", "26092901"]
    first, second = res.animals
    assert first["image_url"] == IMG + "26100101.jpg"
    assert second["image_url"] is None          # 次の子・バナー（konekobosyu.gif）の写真を付けない
    assert _pick(first, "shelter_date", "location", "color", "sex", "size") == {
        "shelter_date": "令和8年10月1日", "location": "中央区末広", "color": "白うす茶", "sex": "メス", "size": "中"}
    assert _pick(second, "shelter_date", "location", "breed", "color", "sex") == {
        "shelter_date": "令和8年9月29日", "location": "若葉区若松町", "breed": "雑種", "color": "白", "sex": "オス"}
    assert res.dropped == []


# --- 千葉市 市民保護犬: -5 と同じ（h2 掲載日 → h4 番号 → p 写真（任意）→ p 保護日： …）。Wayback 2025-09-06 は 5 頭 --------
def test_chiba_4_groups_like_chiba_5():
    res = _run("city_chiba-4", _fixture("t518_chiba-4_wb20250906.html"))
    assert [a["management_no"] for a in res.animals] == ["B-5024", "B-5023", "B-5019", "B-5009", "B-5001"]
    b24, b23, b19, b09, b01 = res.animals
    assert b24["image_url"] == IMG + "maigodog.jpg" and b19["image_url"] == IMG + "b5019n.jpg"
    assert b23["image_url"] is None and b09["image_url"] is None and b01["image_url"] is None
    assert _pick(b23, "shelter_date", "location", "breed", "color", "sex", "size", "note") == {
        "shelter_date": "令和7年7月2日", "location": "四街道市鹿放が丘", "breed": "雑種", "color": "茶",
        "sex": "メス", "size": "中型", "note": "顔が柴犬、老犬"}
    assert b09["size"] is None                  # 「体格：」が空。次の「特徴：…」を値にしない
    assert b01["note"] == "紺色の首輪(汚れあり)、5歳~10歳程度、足と顔が茶色、人懐っこい、断尾"
    assert res.dropped == []


def test_chiba_4_empty_template_is_not_an_animal():
    # 0 頭の日は h2「現在情報はありません」の下に空の h4 と「保護日：令和年月日」の雛形が残る（2026-10-05）
    res = _run("city_chiba-4", _fixture("t518_chiba-4_empty.html"))
    assert res.animals == []
    assert res.empty_confirmed


# --- 千葉市 市民保護その他: -5 と同じ作り。犬猫以外（インコ・ウサギ）も other で載せる ----------------------------------
def test_chiba_6_today_takes_photo_and_items():
    res = _run("city_chiba-6", _fixture("t518_chiba-6.html"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "management_no", "image_url", "species", "shelter_date", "location", "breed", "color", "sex", "size") == {
        "management_no": "A-5069", "image_url": IMG + "a5069.jpg", "species": "other", "shelter_date": "令和7年11月1日",
        "location": "美浜区打瀬付近", "breed": "セキセイインコ", "color": "イエローとグリーン", "sex": "メス", "size": "小"}
    assert a["note"] == "嘴は黄色 鼻は薄いピンク 頭は黄色 胴体は黄緑色 羽に薄い黒模様あり ほっぺに逆三角形の青模様"


def test_chiba_6_three_animals_keep_their_own_photos():
    res = _run("city_chiba-6", _fixture("t518_chiba-6_wb20250613.html"))
    assert [a["management_no"] for a in res.animals] == ["A-5025", "A-5009", "A-4116"]
    a25, a09, a16 = res.animals
    assert [a["image_url"] for a in res.animals] == [IMG + "a-5025.jpg", IMG + "inko5009.jpg", IMG + "a4116.jpg"]
    assert {a["species"] for a in res.animals} == {"other"}
    assert _pick(a25, "breed", "color") == {"breed": "ウサギ", "color": "全体的に白、部分的に黒"}
    assert a09["location"] == "花見川区千種町付近"   # 保護日と保護場所の間に空の p があっても取る
    assert a16["size"] is None
    assert res.dropped == []


# --- 公開前レビュー（10/5 19:40）F-01・F-02: Wayback の別の作りの日 --------------------------------------------
# 2026-02-09 の迷子猫ページは h2「このページのご利用について」が雛形より前にあり、row_until の h2 で止まらない。
# 写真を既定の img@src で探すと、雛形の行に子猫の育成ボランティアのバナー（konekobosyu.gif）が付いて偽の 1 頭になる。
def test_chiba_2_empty_day_with_heading_first_is_not_a_fake_animal():
    res = _run("city_chiba-2", _fixture("t518_chiba-2_wb20260209_empty.html"))
    assert res.animals == []
    assert res.empty_confirmed is True


def test_chiba_2_last_animal_without_photo_gets_no_banner():
    res = _run("city_chiba-2", _fixture("t518_chiba-2_wb20250911.html"))
    by_no = {a["management_no"]: a for a in res.animals}
    assert set(by_no) == {"25090901", "25090801"}
    assert by_no["25090801"]["image_url"] is None                     # 元ページに写真が無い子
    assert all("konekobosyu" not in (a["image_url"] or "") for a in res.animals)


def test_chiba_2_fourth_animal_without_photo_gets_no_banner():
    res = _run("city_chiba-2", _fixture("t518_chiba-2_wb20260417.html"))
    by_no = {a["management_no"]: a for a in res.animals}
    assert set(by_no) == {"26041501", "26041403", "26041402", "26041401"}
    assert by_no["26041401"]["image_url"] is None
    assert all("konekobosyu" not in (a["image_url"] or "") for a in res.animals)


def test_chiba_1_empty_day_wording_of_2026_04():
    res = _run("city_chiba-1", _fixture("t518_chiba-1_wb20260412_empty.html"))
    assert res.animals == [] and res.empty_confirmed is True
