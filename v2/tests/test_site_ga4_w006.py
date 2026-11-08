"""W006 T073 の続き: GA4 の計測タグ。

config.json の ga4_id（G- で始まる測定 ID）があるときだけ、全ページの head に gtag.js を 1 回ずつ入れ、
about に「アクセス解析」の節（Google アナリティクスを使っていること、Cookie、止め方）を出す。
ga4_id が無い・形が違う（タグの注入になりうる文字を含む）ときは何も出さない。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}
GA = "G-TEST12345"
GTAG_SRC = f"https://www.googletagmanager.com/gtag/js?id={GA}"


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build_ga4", ROOT / "site" / "build.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _animal(aid: str) -> dict[str, Any]:
    return {"id": aid, "source": "s1", "municipality": "テスト市", "prefecture": "徳島県", "kind": "adoption", "species": "dog",
            "source_url": "https://example.lg.jp/a", "phone": None, "address": None, "image_url": None, "name": None,
            "sex": None, "age": None, "breed": None, "color": None, "size": None, "management_no": aid, "shelter_date": None,
            "note": None, "location": None}


def _build(tmp_path: Path, cfg: dict[str, Any]) -> dict[str, str]:
    data = {"date": "2026-11-08", "animals": [_animal("dog000000001")],
            "sources": [{"slug": "s1", "name": "テスト", "municipality": "テスト市", "prefecture": "徳島県",
                         "url": "https://example.lg.jp/a", "status": "ok", "count": 1}]}
    out = tmp_path / "dist"
    _load_build().build_site(data, cfg, out)
    return {str(p.relative_to(out)): p.read_text(encoding="utf-8") for p in out.rglob("*.html")}


def test_every_page_has_the_gtag_once_when_ga4_id_is_set(tmp_path: Path) -> None:
    pages = _build(tmp_path, {**CONFIG, "ga4_id": GA})
    assert {"index.html", "about/index.html", "sources/index.html", "404.html", "animals/dog000000001/index.html"} <= set(pages)
    for name, h in pages.items():
        assert h.count(GTAG_SRC) == 1, name
        assert f"gtag('config', '{GA}')" in h, name
        assert h.index(GTAG_SRC) < h.index("</head>"), name


def test_no_tag_and_no_analytics_section_without_ga4_id(tmp_path: Path) -> None:
    pages = _build(tmp_path, dict(CONFIG))
    for name, h in pages.items():
        assert "googletagmanager" not in h, name
    assert "Google アナリティクス" not in pages["about/index.html"]


def test_malformed_ga4_id_is_ignored(tmp_path: Path) -> None:
    pages = _build(tmp_path, {**CONFIG, "ga4_id": "G-1');alert(1);//"})
    for name, h in pages.items():
        assert "googletagmanager" not in h, name
        assert "alert(1)" not in h, name


@pytest.mark.parametrize("bad", ["g-abcd1234", "G-AB", "G-ABCD1234<", "UA-12345-1", "G-ABCD 1234", "G-ABCD1234\nx"])
def test_ga4_id_must_be_the_exact_g_form(bad: str) -> None:
    mod = _load_build()
    assert mod.ga4_id({"ga4_id": bad}) == ""
    assert mod.ga4_head({"ga4_id": bad}) == ""


def test_surrounding_whitespace_is_trimmed_not_embedded() -> None:
    mod = _load_build()
    assert mod.ga4_id({"ga4_id": " G-ABCD1234\n"}) == "G-ABCD1234"
    assert "\n" not in mod.ga4_head({"ga4_id": " G-ABCD1234\n"}).split("id=")[1].split('"')[0]


def test_about_discloses_analytics_and_how_to_opt_out(tmp_path: Path) -> None:
    about = _build(tmp_path, {**CONFIG, "ga4_id": GA})["about/index.html"]
    assert "アクセス解析" in about
    assert "Google アナリティクス" in about
    assert "Cookie" in about
    assert "https://tools.google.com/dlpage/gaoptout" in about
    assert "https://policies.google.com/technologies/partner-sites" in about


def test_production_config_uses_the_oneco_property() -> None:
    cfg = json.loads((ROOT / "site" / "config.json").read_text(encoding="utf-8"))
    assert cfg["ga4_id"] == "G-KEE66C1E8B"
