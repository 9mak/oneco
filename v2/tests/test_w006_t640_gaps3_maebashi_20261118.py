"""W006 T640 掲載漏れ 3 回目 A: 前橋市の飼い主を募集している猫・犬（2026-11-18・ネットワークなし）。

- 猫の飼い主を募集しています（18316）14 頭と、犬の飼い主を募集しています（18317）1 頭。台帳の city_maebashi（保護犬。迷子）・-2・-3（市民の掲示板）とは別のページ。
  仕様の親ページ（4126.html）は「犬・猫の譲渡事業」の案内で、一覧は猫（18316）・犬（18317）の 2 ページ。
- 1 頭 = 管理番号を caption にした表 1 つ（仮名・猫種／毛色・性別／推定年齢・性格・ワクチン歴等／紹介欄／写真）。猫と犬で 2 段目の並びが違う
  （猫は毛色・性別、犬は性別・毛色）。見出しの無い位置読みなので、性別の欄がオス・メスでない行は載せず、並びが入れ替わった日は 1 頭も読めない（failed で通知）。
- 写真は pending（前橋市は規約が転載要申請の事前相談が要るホスト）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

CAT, DOG = "city_maebashi-4", "city_maebashi-5"
CAT_URL = "https://www.city.maebashi.gunma.jp/kurashi_tetsuzuki/1/1/3/18316.html"
DOG_URL = "https://www.city.maebashi.gunma.jp/kurashi_tetsuzuki/1/1/3/18317.html"
IMG = "https://www.city.maebashi.gunma.jp/material/images/group/43/"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def _without_animal_tables(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup.select("table"):
        cap = t.select_one("caption")
        if cap is not None and "-" in cap.get_text():
            t.decompose()
    return str(soup)


def test_registry():
    for slug, url, species in ((CAT, CAT_URL, "cat"), (DOG, DOG_URL, "dog")):
        s = SOURCES[slug]
        assert (s.url, s.kind, s.species, s.mode, s.enabled) == (url, "adoption", species, "recipe", True)
        assert (s.municipality, s.prefecture, s.phone) == ("前橋市", "群馬県", "027-220-5777")
        assert s.photo == "pending"   # 事前相談の要るホスト（返事待ち）。既存の city_maebashi と同じ
        assert s.recipe_path.exists()


def test_cat_today_reads_14_cats_with_the_columns_in_their_places():
    html = _fx("w006_city_maebashi-4_20261118.html")
    assert "譲渡が決まりました" in html and "<caption>譲渡決定♪♪</caption>" in html   # 決まった子（シラ）の表も一覧に残っているが、載せない
    c = _run(CAT, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 14 and len({a["id"] for a in animals}) == 14 and "シラ" not in [a["name"] for a in animals]
    assert all(a["species"] == "cat" for a in animals)
    assert [(a["management_no"], a["name"], a["breed"], a["color"], a["sex"], a["age"]) for a in animals[:4]] == [
        ("C2026-057", "てん", "雑種", "黒", "オス", "6ヶ月"),
        ("C2026-090", "きぃ", "雑種", "キジトラ", "去勢済オス", "4ヶ月"),
        ("C2026-117", "かみお", "雑種", "キジトラ", "去勢済オス", "7ヶ月"),
        ("C2026-124", "姫", "雑種", "キジ白", "メス", "3ヶ月"),
    ]
    assert [a["management_no"] for a in animals] == [
        "C2026-057", "C2026-090", "C2026-117", "C2026-124", "C2026-125", "C2026-126", "C2026-128",
        "C2026-131", "C2026-132", "C2026-137", "C2026-138", "C2026-139", "C2026-174", "C2026-176"]
    last = animals[-1]
    assert (last["name"], last["color"], last["sex"], last["age"]) == ("カネトラ", "茶トラ", "オス", "7才")
    # 写真は表の最終行の img（//www… の相対 URL を絶対にする）。性格・ワクチン歴等・紹介欄は note に出す
    assert animals[0]["image_url"] == IMG + "vga2026-06-10amagawaooshimamachikuroosu5.jpg"
    assert "性格：大人しい" in animals[0]["note"] and "3種混合ワクチン(2回目)" in animals[0]["note"] and "エコ的な動作" in animals[0]["note"]
    assert "真菌治療中" in animals[3]["note"]
    # 元ページのリンクは一覧のページ（個別ページは無い）
    assert all(a["source_url"] == CAT_URL for a in animals)


def test_dog_today_reads_1_dog_with_sex_and_color_in_the_dogs_order():
    c = _run(DOG, _fx("w006_city_maebashi-5_20261118.html"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 1 and animals[0]["species"] == "dog"
    a = animals[0]
    assert (a["management_no"], a["name"], a["sex"], a["color"], a["age"]) == ("D2026-004", "マヨ", "メス", "薄茶", "12歳")
    assert a["breed"].startswith("MIX(マルチーズ")
    assert a["image_url"] == IMG + "vga2026-09-28ikehatamachi16.jpg"


def test_a_page_whose_columns_are_swapped_is_not_read_with_the_wrong_values():
    # 猫のページを犬の並びで読むと「性別」の位置に毛色が来る。値をずらして載せず、1 頭も読めない（failed で通知）
    assert _run(DOG, _fx("w006_city_maebashi-4_20261118.html")).status == "failed"
    assert _run(CAT, _fx("w006_city_maebashi-5_20261118.html")).status == "failed"


def test_zero_days_in_wayback_cat_2025_05_and_dog_2026_04():
    # 0 頭の日の実物。猫 2025-05 は見出しが「飼い主を募集している「猫」の一覧※現在はいません」で動物の表が無い。
    # 犬 2026-04 は見出しはそのままで、決まった子（caption「譲渡決定」・「譲渡が決まりました」）の表だけが残る。どちらも 0 頭
    cat = _fx("w006_city_maebashi-4_wb20250513.html")
    assert "「猫」の一覧※現在はいません" in cat and not any("-" in c.get_text() for c in BeautifulSoup(cat, "lxml").select("caption"))
    assert _zero(_run(CAT, cat))
    dog = _fx("w006_city_maebashi-5_wb20260412.html")
    assert "譲渡が決まりました" in dog and "<caption>譲渡決定</caption>" in dog
    assert _zero(_run(DOG, dog))
    dog0 = _fx("w006_city_maebashi-5_wb20250318.html")   # 犬 2025-03: 見出しが「飼い主を募集している犬の一覧【現在は譲渡対象犬はいません】」
    assert "【現在は譲渡対象犬はいません】" in dog0
    assert _zero(_run(DOG, dog0))
    # その保存ページに今日の動物の表を足した日は 0 頭にしない
    cat_with_animal = _fx("w006_city_maebashi-4_20261118.html")
    assert not _zero(_run(CAT, cat_with_animal))


def test_other_days_in_wayback_are_read_with_the_same_columns():
    # 猫 2026-04（1 頭 C2025-153。決まった子の表 2 つは載せない）・2026-09（13 頭。ID は今日と同じ子で同じ）・犬 2025-11（1 頭 D2025-011）
    c = _run(CAT, _fx("w006_city_maebashi-4_wb20260412.html"))
    assert c.status == "ok" and [(a["management_no"], a["name"], a["sex"], a["color"], a["age"]) for a in c.result.animals] == [
        ("C2025-153", "ブチ", "メス(避妊済み)", "黒白", "10歳以上")]
    assert "性格：ベロ出し" in c.result.animals[0]["note"]
    sep = _run(CAT, _fx("w006_city_maebashi-4_wb20260923.html"))
    assert sep.status == "ok" and len(sep.result.animals) == 13
    today = _run(CAT, _fx("w006_city_maebashi-4_20261118.html"))
    by_sep = {a["management_no"]: a["id"] for a in sep.result.animals}
    by_today = {a["management_no"]: a["id"] for a in today.result.animals}
    shared = set(by_sep) & set(by_today)
    # 9 月から 11 月で入れ替わった子もいる。両方に載っている子（C2026-057 など 6 頭）は ID が同じ（写真から作る）
    assert "C2026-057" in shared and len(shared) == 6 and all(by_sep[m] == by_today[m] for m in shared)
    d = _run(DOG, _fx("w006_city_maebashi-5_wb20251113.html"))
    assert d.status == "ok" and [(a["management_no"], a["name"], a["sex"], a["color"], a["age"]) for a in d.result.animals] == [
        ("D2025-011", "しらたま", "オス(未去勢)", "白", "7歳")]


def test_old_layouts_of_2019_are_not_zero():
    # 2019 年は管理番号の caption が無い別の作り（「ねこ」の一覧・個別の詳細情報の表）。1 頭も読めないが 0 頭とは言わない（failed で通知）
    assert _run(CAT, _fx("w006_city_maebashi-4_wb20190721.html")).status == "failed"
    assert _run(DOG, _fx("w006_city_maebashi-5_wb20191021.html")).status == "failed"


def test_zero_only_when_the_frame_is_there_and_no_animal_table_is():
    # 今日の保存ページから動物の表を消して再現する（雛形の表「管理番号」・年度別の頭数の表は残る）
    for slug, name in ((CAT, "w006_city_maebashi-4_20261118.html"), (DOG, "w006_city_maebashi-5_20261118.html")):
        zero = _without_animal_tables(_fx(name))
        assert "管理番号" in zero and "-" not in "".join(t.get_text() for t in BeautifulSoup(zero, "lxml").select("caption")), slug
        assert _zero(_run(slug, zero)), slug
        # 枠の見出しが変わった日は 0 頭にしない
        assert not _zero(_run(slug, zero.replace("の一覧", "の紹介"))), slug
        # 動物の表の caption の書き方が変わった日（写真の行は残る）は 0 頭にしない
        assert not _zero(_run(slug, _fx(name).replace("C2026-", "C2026・").replace("D2026-", "D2026・"))), slug
