"""W006 鹿児島県 PR #102 の公開ゲート第 2 回の指摘（F-01 除外語は終わった言い方だけ・F-02 場所が読めない行は 0 頭にしない・
F-03 -4/-5 も備考の自由記述を読まない・F-04 トライアル中の判断の記録）への対応（2026-11-07・ネットワークなし）。
fixture は test_w006_pref_kagoshima_20261107.py と同じ（2026-11-07 の実ページ）。
"""

from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import Source, load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW_NOTES = {r["slug"]: r.get("note") for r in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]}
HOST = "http://dogcat.pref.kagoshima.jp"
LOST_INDEX = f"{HOST}/Search/Lost_index"
JOUTO_INDEX = f"{HOST}/Search/Jouto_index"
LOST_ACTION = f"{HOST}/Search/Search_lost"
JOUTO_ACTION = f"{HOST}/Search/Search_jouto"
LOST_GROUP = ["pref_kagoshima-1", "pref_kagoshima-3", "pref_kagoshima-4", "pref_kagoshima-5"]
HOGO = ["pref_kagoshima-4", "pref_kagoshima-5"]


def _fx(name: str) -> str:
    return (FIX / f"w006_pref_kagoshima_{name}_20261107.html").read_text(encoding="utf-8")


def _read(slug, entry, entry_fx, post_fx, mutate=lambda h: h):
    action = LOST_ACTION if entry == LOST_INDEX else JOUTO_ACTION
    pages = {entry: _fx(entry_fx), f"{action}#post1": mutate(_fx(post_fx).replace("paging_next", "paging_x"))}
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _stray(slug, mutate=lambda h: h):
    return _read(slug, LOST_INDEX, "lost_index", "stray_dog", mutate)


def _stray_with(slug, phrase):
    return _stray(slug, lambda h: h.replace("鹿屋市笠之原町で保護されました", f"鹿屋市笠之原町で保護されました。{phrase}"))


# --- F-01: 今いる子の備考に出る言い方では落とさない（3 頭のまま） -------------------------
LIVE_PHRASES = [
    "飼い主が見つかるまで預かります",
    "飼い主が見つかりません",
    "飼主が見つかるまで保護します",
    "飼い主が見つかりましたらご連絡ください",
    "返還できるよう探しています",
    "お返しできるよう飼い主さんを探しています",
    "解決に向けて調整中です",
    "見つかるまで預かります",
]


@pytest.mark.parametrize("phrase", LIVE_PHRASES)
@pytest.mark.parametrize("slug", LOST_GROUP)
def test_live_animal_notes_do_not_drop_rows(slug, phrase):
    c = _stray_with(slug, phrase)
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in c.result.animals] == ["26D0310", "26D0309", "26D0308"]


FINISHED_PHRASES = [
    "飼い主が見つかりました。",
    "飼い主さんが見つかりました！",
    "飼主が見つかりました。",
    "飼い主が見つかりましたので掲載を終了します",
    "飼い主のもとに戻りました",
    "飼い主さんのもとへ帰りました",
    "飼い主さんと一緒に帰りました",
    "返還しました",
    "返還済み",
    "お返ししました",
    "解決しました",
    "解決済み",
]


@pytest.mark.parametrize("phrase", FINISHED_PHRASES)
@pytest.mark.parametrize("slug", LOST_GROUP)
def test_finished_phrases_still_drop_returned_rows(slug, phrase):
    c = _stray_with(slug, phrase)
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in c.result.animals] == ["26D0309", "26D0308"], phrase


@pytest.mark.parametrize("n", [1, 3, 4, 5])
def test_lost_recipes_have_no_stem_only_words(n):
    raw = yaml.safe_load((ROOT / "recipes" / f"pref_kagoshima-{n}.yaml").read_text(encoding="utf-8"))
    for w in raw["row_filter"]["text_lacks"]:
        assert w not in ("返還", "お返し", "解決", "見つかりました", "飼い主が見つか", "飼主が見つか"), w


# --- F-02: 場所が読めない行は 0 頭と読まず、failed にする --------------------------------
@pytest.mark.parametrize("slug", HOGO)
def test_unreadable_location_day_is_failed_not_empty(slug):
    c = _stray(slug, lambda h: h.replace("保護場所", "発見場所"))
    assert c.status in ("failed", "ambiguous_empty"), c.status
    assert not (c.result and c.result.empty_confirmed)


@pytest.mark.parametrize("slug", HOGO)
def test_location_without_place_word_is_failed(slug):
    def mutate(h):
        return h.replace("鹿屋市</td>", "不明</td>").replace("西之表市</td>", "不明</td>").replace("徳之島町</td>", "不明</td>")

    c = _stray(slug, mutate)
    assert c.status in ("failed", "ambiguous_empty"), c.status
    assert not (c.result and c.result.empty_confirmed)


@pytest.mark.parametrize("slug", HOGO)
def test_one_unreadable_row_does_not_hide_the_others(slug):
    c = _stray(slug, lambda h: h.replace("鹿屋市</td>", "不明</td>"))
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in c.result.animals] == ["26D0309", "26D0308"]
    assert any("必須項目" in d.reason for d in c.result.dropped)


@pytest.mark.parametrize("n", [4, 5])
def test_hogo_recipe_comment_matches_behavior(n):
    txt = (ROOT / "recipes" / f"pref_kagoshima-{n}.yaml").read_text(encoding="utf-8")
    assert "0 頭にならず ok にもならない" not in txt
    assert "field_required" in txt and "field_has_any" not in txt


def _src() -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="東京都", url="https://x.jp/a/", kind="stray", species="dog")


def test_field_required_engine_drops_row_without_counting_as_excluded():
    html = "<table class='t'><tr><th>No</th><td>1</td></tr><tr><th>場所</th><td>不明</td></tr></table>"
    recipe = Recipe.from_dict({"rows": "table.t", "empty_container": "table",
                               "row_filter": {"field_required": {"location": ["市"]}},
                               "fields": {"management_no": {"label": "No"}, "location": {"label": "場所"}}})
    doc = Doc(url="https://x.jp/a", html=html, soup=BeautifulSoup(html, "lxml"))
    res = build(_src(), recipe, [doc])
    assert res.animals == [] and not res.empty_confirmed and not res.ambiguous_empty
    assert res.rows == 1 and [d.reason for d in res.dropped] == ["必須項目が読めない（location）"]


def test_field_required_is_valid_in_schema():
    base = {"rows": "table.t", "fields": {"location": {"label": "場所"}}}
    ok = validate_recipe_dict({**base, "row_filter": {"field_required": {"location": ["市"]}}}, "https://x.jp/a/")
    assert not [e for e in ok if "field_required" in str(e)]
    bad = validate_recipe_dict({**base, "row_filter": {"field_required": ["市"]}}, "https://x.jp/a/")
    assert any("field_required" in str(e) for e in bad)


# --- F-03: -4/-5 も備考の自由記述は読まない -----------------------------------------------
@pytest.mark.parametrize("slug", HOGO)
def test_hogo_note_has_only_contact(slug):
    leak = "ご連絡は山田太郎 090-1111-2222 まで"
    c = _stray(slug, lambda h: h.replace("首輪等はつけていませんでした。", leak))
    assert c.status == "ok", c.error
    dump = " ".join(str(v) for a in c.result.animals for v in a.values())
    assert "山田太郎" not in dump and "090-1111-2222" not in dump
    first = next(a for a in c.result.animals if a["management_no"] == "26D0310")
    assert first["note"] == "お問い合わせ先 鹿屋保健所(0994-52-2113)"
    assert first["location"] == "鹿屋市" and first["shelter_date"] == "2026年11月06日"


@pytest.mark.parametrize("n", [4, 5])
def test_hogo_recipes_do_not_read_free_text_field(n):
    raw = yaml.safe_load((ROOT / "recipes" / f"pref_kagoshima-{n}.yaml").read_text(encoding="utf-8"))
    parts = raw["fields"]["note"]["join"]
    assert not any(p.get("label") == "備考" for p in parts)


# --- F-04: トライアル中の子は載せる（掲載元が譲渡対象として載せ、備考にそのまま書いてある） ----------
def test_trial_rows_stay_listed_with_trial_note():
    c = _read("pref_kagoshima-2", JOUTO_INDEX, "jouto_index", "douai_dog")
    assert c.status == "ok", c.error
    by_no = {a["management_no"]: a for a in c.result.animals}
    assert len(by_no) == 7
    assert "トライアル(お試し)実施中" in by_no["26D0277"]["note"]
    assert "トライアル(お試し)実施中" in by_no["26D0123"]["note"]


def test_registry_note_records_trial_decision():
    assert "トライアル" in RAW_NOTES["pref_kagoshima-2"]
