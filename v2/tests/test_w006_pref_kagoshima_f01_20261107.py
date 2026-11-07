"""W006 鹿児島県 PR #102 の公開ゲート指摘（F-01 掲載日・F-02 備考と写真・F-03 保護場所）への対応（2026-11-07・ネットワークなし）。

fixture は test_w006_pref_kagoshima_20261107.py と同じ（2026-11-07 の実ページ）。
"""

from pathlib import Path

import pytest
import yaml
from collector.fetch import FakeFetcher
from collector.recipe import Recipe
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW_NOTES = {r["slug"]: r.get("note") for r in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]}
HOST = "http://dogcat.pref.kagoshima.jp"
LOST_ACTION = f"{HOST}/Search/Search_lost"
JOUTO_ACTION = f"{HOST}/Search/Search_jouto"
LOST_INDEX = f"{HOST}/Search/Lost_index"
JOUTO_INDEX = f"{HOST}/Search/Jouto_index"


def _fx(name: str) -> str:
    return (FIX / f"w006_pref_kagoshima_{name}_20261107.html").read_text(encoding="utf-8")


def _read(slug: str, entry: str, entry_fx: str, post_fx: str, mutate=lambda h: h):
    action = LOST_ACTION if entry == LOST_INDEX else JOUTO_ACTION
    pages = {entry: _fx(entry_fx), f"{action}#post1": mutate(_fx(post_fx))}
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _p14_cat():
    # 14 ページ目は pager なし（最後のページ）。掲載日が 2024-08 まで遡る
    return _read("pref_kagoshima-12", JOUTO_INDEX, "jouto_index", "keisai_cat_p14")


# --- F-01: 掲載日を残す ------------------------------------------------------------
def test_old_posting_keeps_its_posting_date_in_note_not_in_shelter_date():
    c = _p14_cat()
    assert c.status == "ok", c.error
    by_no = {a["management_no"]: a for a in c.result.animals}
    old = by_no["24C0503"]
    assert "掲載日 2024年08月28日" in old["note"]
    assert "お問い合わせ先 川薩保健所(0996-23-3167)" in old["note"]
    # サイトでは shelter_date が「保護日」と出る。掲載日を入れると誤表示になるので入れない
    assert all(not a.get("shelter_date") for a in c.result.animals)
    assert "掲載日 2025年11月28日" in by_no["25C0517"]["note"]


def test_lost_posts_keep_posting_date_with_body():
    c = _read("pref_kagoshima-7", LOST_INDEX, "lost_index", "klost_cat_p1", lambda h: h.replace("paging_next", "paging_x"))
    assert c.status == "ok", c.error
    first = next(a for a in c.result.animals if a["management_no"] == "26C0481")
    assert "掲載日 2026年11月05日" in first["note"]
    assert "黒白の長毛" in first["note"]          # 迷子の特徴は探す手がかりなので残す
    last = next(a for a in c.result.animals if a["management_no"] == "25C0592")
    assert "掲載日 2026年02月03日" in last["note"]


# --- F-02: 掲載者の事情と個人名を出さない -----------------------------------------------
def test_adoption_listing_does_not_publish_free_text_circumstances():
    c = _p14_cat()
    dump = " ".join(str(v) for a in c.result.animals for v in a.values())
    for leaked in ("亡くな", "高齢", "取り残", "叔父", "ネコかぜ", "屋根裏", "保護した方"):
        assert leaked not in dump, leaked
    # 飼養場所（市町村）だけは備考から取る。県の施設にいる子ではないと分かるように
    by_no = {a["management_no"]: a for a in c.result.animals}
    assert by_no["25C0379"]["location"] == "薩摩川内市"
    assert by_no["25C0517"]["location"] == "志布志市"


def test_person_posted_sources_read_no_image_so_no_filename_in_data():
    for slug, entry, entry_fx, post_fx in (
        ("pref_kagoshima-12", JOUTO_INDEX, "jouto_index", "keisai_cat_p14"),
        ("pref_kagoshima-7", LOST_INDEX, "lost_index", "klost_cat_p1"),
    ):
        c = _read(slug, entry, entry_fx, post_fx, lambda h: h.replace("paging_next", "paging_x"))
        assert c.status == "ok" and c.result.animals
        assert all(not a.get("image_url") for a in c.result.animals), slug
        assert len({a["id"] for a in c.result.animals}) == len(c.result.animals)
    for n in (4, 5, 6, 7, 11, 12):
        raw = yaml.safe_load((ROOT / "recipes" / f"pref_kagoshima-{n}.yaml").read_text(encoding="utf-8"))
        assert "image" not in raw, n


@pytest.mark.parametrize("n", [11, 12])
def test_adoption_recipes_do_not_read_free_text_field(n):
    raw = yaml.safe_load((ROOT / "recipes" / f"pref_kagoshima-{n}.yaml").read_text(encoding="utf-8"))
    note = raw["fields"]["note"]["join"]
    assert not any(part.get("label") == "備考" for part in note)
    assert raw["fields"]["location"]["label"] == "備考" and raw["fields"]["location"]["regex"]    # 飼養場所だけ


# --- F-03: 保護場所が読めない行は動物にしない ----------------------------------------------
@pytest.mark.parametrize("slug", ["pref_kagoshima-4", "pref_kagoshima-5"])
def test_hogo_row_without_location_is_not_ok(slug):
    # 子のいる日の形が未確認のため、保護した犬の一覧（同じ Search_lost の結果。保護場所の欄がある）を代用して確かめる
    ok = _read(slug, LOST_INDEX, "lost_index", "stray_dog")
    assert ok.status == "ok" and len(ok.result.animals) == 3
    assert all(a["location"] for a in ok.result.animals)
    # 保護場所の欄が無い形に変わった日は、location 空のまま ok にしない
    c = _read(slug, LOST_INDEX, "lost_index", "stray_dog", lambda h: h.replace("保護場所", "発見場所"))
    assert c.status != "ok", c.status
    assert not c.result or not c.result.animals


def test_registry_notes_state_the_remaining_limits():
    for n in (6, 7, 11, 12):
        note = RAW_NOTES[f"pref_kagoshima-{n}"]
        assert "古い掲載が残りうる" in note and "掲載日" in note, n
    for n in (11, 12):
        note = RAW_NOTES[f"pref_kagoshima-{n}"]
        assert "備考は読まない" in note and "写真は読まない" in note, n
    assert "1 行に複数匹" in RAW_NOTES["pref_kagoshima-12"]
    for n in (4, 5):
        assert "保護場所" in RAW_NOTES[f"pref_kagoshima-{n}"]
    for n in range(1, 13):
        assert "入口" in RAW_NOTES[f"pref_kagoshima-{n}"] and "区分を選" in RAW_NOTES[f"pref_kagoshima-{n}"], n


def test_recipes_still_load():
    for n in range(1, 13):
        Recipe.load(ROOT / "recipes" / f"pref_kagoshima-{n}.yaml")
