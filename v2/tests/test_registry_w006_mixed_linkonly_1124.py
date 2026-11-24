"""W006 保護された子と飼い主の手放しが同じページに混ざる掲載元は、全部リンクのみ・写真なし（POLICY.md 方針 41。2026-11-24 おまえさん決定）。

長野市 -5〜-7・福井 -3 は 2026-11-21 の決定で既にリンクのみ。ここでは今のままであることを確かめる。レシピは許諾が変わったときのために残す。
"""

from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
NOTES = {d["slug"]: d.get("note") or "" for d in RAW}
PHRASE = "保護された子と飼い主の手放しの掲載が同じページに混ざり、掲載ごとに見分けられないためリンクのみ（POLICY.md 方針 41）"

NEW = (
    [f"city_matsumoto-{n}" for n in range(4, 10)]
    + ["kumamoto_doubutuaigo-5", "kumamoto_doubutuaigo-6", "city_aomori-1"]
)
ALREADY = ["city_nagano-5", "city_nagano-6", "city_nagano-7", "fapscsite-3"]


class _NoFetch:
    def get(self, *a: object, **k: object) -> None:
        raise AssertionError("link_only のページを取得しようとした")


@pytest.mark.parametrize("slug", NEW + ALREADY)
def test_link_only_without_photo(slug: str) -> None:
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)


@pytest.mark.parametrize("slug", NEW)
def test_note_has_reason_and_decision_date(slug: str) -> None:
    n = NOTES[slug]
    assert "2026-11-24" in n and PHRASE in n


@pytest.mark.parametrize("slug", NEW + ALREADY)
def test_recipe_is_kept(slug: str) -> None:
    s = SOURCES[slug]
    assert s.recipe_path is not None and s.recipe_path.exists()


@pytest.mark.parametrize("slug", NEW + ALREADY)
def test_collect_does_not_fetch(slug: str) -> None:
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


@pytest.mark.parametrize("slug", ["city_matsumoto-4", "city_aomori-1"])
def test_earlier_facts_in_note_are_kept(slug: str) -> None:
    assert "2026-10-05 T519" in NOTES[slug]


@pytest.mark.parametrize("slug", ["kumamoto_doubutuaigo-5", "kumamoto_doubutuaigo-6"])
def test_kumamoto_keeps_the_record_of_the_ok_reply(slug: str) -> None:
    assert "2026-11-13 熊本県" in NOTES[slug] and "写真は表示してよい" in NOTES[slug]


def test_only_targets_carry_this_decision() -> None:
    assert sorted(k for k, n in NOTES.items() if PHRASE in n) == sorted(NEW)
