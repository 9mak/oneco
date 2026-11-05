"""W006 T630: 岡山市（返事 2026-11-02「表示してよい」）と埼玉県（返事 2026-11-05 県庁 生活衛生課がとりまとめ）。

埼玉県: 県内の収容動物の情報は写真を含め掲載して差し支えない（政令・中核市を除く）。
個人保護の 8 件は、返事の「収容動物」に個人保護が入るか不明で県庁に確認中のため pending のまま。
"""

from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

NOTES = {
    d["slug"]: d.get("note") or ""
    for d in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
}

SAITAMA_OK = [
    f"pref_saitama_{k}"
    for k in (
        "nanbu asaka kasukabe souka konosu higashimatsuyama sakado sayama kazo satte "
        "kumagaya honjo chichibu center_honsho center_minami joto_inu "
        "joto_neko_honsho joto_neko_minami"
    ).split()
]
SAITAMA_PENDING = [
    f"pref_saitama_{k}-2"
    for k in "nanbu asaka chichibu kazo kumagaya sakado center_honsho center_minami".split()
]


def test_counts():
    assert len(SAITAMA_OK) == 18 and len(SAITAMA_PENDING) == 8


@pytest.mark.parametrize("slug", ["city_okayama", *SAITAMA_OK])
def test_photo_ok(slug):
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "ok")


@pytest.mark.parametrize("slug", SAITAMA_PENDING)
def test_saitama_personal_stays_pending(slug):
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "pending")
    assert "確認中" in NOTES[slug]
