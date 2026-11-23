"""W006 POLICY.md 方針 5・44・9・41 の台帳の直し（2026-11-23）。

- 方針 44・5: 町田市の迷子の捜索 3 ページ（-2〜-4）は町田市の可の返事の範囲なので写真ありに戻す
- 方針 5: 「飼い主の写真だから」で photo: no にしていた残り 13 掲載元は、可の返事がまだ無いので pending
- 方針 9: 団体自身のサイト（nyantomo・spec_aniwel）は台帳から外し、discover は excluded にして通知し直さない
- 方針 41: 越谷市「新しい飼い主探し掲示板」は飼い主の手放しなのでリンクのみで足す
"""

import re
from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
BY = {d["slug"]: d for d in RAW}
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
KNOWN = yaml.safe_load((ROOT / "registry" / "discover_known.yaml").read_text(encoding="utf-8"))

MACHIDA = ["city_machida-2", "city_machida-3", "city_machida-4"]
PENDING13 = [
    "aniwel_okinawa-3", "aniwel_okinawa-4", "animal_net_nagasaki-3", "city_maebashi-2", "city_funabashi-4",
    "pref_tottori-2", "city_miyazaki-4", "city_miyazaki-5", "kochi_apc-3", "kochi_apc-4",
    "spec_douaicenter-9", "spec_douaicenter-10", "spec_douaicenter-11",
]


def _note(slug: str) -> str:
    return str(BY[slug].get("note") or "")


@pytest.mark.parametrize("slug", MACHIDA)
def test_machida_lost_pages_show_photos_again(slug: str) -> None:
    assert SOURCES[slug].photo == "ok"
    n = _note(slug)
    assert "2026-11-09" in n and "返事" in n and "方針 5・44" in n
    assert "出さない" not in n


@pytest.mark.parametrize("slug", PENDING13)
def test_owner_photo_pages_are_pending_not_no(slug: str) -> None:
    assert SOURCES[slug].photo == "pending"
    n = _note(slug)
    assert "確認が取れるまで出さない" in n and "方針 5" in n
    assert "photo: no" not in n and "町田市 -2〜-4 と同じ扱い" not in n and "町田の前例" not in n


def test_no_note_keeps_the_owner_photo_reason() -> None:
    for slug, d in BY.items():
        assert "迷子の写真は出さない" not in str(d.get("note") or ""), slug
        assert "旭川市の返事にかかわらず出さない" not in str(d.get("note") or ""), slug


def test_other_no_sources_are_untouched() -> None:
    """自治体に不可と言われた no・リンクのみの no は今回触らない（理由が飼い主の写真ではない）。"""
    for slug in ("city_koshigaya_kojin", "animal_net_nagasaki-2", "pref_kagoshima-11", "pref_kagoshima-12"):
        assert SOURCES[slug].photo == "no"


def test_org_sites_are_removed_from_registry() -> None:
    for slug in ("nyantomo", "spec_aniwel"):
        assert slug not in SOURCES
        assert not (ROOT / "recipes" / f"{slug}.yaml").exists()


def test_discover_known_excludes_org_sites_without_renotifying() -> None:
    d = KNOWN["domains"]
    for dom in ("aniwel.jp", "nyantomo.jp"):
        assert d[dom]["status"] == "excluded" and "方針 9" in d[dom]["note"] and "団体自身のサイト" in d[dom]["note"], dom
    assert not {"nyantomo", "spec_aniwel"} & set(d["pref.hokkaido.lg.jp"]["slugs"])
    for k, v in KNOWN["pages"].items():
        assert not {"nyantomo", "spec_aniwel"} & set(v.get("slugs") or []), k


KOSHIGAYA_URL = "https://www.city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/jouto/keijiban.html"
KOSHIGAYA_KEY = "city.koshigaya.saitama.jp/kurashi_shisei/fukushi/hokenjo/pet/jouto/keijiban.html"


def test_koshigaya_keijiban_is_link_only() -> None:
    s = SOURCES["city_koshigaya-5"]
    assert (s.mode, s.photo, s.enabled, s.kind) == ("link_only", "no", True, "adoption")
    assert s.url == KOSHIGAYA_URL and s.phone == "048-969-8511"
    assert "飼い主が自分のペットを手放すための譲渡なのでリンクのみ（POLICY.md 方針 41）" in _note("city_koshigaya-5")


def test_koshigaya_keijiban_does_not_fetch() -> None:
    class NoFetch:
        def get(self, *a: object, **k: object) -> None:
            raise AssertionError("link_only のページを取得しようとした")

    assert collect_one(SOURCES["city_koshigaya-5"], NoFetch()).status == "link_only"  # type: ignore[arg-type]


def test_koshigaya_discover_known_follows_registry() -> None:
    v = KNOWN["pages"][KOSHIGAYA_KEY]
    assert v["status"] == "covered" and v["slugs"] == ["city_koshigaya-5"]
    assert "リンクのみ" in v["note"] and "方針 41" in v["note"]
    assert "載せない" not in v["note"]


def test_koshigaya_3_note_matches_registry() -> None:
    n = _note("city_koshigaya-3")
    assert "新しい飼い主探し掲示板" in n and "city_koshigaya-5" in n and "リンクのみ" in n
    assert "新しい飼い主探し掲示板（飼い主からの譲渡）・譲渡団体の紹介は載せない" not in n


def test_toyama_niikawa_note_has_the_basis() -> None:
    assert "2026-10-27 富山県から写真の表示は可と返事（T630）" in _note("pref_toyama_niikawa")


def test_no_stale_unspecified_is_ok_note() -> None:
    for slug, d in BY.items():
        assert not re.search(r"未指定[＝=]\s*ok", str(d.get("note") or "")), slug
    for slug in ("city_saitama-3", "city_saitama-4", "city_akita-4", "pref_iwate_chubu-2"):
        assert "未指定＝pending" in _note(slug), slug
