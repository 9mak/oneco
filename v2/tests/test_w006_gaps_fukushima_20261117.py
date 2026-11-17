"""W006 T640 掲載漏れ 1 回目: 福島県動物愛護センター（本所・会津支所・相双支所）の譲渡犬・譲渡猫 6 ページの追加（2026-11-17・ネットワークなし）。

台帳には福島県の迷子 5 ページ（pref_fukushima-1〜5）しか無く、飼い主募集中のページが抜けていた。
- 本所（-6 猫・-7 犬）: 一覧表の 1 行 = 1 頭（ニックネーム＋写真・種類・毛色・性別・推定年齢）。詳しい表は読まない。
- 会津支所（-8 犬・-10 猫）・相双支所（-9 猫・-11 犬）: 1 頭 1 表（thead の th に管理番号とニックネーム）。
  0 頭の日は同じ表の雛形が残る（会津の猫・相双の犬が今日 0 頭）。0 頭は文言でなく「表・一覧に写真も個体の見出しも無い」ことで決める。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
TODAY = "20261117"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _today(n: int) -> str:
    return _fx(f"w006_pref_fukushima-{n}_{TODAY}.html")


def _run(n: int, html: str) -> Collected:
    s = SOURCES[f"pref_fukushima-{n}"]
    return collect_one(s, FakeFetcher({s.url: html}))


def _hits(n: int, html: str):
    s = SOURCES[f"pref_fukushima-{n}"]
    recipe = Recipe.load(ROOT / "recipes" / f"pref_fukushima-{n}.yaml")
    return empty_hits(recipe, [Doc(url=s.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry_entries():
    expect = {
        6: ("cat", "024-953-6400"), 7: ("dog", "024-953-6400"), 8: ("dog", "0242-29-5517"),
        9: ("cat", "0244-26-1351"), 10: ("cat", "0242-29-5517"), 11: ("dog", "0244-26-1351"),
    }
    for n, (species, phone) in expect.items():
        s = SOURCES[f"pref_fukushima-{n}"]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "福島県", n
        assert s.species == species and s.phone == phone and s.address, n
        assert s.photo == "ok", n  # 既存の福島県の掲載元と同じ（規約は無断転載禁止のみ）
        assert s.contact_scope == "facility", n
        assert s.url.startswith("https://www.pref.fukushima.lg.jp/sec/2162"), n


def test_miharu_cat_reads_19_from_the_list_table():
    c = _run(6, _today(6))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 19  # 一覧表の行 19・詳しい表の見出し（a#名前）も 19
    assert all(a["species"] == "cat" and a["image_url"] for a in animals)
    first = animals[0]
    assert (first["name"], first["breed"], first["color"], first["sex"], first["age"]) == (
        "ナイル", "雑種", "茶", "オス(去勢手術済み)", "1歳位")
    # 一覧の行の 2 行目の動画の案内（👉紹介動画あり！）が名前に混ざらない
    assert animals[1]["name"] == "おちょ" and animals[1]["sex"].startswith("メス")
    assert len({a["id"] for a in animals}) == 19
    assert _hits(6, _today(6)) == []


def test_miharu_cat_child_day_in_wayback_reads_and_never_zero():
    html = _fx("w006_pref_fukushima-6_child_wb20261016.html")  # Wayback 2026-10-16（掲載日 10月14日）
    c = _run(6, html)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 11
    assert c.result.animals[0]["name"] == "ナイル"
    assert _hits(6, html) == []


def test_miharu_dog_reads_two():
    c = _run(7, _today(7))
    assert c.status == "ok", c.error
    got = [(a["name"], a["breed"], a["color"], a["sex"], a["age"]) for a in c.result.animals]
    assert got == [("カイリ", "雑種", "こげ茶", "メス", "10歳"), ("グーフィー", "雑種", "茶", "オス", "15歳")]
    assert all(a["species"] == "dog" for a in c.result.animals)
    assert _hits(7, _today(7)) == []


def test_aizu_dog_reads_one_table():
    c = _run(8, _today(8))
    assert c.status == "ok", c.error
    [a] = c.result.animals
    assert (a["management_no"], a["name"], a["breed"], a["age"], a["species"]) == ("26-11-01", "ラグナ", "ミックス", "6歳", "dog")
    assert a["sex"].startswith("オス") and "日本犬の飼育経験者" in a["note"] and a["image_url"]
    assert _hits(8, _today(8)) == []


def test_soso_cat_reads_seven_tables():
    c = _run(9, _today(9))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 7
    first = animals[0]
    assert (first["management_no"], first["breed"], first["age"], first["size"]) == ("20260806_01", "雑種", "2才", "中型")
    assert first["name"].replace("　", " ") == "うに くん" and first["sex"].startswith("オス")
    assert [a["management_no"] for a in animals][-1] == "20261111_04"
    assert all(a["species"] == "cat" and a["image_url"] for a in animals)
    assert _hits(9, _today(9)) == []


def test_aizu_cat_and_soso_dog_are_zero_today():
    # 会津の猫は「〇現在、譲渡猫情報はありません。」、相双の犬は文言なしで、どちらもセルが空の雛形の表だけが残る
    assert "現在、譲渡猫情報はありません" in _today(10)
    assert _zero(_run(10, _today(10)))
    assert _zero(_run(11, _today(11)))


def test_zero_template_is_not_read_as_an_animal():
    # 雛形の表（管理番号の括弧が空）は動物にならない
    for n in (10, 11):
        c = _run(n, _today(n))
        assert c.result is not None and c.result.animals == [], n


def test_structure_change_with_children_is_not_zero():
    # 行の読み方が崩れた（見出しの語が変わった）子のいる日は 0 頭にしない（会津・相双は写真、本所は一覧の写真が残る）
    for n in (8, 9):
        html = _today(n).replace("管理番号", "ID")
        assert not _zero(_run(n, html)), n
        assert _hits(n, html) == [], n
    for n in (6, 7):
        html = _today(n).replace('href="#', 'href="/x#')
        assert not _zero(_run(n, html)), n


def _strip_animals(html: str, n: int) -> str:
    soup = BeautifulSoup(html, "lxml")
    if n in (6, 7):
        for tr in soup.select("div#main_body tr:has(> td a[href^='#'] img)"):
            tr.decompose()
        for a in soup.select("div#main_body a[id]:has(> strong)"):
            a.decompose()
    return str(soup)


def test_miharu_zero_day_without_rows_is_empty():
    # 本所の 0 頭の日の版は Wayback に無いので、今日の保存ページから動物の行と見出しだけを消して再現する
    for n in (6, 7):
        assert _zero(_run(n, _strip_animals(_today(n), n))), n
