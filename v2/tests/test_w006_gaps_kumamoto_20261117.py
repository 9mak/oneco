"""W006 T640 掲載漏れ 1 回目: 熊本県動物愛護センター「保健所・センターからの保護犬・保護猫情報」（type_id:3）の追加（2026-11-17・ネットワークなし）。

type_id:3 は「迷子でも譲渡対象でもないが、保健所・センターで保護されている犬猫」。既存の 8 ページ（type_id:1 迷子・type_id:2 譲渡）と同じテンプレートで、
一覧 ul.list-4col li に収容日・種類・性別・個体管理ナンバー・保健所・電話番号が揃う。区分は sheltered（保護中）。
0 頭の日は「0件中 0～0件目を表示」（Wayback 猫 2025-09・犬 2025-04）。子のいる日（Wayback 2026-02・今日）には出ない。
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

DOG, CAT = "kumamoto_doubutuaigo-9", "kumamoto_doubutuaigo-10"
DOG_URL = "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:3/animal_id:1"
CAT_URL = "https://www.kumamoto-doubutuaigo.jp/animals/index/type_id:3/animal_id:2"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, pages: dict[str, str]) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry_entries():
    for slug, url, species in ((DOG, DOG_URL, "dog"), (CAT, CAT_URL, "cat")):
        s = SOURCES[slug]
        assert s.url == url and s.mode == "recipe" and s.enabled
        assert s.kind == "sheltered" and s.species == species and s.prefecture == "熊本県"
        # 2026-11-13 の熊本県の返事は依頼した 8 ページ（type_id:1・2）についてで、type_id:3 は依頼に入れていなかったので改めて聞くまで出さない
        assert s.photo == "pending"
    # 既存の同じサイトの 8 ページと同じく、電話は個体ごとの保健所（子の項目）で出す
    assert all(SOURCES[f"kumamoto_doubutuaigo-{i}"].phone is None for i in range(1, 9))


def test_dog_today_reads_two_pages_28_dogs():
    c = _run(DOG, {DOG_URL: _fx("w006_kumamoto_doubutuaigo-9_20261117.html"),
                   DOG_URL + "/page:2": _fx("w006_kumamoto_doubutuaigo-9_p2_20261117.html")})
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 28  # ページの「28件中 1～20件目」+「28件中 21～28件目」
    first = animals[0]
    assert first["management_no"] == "AM00199" and first["location"] == "天草保健所"
    assert first["phone"] == "0969-23-0299" and first["shelter_date"]
    assert all(a["management_no"] and a["species"] == "dog" for a in animals)
    assert len({a["id"] for a in animals}) == 28


def test_cat_today_reads_three_cats():
    c = _run(CAT, {CAT_URL: _fx("w006_kumamoto_doubutuaigo-10_20261117.html")})
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 3
    assert all(a["species"] == "cat" and a["management_no"] for a in c.result.animals)


def test_child_days_in_wayback_read_and_never_zero():
    c = _run(DOG, {DOG_URL: _fx("w006_kumamoto_doubutuaigo-9_child_wb20260205.html")})
    assert c.status == "ok" and len(c.result.animals) == 1, c.error
    assert _hits(DOG, _fx("w006_kumamoto_doubutuaigo-9_child_wb20260205.html")) == []
    c = _run(CAT, {CAT_URL: _fx("w006_kumamoto_doubutuaigo-10_child_wb20260205.html")})
    assert c.status == "ok" and len(c.result.animals) == 2, c.error
    assert _hits(CAT, _fx("w006_kumamoto_doubutuaigo-10_child_wb20260205.html")) == []


def test_zero_days_are_empty():
    assert _zero(_run(DOG, {DOG_URL: _fx("w006_kumamoto_doubutuaigo-9_zero_wb20250401.html")}))
    assert _zero(_run(CAT, {CAT_URL: _fx("w006_kumamoto_doubutuaigo-10_zero_wb20250902.html")}))


def test_structure_change_is_not_zero():
    # 一覧の入れ物の名前が変わって行が取れなくなった子のいる日は、0 頭にしない（「0件中」の文言も出ていない）
    html = _fx("w006_kumamoto_doubutuaigo-10_20261117.html").replace("list-4col", "list-3col")
    assert not _zero(_run(CAT, {CAT_URL: html}))
