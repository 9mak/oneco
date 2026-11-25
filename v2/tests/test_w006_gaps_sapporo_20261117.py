"""W006 T640 掲載漏れ 1 回目: 札幌市動物愛護管理センターの譲渡犬・譲渡猫 2 ページの追加（2026-11-17・ネットワークなし）。

台帳には札幌市の迷子犬・迷子猫（city_sapporo-1・2）しか無く、譲渡のページが抜けていた。
- city_sapporo-3（譲渡犬）: 犬ごとに h2（管理番号）+ table。今日（2026-11-17）は 0 頭で、h2「AD081109-01は譲渡されました（11/13）」と空の雛形の表が残る
  （「現在いません」の文言は無い）。子のいる日の作りは Wayback 2026-05-18（2 頭）。
- city_sapporo-4（譲渡猫）: h2 の区分 + 猫ごとの h3「名前（管理番号） 年齢 性別」。今日は 42 頭（ページの「譲渡可能な成猫の数 42匹」と合う）。
  「一時的に譲渡対象外の猫」の 1 頭は載せない。写真の規約は返事待ちなので photo: pending。
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
DOG, CAT = "city_sapporo-3", "city_sapporo-4"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry_entries():
    for slug, species in ((DOG, "dog"), (CAT, "cat")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "北海道", slug
        assert s.species == species and s.phone == "011-736-6134" and s.address, slug
        assert s.photo == "ok", slug  # 2026-11-24 札幌市から「写真も含め表示することについては、特に問題ありません」と返事
        assert s.recipe_path.exists(), slug


def test_dog_today_is_zero_because_the_only_block_is_adopted():
    html = _fx("w006_city_sapporo-3_20261117.html")
    assert "AD081109-01は譲渡されました" in html
    c = _run(DOG, html)
    assert _zero(c), (c.status, c.error)
    assert len(c.result.dropped) == 1 and "譲渡されました" in c.result.dropped[0].reason


def test_dog_child_day_in_wayback_reads_two_and_never_zero():
    html = _fx("w006_city_sapporo-3_child_wb20260518.html")
    c = _run(DOG, html)
    assert c.status == "ok", c.error
    got = [(a["management_no"], a["name"], a["breed"], a["sex"], a["age"], a["size"]) for a in c.result.animals]
    assert got == [("AD080511-01", "エリザベス", "雑種", "メス", "13歳", "小(4.2kg)"),
                   ("AD080427-02", "ゆき", "雑種", "メス", "推定2歳", "中(13.5kg)")]
    assert all(a["species"] == "dog" and a["image_url"] for a in c.result.animals)
    assert _hits(DOG, html) == []


def test_dog_structure_change_on_a_child_day_is_not_zero():
    html = _fx("w006_city_sapporo-3_child_wb20260518.html").replace("種類", "区分")
    assert not _zero(_run(DOG, html))
    # 「譲渡されました」が付かない雛形（見出しが管理番号だけで表が空）になった日は、行が取れず「読めなかった」でなく 0 頭になるのは写真が無いときだけ
    html = _fx("w006_city_sapporo-3_child_wb20260518.html").replace('src="/inuneko/syuuyou_doubutsu/images/ad080511-01.jpg"', "")
    assert not _zero(_run(DOG, html))


def test_cat_today_reads_42_and_skips_temporarily_not_adoptable():
    html = _fx("w006_city_sapporo-4_20261117.html")
    assert "譲渡可能な成猫の数" in html
    c = _run(CAT, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 42 and len(c.result.dropped) == 1
    nos = [a["management_no"] for a in animals]
    assert nos[0] == "AC080727-01" and "AC081029-19" not in nos  # 一時的に譲渡対象外（まさむね）
    assert len(set(nos)) == 42 and len({a["id"] for a in animals}) == 42
    first = animals[0]
    assert (first["name"], first["age"], first["sex"], first["species"]) == ("ぷーあーる", "9歳", "オス", "cat")
    assert first["note"].startswith("人に馴れている猫。") and first["image_url"]
    assert any(a["note"].startswith("あまり人に馴れていない猫。") for a in animals)
    assert _hits(CAT, html) == []


def test_cat_child_day_in_wayback_matches_the_page_count():
    html = _fx("w006_city_sapporo-4_child_wb20260609.html")
    assert "譲渡可能な成猫の数" in html and "12匹" in html
    c = _run(CAT, html)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 12  # ページの「譲渡可能な成猫の数 12匹」
    assert all(a["species"] == "cat" and a["management_no"] and a["image_url"] for a in c.result.animals)
    assert _hits(CAT, html) == []


def test_cat_structure_change_is_not_zero_and_zero_day_is_empty():
    html = _fx("w006_city_sapporo-4_20261117.html")
    broken = html.replace("（AC", "（XX").replace("（LC", "（XX")
    assert not _zero(_run(CAT, broken))
    # 0 頭の日の版は Wayback で見つからないので、今日の保存ページから猫の見出しと写真だけを消して再現する
    soup = BeautifulSoup(html, "lxml")
    for h3 in soup.select("#tmp_contents h3"):
        h3.decompose()
    for img in soup.select("#tmp_contents p > img[src*='/inuneko/syuuyou_doubutsu/images/A'], #tmp_contents p > img[src*='/inuneko/syuuyou_doubutsu/images/L']"):
        img.decompose()
    assert _zero(_run(CAT, str(soup)))
