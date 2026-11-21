"""W006 T630 福岡市動物愛護管理センターの返事（2026-11-19）。

写真や文章の二次利用は遠慮してほしい。公式ホームページと「ずっといっしょ」へのリンクは問題ない。
「わんにゃんよかネット」は閉鎖したので、「福岡市わんにゃん」の表記を「福岡市」へ変えてほしい。
久留米市と同じく、4 掲載元（ずっといっしょ 2 件・市サイト 2 件）はリンクだけを載せ、わんにゃんよかネットの 2 件は台帳から消す。
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

ZUTTO = ["zuttoissho_fukuoka-1", "zuttoissho_fukuoka-2"]
INTERIM = ["city_fukuoka_interim-1", "city_fukuoka_interim-2"]
LINK_ONLY = ZUTTO + INTERIM
CLOSED = ["wannyan_fukuoka-1", "wannyan_fukuoka-2"]


class _NoFetch:
    def get(self, *a, **k):
        raise AssertionError("link_only のページを取得しようとした")


@pytest.mark.parametrize("slug", LINK_ONLY)
def test_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)
    assert s.recipe_path.exists()           # 許諾が変わったときのために残す
    assert "2026-11-19" in NOTES[slug] and "T630" in NOTES[slug]


@pytest.mark.parametrize("slug", LINK_ONLY)
def test_names_do_not_say_wannyan(slug):
    s = SOURCES[slug]
    assert "わんにゃん" not in s.name and "わんにゃん" not in s.municipality
    assert s.municipality == "福岡市"
    assert s.name.startswith("福岡市（")


def test_names_are_the_agreed_ones():
    assert SOURCES["zuttoissho_fukuoka-1"].name == "福岡市（犬譲渡）"
    assert SOURCES["zuttoissho_fukuoka-2"].name == "福岡市（猫譲渡）"
    assert SOURCES["city_fukuoka_interim-1"].name == "福岡市（センターに収容されている犬）"
    assert SOURCES["city_fukuoka_interim-2"].name == "福岡市（センターに収容されている猫）"


@pytest.mark.parametrize("slug", ZUTTO)
def test_zuttoissho_has_no_phone_or_address_from_the_closed_site(slug):
    # 電話・所在地は閉鎖したわんにゃんよかネットの about ページが根拠だった
    d = next(x for x in RAW if x["slug"] == slug)
    for key in ("phone", "address", "verified_phone_url", "verified_address_url"):
        assert d.get(key) is None, key


@pytest.mark.parametrize("slug", INTERIM)
def test_interim_keeps_phone_and_address_from_the_city_page(slug):
    s = SOURCES[slug]
    assert s.phone == "092-691-0131" and s.address
    assert "wannyan" not in (s.verified_phone_url or "") and "wannyan" not in (s.verified_address_url or "")


@pytest.mark.parametrize("slug", INTERIM)
def test_interim_note_drops_the_resume_procedure(slug):
    note = NOTES[slug]
    assert "閉鎖" in note
    for old in ("暫定ページ", "wannyan_fukuoka-1", "enabled: false"):
        assert old not in note, old


@pytest.mark.parametrize("slug", LINK_ONLY)
def test_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


@pytest.mark.parametrize("slug", CLOSED)
def test_closed_wannyan_entries_are_gone(slug):
    assert slug not in SOURCES
    assert not (ROOT / "recipes" / f"{slug}.yaml").exists()


def test_other_fukuoka_sources_are_untouched():
    z = [s for s in SOURCES.values() if s.slug.startswith("zaidan_fukuoka_douai-")]
    assert len(z) == 8 and all(s.mode != "link_only" for s in z)
    assert SOURCES["city_kurume-1"].mode == "link_only"


def test_no_wannyan_wording_in_public_fields():
    for s in SOURCES.values():
        if s.prefecture == "福岡県":
            assert "福岡市わんにゃん" not in s.name + s.municipality, s.slug
