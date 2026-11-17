"""W006 T640 掲載漏れ 1 回目: 広島県動物愛護センターの譲渡犬・譲渡猫、大阪府動物愛護管理センターの譲渡犬・譲渡猫・犬猫以外の追加（2026-11-17・ネットワークなし）。

台帳には広島県の迷い犬・迷い猫（pref_hiroshima-1・2）と大阪府の迷い犬猫（pref_osaka）しか無く、里親募集のページが抜けていた。
- 広島県（-3 犬・-4 猫）: h2「管理番号：…」→ p 写真 → p 性別・推定年齢… の平らな並び（1 頭分が div で入れ子になる日もある）。
- 大阪府（pref_osaka_joto-1 犬・-3 犬猫以外）: 1 頭 = 1 つの table。区分の見出し（h3）を note の先頭に出す。
- 大阪府の猫（pref_osaka_joto-2）: 個票は PDF で、本文には写真と見出し（性別・年齢の区分）しか無い。PDF は読まず、写真 1 枚 = 1 頭。
0 頭は文言でなく「管理番号の見出し・表・写真のリンクが無い」ことで決める（区分ごとの「現在対象の犬はいません」は子のいる日にも出る）。
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
HIRO = ("pref_hiroshima-3", "pref_hiroshima-4")
OSAKA = ("pref_osaka_joto-1", "pref_osaka_joto-2", "pref_osaka_joto-3")


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _today(slug: str) -> str:
    return _fx(f"w006_{slug}_{TODAY}.html")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry_entries():
    expect = {
        "pref_hiroshima-3": ("広島県", "dog", "0848-60-8511"), "pref_hiroshima-4": ("広島県", "cat", "0848-60-8511"),
        "pref_osaka_joto-1": ("大阪府", "dog", "072-958-8212"), "pref_osaka_joto-2": ("大阪府", "cat", "072-958-8212"),
        "pref_osaka_joto-3": ("大阪府", "mixed", "072-958-8212"),
    }
    for slug, (pref, species, phone) in expect.items():
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == pref, slug
        assert s.species == species and s.phone == phone and s.address, slug
        assert s.photo == "ok", slug  # 既存の同じホスト（pref.hiroshima.lg.jp・pref.osaka.lg.jp）の掲載元と同じ（規約は無断転載禁止のみ）
        assert s.contact_scope == "facility", slug
        assert s.recipe_path.exists(), slug


def test_hiroshima_dog_reads_18_including_nested_div():
    c = _run("pref_hiroshima-3", _today("pref_hiroshima-3"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 18  # h2「管理番号：…」が 18
    nos = [a["management_no"] for a in animals]
    assert nos[0] == "1HD20260132" and nos[4] == "1HD20260143" and nos[-1] == "1HD20260198"  # 5 頭目の後ろは div で入れ子
    assert len(set(nos)) == 18 and len({a["id"] for a in animals}) == 18
    first = animals[0]
    assert (first["sex"], first["age"], first["species"]) == ("雄", "推定5歳", "dog")
    assert first["note"] == "※2週間のトライアル必須" and first["image_url"]
    assert animals[4]["sex"] == "雌" and animals[4]["age"] == "推定4か月" and not animals[4].get("note")
    assert _hits("pref_hiroshima-3", _today("pref_hiroshima-3")) == []


def test_hiroshima_cat_reads_6_and_notes_trial():
    c = _run("pref_hiroshima-4", _today("pref_hiroshima-4"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"] for a in animals] == [
        "1HN20260034", "1HN20260043", "1HN20260042", "1HN20260037", "1HN20260045", "1HN20260092"]
    assert all(a["species"] == "cat" and a["image_url"] for a in animals)
    assert animals[0]["sex"] == "雌" and animals[0]["age"] == "推定3歳"
    # h2 に「※現在トライアル中です」が付いた子は載せて note に出す
    assert animals[-1]["note"] == "※現在トライアル中です。※最大2週間のトライアル可能"
    assert _hits("pref_hiroshima-4", _today("pref_hiroshima-4")) == []


def test_osaka_dog_reads_three_with_section_in_note():
    c = _run("pref_osaka_joto-1", _today("pref_osaka_joto-1"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["management_no"], a["name"]) for a in animals] == [
        ("26-00132", "てんしん"), ("25-00643", "ロビン"), ("26-00053", "ロッキー")]
    first = animals[0]
    assert (first["breed"], first["color"], first["sex"], first["age"], first["size"]) == ("雑種", "茶", "オス", "4歳前後", "約13kg")
    assert animals[0]["note"].startswith("比較的飼いやすい犬。")
    assert animals[1]["note"].startswith("十分な知識や心構えが必要な犬。")
    assert animals[2]["note"].startswith("現在トレーニング中の犬。")  # マッチング・譲渡はトレーニング終了後
    assert all(a["species"] == "dog" and a["image_url"] for a in animals)
    # 「現在対象の犬はいません。」（持続的なケアが必要な犬の節）は子のいる今日も出ている
    assert "現在対象の犬はいません" in _today("pref_osaka_joto-1")
    assert _hits("pref_osaka_joto-1", _today("pref_osaka_joto-1")) == []


def test_osaka_cat_reads_15_photos_and_skips_not_yet_public():
    c = _run("pref_osaka_joto-2", _today("pref_osaka_joto-2"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    # 写真のリンクは 17 枚。うち 2 枚（コーナンの店舗の猫）は「令和8年11月24日から公開予定」なので載せない
    assert len(animals) == 15 and len(c.result.dropped) == 2
    assert len({a["id"] for a in animals}) == 15
    assert all(a["species"] == "cat" and a["image_url"] and not a.get("management_no") for a in animals)
    sexes = [a["sex"] for a in animals]
    assert sexes == ["雄"] * 4 + ["雌"] * 5 + ["雄"] * 2 + ["雌"] * 4
    assert [a["age"] for a in animals] == ["1歳齢以上"] * 9 + ["1歳齢未満"] * 6
    assert _hits("pref_osaka_joto-2", _today("pref_osaka_joto-2")) == []


def test_osaka_cat_store_cats_are_listed_once_public():
    # 公開予定の表記が消えた（店舗の猫が公開された）日は、店舗の猫を note に出して載せる
    html = _today("pref_osaka_joto-2").replace("（令和8年11月24日から公開予定）", "")
    c = _run("pref_osaka_joto-2", html)
    assert c.status == "ok" and len(c.result.animals) == 17, c.error
    stores = [a for a in c.result.animals if a.get("note")]
    assert len(stores) == 2 and all("ホームセンターコーナン" in a["note"] for a in stores)


def test_osaka_other_reads_six_rabbits_as_other():
    c = _run("pref_osaka_joto-3", _today("pref_osaka_joto-3"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 6
    assert all(a["species"] == "other" and a["breed"] == "ウサギ" and a["image_url"] for a in animals)
    by = {a["management_no"]: a for a in animals}
    assert by["25-00885"]["name"] == "しーくん" and by["25-00885"]["sex"] == "オス" and by["25-00885"]["age"] == "2歳前後"
    assert by["26-00138"]["name"] == "ジャスミン" and by["26-00138"]["sex"] == "メス"
    assert _hits("pref_osaka_joto-3", _today("pref_osaka_joto-3")) == []


def _strip_animals(html: str, slug: str) -> str:
    """子のいない日の作りを今日の保存ページから作る（動物の見出し・表・写真だけ消し、枠・案内文は残す）。"""
    soup = BeautifulSoup(html, "lxml")
    if slug.startswith("pref_hiroshima"):
        for h2 in soup.select("div#main_body h2:-soup-contains('管理番号')"):
            h2.decompose()
        for img in soup.select("div#main_body div.detail_free p > img"):
            img.decompose()
    elif slug == "pref_osaka_joto-2":
        for a in soup.select("#tmp_contents a[href$='.pdf']:has(> img)"):
            a.decompose()
    else:
        for t in soup.select("#tmp_contents table"):
            if "管理番号" in t.get_text():
                t.decompose()
        for img in soup.select("#tmp_contents img[src*='/images/1443/'], #tmp_contents img[src*='/images/20402/']"):
            img.decompose()
    return str(soup)


def test_zero_day_without_any_animal_is_empty():
    # 0 頭の日の版は Wayback に無い（取れた版はどれも子のいる日）ので、今日の保存ページから動物だけを消して再現する
    for slug in HIRO + OSAKA:
        assert _zero(_run(slug, _strip_animals(_today(slug), slug))), slug


def test_structure_change_with_children_is_not_zero():
    # 行の読み方が崩れた（見出しの語・表の class が変わった）子のいる日は 0 頭にしない
    for slug in HIRO:
        html = _today(slug).replace("管理番号：", "番号：")
        assert not _zero(_run(slug, html)), slug
    html = _today("pref_osaka_joto-1").replace("datatable", "datatable2")
    assert not _zero(_run("pref_osaka_joto-1", html))
    html = _today("pref_osaka_joto-3").replace("管理番号", "ID")
    assert not _zero(_run("pref_osaka_joto-3", html))
    html = _today("pref_osaka_joto-2").replace('.pdf"', '.pdf2"')
    assert not _zero(_run("pref_osaka_joto-2", html))
