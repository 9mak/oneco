"""W006 T616（reviewer F-01）: 県のまとめページの電話・所在地は運営元のもので、収容先そのものではない。

台帳の `contact_scope: operator` を個体に引き継ぎ、個体ページでは「電話」「所在地」でなく「問い合わせ先」と出す。
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"

OPERATOR_SLUGS = sorted([
    "mie_dakc", "pref_toyama", "spec_pref_gifu", "pref_iwate", "shuyojoho_tokyo-1", "shuyojoho_tokyo-2",
    "pref_ishikawa", "pref_fukushima-1", "pref_fukushima-2", "animal_net_nagasaki-1", "animal_net_nagasaki-2",
    "animal_net_nagasaki-3", "animal_net_nagasaki-4", "pref_shizuoka", "kochi_apc", "pref_tottori",
])


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _animals() -> dict[str, Any]:
    a = json.loads((FIX / "animals_tokushima.json").read_text(encoding="utf-8"))
    return {"date": "2026-09-28", "animals": a["animals"], "sources": a["sources"]}


def test_registry_contact_scope_defaults_to_facility_and_operator_is_the_16_hubs():
    srcs = load_sources()
    scopes = {s.contact_scope for s in srcs}
    assert scopes <= {"facility", "operator"}
    ops = sorted(s.slug for s in srcs if s.contact_scope == "operator")
    assert ops == OPERATOR_SLUGS
    by = {s.slug: s for s in srcs}
    assert all(by[s].phone and by[s].address for s in OPERATOR_SLUGS)
    assert by["city_yokkaichi_pdf"].contact_scope == "facility"


def test_extract_copies_contact_scope_to_each_animal():
    src = next(s for s in load_sources() if s.slug == "pref_fukushima-4")
    html = (FIX / "fix1009_fukushima-4_20261005.html").read_text(encoding="utf-8")
    recipe = Recipe.load(ROOT / src.recipe)
    docs = [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))]
    res = build(dataclasses.replace(src, contact_scope="operator"), recipe, docs)
    assert res.animals and all(a["contact_scope"] == "operator" for a in res.animals)
    res2 = build(src, recipe, docs)
    assert res2.animals and all(a["contact_scope"] == "facility" for a in res2.animals)


def test_site_labels_operator_contact_as_inquiry(tmp_path: Path):
    data = _animals()
    op = dict(data["animals"][0])
    op.update({"id": "operator0001", "phone": "03-3302-3507", "address": "〒156-0056 東京都世田谷区八幡山二丁目9番地11号",
               "contact_scope": "operator"})
    fac = dict(data["animals"][1])
    fac.update({"id": "facility0001", "phone": "088-621-2104", "address": "徳島市中前川町"})
    legacy = dict(data["animals"][2])
    legacy.update({"id": "legacy000001", "phone": "088-621-2104", "address": "徳島市中前川町"})
    legacy.pop("contact_scope", None)  # 旧データには項目が無い → facility 扱い
    data["animals"] += [op, fac, legacy]
    out = tmp_path / "dist"
    _load_build().build_site(data, {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}, out)

    d = (out / "animals" / "operator0001" / "index.html").read_text(encoding="utf-8")
    assert "<dt>問い合わせ先</dt>" in d and "03-3302-3507" in d
    assert "<dt>問い合わせ先の所在地</dt>" in d and "八幡山" in d
    assert "<dt>電話</dt>" not in d and "<dt>所在地</dt>" not in d
    for aid in ("facility0001", "legacy000001"):
        f = (out / "animals" / aid / "index.html").read_text(encoding="utf-8")
        assert "<dt>電話</dt>" in f and "<dt>所在地</dt>" in f and "問い合わせ先" not in f
