"""T521（2026-10-07）ゲートと T520 の監視で見つかった直しのテスト（ネットワークなし）。

- 仙台 譲渡犬（city_sendai-1）: 愛称に半角の括弧が入る子（Wayback 2026-06 の D26001「Ohana(オハナ)」・D26002「作(サク)」）
- 一関 迷子（pref_iwate_ichinoseki）: 「死亡した状態で発見されました」の犬 1-6 が迷子として載っていた（10/6・10/7 の本番）
- 大船渡 譲渡・迷子（pref_iwate_ofunato・-2）: Wayback 2024-04・2025-09 の作り（写真が p.imageright・見出し「【保護】もとの飼い主さんを
  探しています」）でどちらも failed だった。2024-04 の譲渡には柴犬 231203 がいて、台帳の猫固定で猫として出ていた
- 広島県 迷い犬（pref_hiroshima-1）: Wayback 2025-05 は返還済みの犬が載り品種に性別が入る、2025-11 は品種に「収容された日」の文が入る
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Executor, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(slug: str, fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_sendai_name_keeps_half_width_parentheses():
    names = {a["management_no"]: a["name"] for a in _run("city_sendai-1", "t521_city_sendai-1_wb20260618.html").animals}
    assert names == {"D24018": "平助", "D26001": "Ohana(オハナ)", "D26002": "作(サク)"}


def test_ichinoseki_dog_found_dead_is_not_listed():
    res = _run("pref_iwate_ichinoseki", "t521_ichinoseki_20261007.html")
    assert [a["management_no"] for a in res.animals] == ["9-1"]
    assert any("1-6" in d.text for d in res.dropped)


def test_ofunato_adoption_today_is_unchanged():
    res = _run("pref_iwate_ofunato", "t521_ofunato_20261007.html")
    assert len(res.animals) == 9 and {a["species"] for a in res.animals} == {"cat"}
    assert "高はにゃ田" in {a["name"] for a in res.animals}


def test_ofunato_adoption_imageright_layout_and_a_dog():
    res = _run("pref_iwate_ofunato", "t521_ofunato_wb20240418.html")
    got = {a["management_no"]: a["species"] for a in res.animals}
    assert len(got) == 7 and got["231203"] == "dog" and got["240201"] == "cat"
    assert all(a["image_url"] for a in res.animals)


def test_ofunato_adoption_drops_the_one_already_adopted():
    res = _run("pref_iwate_ofunato", "t521_ofunato_wb20250915.html")
    nos = [a["management_no"] for a in res.animals]
    assert len(nos) == 9 and "250105" not in nos


def test_ofunato_stray_today_and_zero_days():
    assert len(_run("pref_iwate_ofunato-2", "t521_ofunato_20261007.html").animals) == 1
    for fx in ("t521_ofunato_wb20240418.html", "t521_ofunato_wb20250915.html"):
        res = _run("pref_iwate_ofunato-2", fx)
        assert res.animals == [] and res.empty_confirmed


def test_hiroshima_stray_dog_today_is_unchanged():
    (a,) = _run("pref_hiroshima-1", "t521_pref_hiroshima-1_20261007.html").animals
    assert (a["management_no"], a["breed"], a["sex"], a["note"]) == ("1HD20260205", "雑種", "雄", "保護時に茶色の皮の首輪を装着")


def test_hiroshima_returned_dogs_are_dropped_and_breed_is_not_sex():
    (a,) = _run("pref_hiroshima-1", "t521_pref_hiroshima-1_wb20250524.html").animals
    assert (a["management_no"], a["breed"], a["sex"], a["age"]) == ("1HD20250058", "雑種", "雌", "推定3歳")


# --- 島根県 松江保健所の収容動物の表（pref_shimane-2） -------------------------------------------------------------
# T521 で pref_shimane の入口を現行一覧に変えたので（judgeB2 F-01）、2023〜2026-02 に子を載せていた表のページを別の slug で読む。
# 表には死亡が書かれないまま行が残る日がある（Wayback 2023-06-02 の 23C130。個別ページの備考は「収容後死亡しました」。最終ゲート F-01）
# ので、表の行のリンクを辿って個別ページを pref_shimane と同じ読み方・同じ除外で読む。

SHIMANE_TABLE = "https://www.pref.shimane.lg.jp/infra/nature/animal/matsue_hoken/doubutu/hogozyouhou_kakobunn/syuyouari.html"
SHIMANE_PAST = "https://www.pref.shimane.lg.jp/infra/nature/animal/matsue_hoken/doubutu/hogozyouhou_kakobunn/"


def _shimane_table(pages: dict[str, str]):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "pref_shimane-2")
    recipe = Recipe.load(ROOT / src.recipe)
    ex = Executor(FakeFetcher({u: (FIX / f).read_text(encoding="utf-8") for u, f in pages.items()}), recipe)
    docs = ex.resolve(src.url)
    return build(src, recipe, docs, ex.visited)


def test_shimane_table_dead_cat_left_in_the_table_is_not_listed():
    res = _shimane_table({SHIMANE_TABLE: "t521_shimane-2_wb20230602.html",
                          SHIMANE_PAST + "dobutu7.html": "t521_shimane-2_dobutu7_wb20230601.html"})
    assert res.animals == [] and not res.empty_confirmed   # 0 頭とも確定しない（読めなかった側で通知に載る）


def test_shimane_table_follows_the_link_and_reads_the_detail_page():
    # 表 2023-02-06 の 22D210 のリンク先 jyohoinu.html は、同じファイル名を後の子が使い回すので、保存（2023-04-21）は 23D1 の頁。
    # ここでは表から個別ページを辿って読めること（と 2023 年の「管理番号・23D1」の書き方）を確かめる
    (a,) = _shimane_table({SHIMANE_TABLE: "t521_shimane-2_wb20230206.html",
                           SHIMANE_PAST + "jyohoinu.html": "t521_shimane-2_jyohoinu_wb20230421.html"}).animals
    assert (a["management_no"], a["species"], a["shelter_date"], a["location"], a["sex"]) == (
        "23D1", "dog", "2023年4月13日", "安来市利弘町地内", "オス")


def test_shimane_table_zero_days_are_empty():
    for fx in ("t521_shimane-2_wb20260315.html", "t521_shimane-2_20261005.html"):
        res = _shimane_table({SHIMANE_TABLE: fx})
        assert res.animals == [] and res.empty_confirmed


def test_shimane_table_with_links_but_unreadable_details_is_not_empty():
    # 表に子のリンクがあるのに個別ページが 1 本も読めない日は 0 頭にしない
    res = build(next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "pref_shimane-2"),
                Recipe.load(ROOT / "recipes" / "pref_shimane-2.yaml"), [],
                [Doc(url=SHIMANE_TABLE, html=(h := (FIX / "t521_shimane-2_wb20250422.html").read_text(encoding="utf-8")),
                     soup=BeautifulSoup(h, "lxml"))])
    assert res.empty_confirmed is False


def test_hiroshima_attributes_split_over_paragraphs():
    got = {a["management_no"]: (a["breed"], a["sex"], a["age"], a["location"]) for a in
           _run("pref_hiroshima-1", "t521_pref_hiroshima-1_wb20251109.html").animals}
    assert got == {"1HD20250250": ("雑種", "雄", "推定8歳", "尾道市因島重井町付近"),
                   "1HD20250269": ("雑種", "雄", "推定5歳", "東広島市高屋町付近")}
