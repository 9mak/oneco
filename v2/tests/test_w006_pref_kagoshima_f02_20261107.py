"""W006 鹿児島県 PR #102 の残りの指摘（2026-11-07・ネットワークなし）。

1. 迷子を探している方の情報（-6・-7）は備考の自由記述を読まない（探す本人が書く欄で、電話・氏名が入っても落とせない）。
2. 返還済み・譲渡済みの行を除く語を広げる（子が載っている今日の fixture が 1 頭も落ちないことも固定）。
fixture は test_w006_pref_kagoshima_20261107.py と同じ（2026-11-07 の実ページ）。
"""

from pathlib import Path

import pytest
import yaml
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
HOST = "http://dogcat.pref.kagoshima.jp"
LOST_ACTION = f"{HOST}/Search/Search_lost"
JOUTO_ACTION = f"{HOST}/Search/Search_jouto"
LOST_INDEX = f"{HOST}/Search/Lost_index"
JOUTO_INDEX = f"{HOST}/Search/Jouto_index"


def _fx(name: str) -> str:
    return (FIX / f"w006_pref_kagoshima_{name}_20261107.html").read_text(encoding="utf-8")


def _read(slug: str, entry: str, entry_fx: str, post_fx: str, mutate=lambda h: h):
    action = LOST_ACTION if entry == LOST_INDEX else JOUTO_ACTION
    pages = {entry: _fx(entry_fx), f"{action}#post1": mutate(_fx(post_fx).replace("paging_next", "paging_x"))}
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _read_lost_group(slug: str, mutate=lambda h: h):
    return _read(slug, LOST_INDEX, "lost_index", "stray_dog", mutate)


def _read_adoption_group(slug: str, mutate=lambda h: h):
    return _read(slug, JOUTO_INDEX, "jouto_index", "douai_dog", mutate)


# --- 1. 探している方の備考は読まない ---------------------------------------------------
def test_seeker_note_has_only_posting_date_and_contact():
    c = _read("pref_kagoshima-7", LOST_INDEX, "lost_index", "klost_cat_p1")
    assert c.status == "ok", c.error
    first = next(a for a in c.result.animals if a["management_no"] == "26C0481")
    assert first["note"] == "掲載日 2026年11月05日　お問い合わせ先 出水保健所(0996-62-1636)"
    assert all("行方不明" not in a["note"] for a in c.result.animals)


def test_seeker_free_text_with_personal_contact_is_dropped():
    leak = "ご連絡は山田太郎 090-1111-2222 まで"
    c = _read(
        "pref_kagoshima-7", LOST_INDEX, "lost_index", "klost_cat_p1",
        lambda h: h.replace("黒白の長毛", leak),
    )
    assert c.status == "ok", c.error
    dump = " ".join(str(v) for a in c.result.animals for v in a.values())
    assert "山田太郎" not in dump and "090-1111-2222" not in dump


@pytest.mark.parametrize("n", [6, 7])
def test_seeker_recipes_do_not_read_free_text_field(n):
    raw = yaml.safe_load((ROOT / "recipes" / f"pref_kagoshima-{n}.yaml").read_text(encoding="utf-8"))
    parts = raw["fields"]["note"]["join"]
    assert not any(p.get("label") == "備考" for p in parts)
    assert "image" not in raw


# --- 2. 返還済み・譲渡済みの行を除く語 -------------------------------------------------
LOST_WORDS = ["帰りました", "戻りました", "飼い主が見つかりました。", "飼主が見つかりました。", "返還しました", "返還済み", "お返ししました", "解決しました", "解決済み"]   # 終わった言い方だけ（語幹止まりは g テストで禁止）
ADOPT_WORDS = ["譲渡済みです", "譲渡済みとなりました", "譲渡済みになりました", "譲渡しました", "譲渡されました", "決まりました。", "決まりました！", "新しい飼い主さんのもと", "新しい飼い主のもと", "新しい家族のもと", "新しい家族になりました"]


@pytest.mark.parametrize("slug", ["pref_kagoshima-1", "pref_kagoshima-3", "pref_kagoshima-4", "pref_kagoshima-5"])
def test_lost_group_today_rows_all_stay(slug):
    c = _read_lost_group(slug)
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in c.result.animals] == ["26D0310", "26D0309", "26D0308"]


@pytest.mark.parametrize("word", LOST_WORDS)
@pytest.mark.parametrize("slug", ["pref_kagoshima-1", "pref_kagoshima-3", "pref_kagoshima-4", "pref_kagoshima-5"])
def test_lost_group_drops_returned_rows(slug, word):
    c = _read_lost_group(slug, lambda h: h.replace("鹿屋市笠之原町で保護されました", f"鹿屋市笠之原町で保護されました。{word}"))
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in c.result.animals] == ["26D0309", "26D0308"], word


@pytest.mark.parametrize("slug", ["pref_kagoshima-2", "pref_kagoshima-8", "pref_kagoshima-9", "pref_kagoshima-10", "pref_kagoshima-11", "pref_kagoshima-12"])
def test_adoption_group_today_rows_all_stay(slug):
    c = _read_adoption_group(slug)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 7


@pytest.mark.parametrize("word", ADOPT_WORDS)
@pytest.mark.parametrize("slug", ["pref_kagoshima-2", "pref_kagoshima-8", "pref_kagoshima-9", "pref_kagoshima-10", "pref_kagoshima-11", "pref_kagoshima-12"])
def test_adoption_group_drops_adopted_rows(slug, word):
    c = _read_adoption_group(slug, lambda h: h.replace("愛称『洸太郎』", f"愛称『洸太郎』<br />{word}"))
    assert c.status == "ok", c.error
    nos = [a["management_no"] for a in c.result.animals]
    assert len(nos) == 6 and "26D0277" not in nos, word


# 今日の実ページの子を落とさない: 「決まりましたら」（これから）と、複数匹の行の中の 1 匹だけ「既に譲渡済み」
@pytest.mark.parametrize("phrase", ["里親さんが決まりましたら、避妊手術を実施します", "数字を未記載の子（写真左上）は既に譲渡済み。"])
@pytest.mark.parametrize("slug", ["pref_kagoshima-2", "pref_kagoshima-12"])
def test_adoption_group_keeps_rows_with_future_or_partial_phrases(slug, phrase):
    c = _read_adoption_group(slug, lambda h: h.replace("愛称『洸太郎』", f"愛称『洸太郎』<br />{phrase}"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 7


# --- 3. 飼養場所の先頭の読点（「現在は，鹿屋市で飼養」の全角コンマ）を含めない ---------------------
@pytest.mark.parametrize("comma", ["，", ",", "、"])
def test_adoption_location_has_no_leading_comma(comma):
    c = _read(
        "pref_kagoshima-12", JOUTO_INDEX, "jouto_index", "keisai_cat_p1",
        lambda h: h.replace("現在、日置市日吉町で飼養", f"現在は{comma}日置市日吉町で飼養"),
    )
    assert c.status == "ok", c.error
    locs = [a.get("location") for a in c.result.animals if a.get("location")]
    assert "日置市日吉町" in locs
    assert all(loc[0] not in ",，、" for loc in locs)


def test_registry_notes_record_old_posting_decision_and_seeker_note():
    raw = {r["slug"]: r.get("note") for r in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]}
    for n in (6, 7, 11, 12):
        assert "古い掲載は外さない" in raw[f"pref_kagoshima-{n}"], n
    for n in (6, 7):
        assert "備考は探している本人の自由記述" in raw[f"pref_kagoshima-{n}"], n
