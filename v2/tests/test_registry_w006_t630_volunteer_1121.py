"""W006 T630 個人・ボランティアが自治体のサイトに出した里親募集は、リンクだけにする（2026-11-21）。

おまえさん決定（2026-11-20）。載せているのが自治体ではなく個人・ボランティア・一般の方である 7 掲載元が対象。
レシピは許諾が変わったときのために残す。松本市・福岡県動物愛護協会・熊本県・団体自身のサイト・市民保護は対象外。
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
PHRASE = "個人やボランティアが自治体のサイトに出した里親募集"

TARGETS = [
    "animal_net_nagasaki-2",
    "pref_kagoshima-11",
    "pref_kagoshima-12",
    "city_nagano-5",
    "city_nagano-6",
    "city_nagano-7",
    "fapscsite-3",
]
# 今回入れない（おまえさんの判断待ち）。台帳を変えない
UNTOUCHED = (
    [f"city_matsumoto-{n}" for n in range(2, 4)]
    + [f"zaidan_fukuoka_douai-{n}" for n in (3, 4, 7, 8)]
    + [f"kumamoto_doubutuaigo-{n}" for n in (3, 4)]
    + ["city_nagano-4", "pref_kagoshima-4", "pref_kagoshima-5"]
)


class _NoFetch:
    def get(self, *a, **k):
        raise AssertionError("link_only のページを取得しようとした")


@pytest.mark.parametrize("slug", TARGETS)
def test_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)
    n = NOTES[slug]
    assert "2026-11-20" in n and "T630" in n and PHRASE in n


@pytest.mark.parametrize("slug", TARGETS)
def test_recipe_is_kept(slug):
    s = SOURCES[slug]
    assert s.recipe_path is not None and s.recipe_path.exists()


@pytest.mark.parametrize("slug", TARGETS)
def test_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


@pytest.mark.parametrize("slug", UNTOUCHED)
def test_others_are_untouched(slug):
    assert slug in SOURCES
    assert PHRASE not in NOTES[slug]


def test_only_targets_carry_this_decision():
    carriers = sorted(k for k, n in NOTES.items() if PHRASE in n)
    assert carriers == sorted(TARGETS)
