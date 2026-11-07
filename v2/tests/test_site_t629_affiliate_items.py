"""T629: 「迎える準備」枠の広告リンク。犬用品は犬のページ、猫用品は猫のページにだけ出し、A8 の計測用画像も広告コードのとおり出す。

config.json の affiliate の 1 件は {"title", "url", "note", "species"（省略可: dog / cat）, "beacon"（省略可: 計測用画像の URL）}。
その子のページに出す広告が 1 件も無ければ、枠も PR 表示も出さない。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev"}
DOG_ONLY = {"title": "犬のごはん", "url": "https://px.a8.net/svt/ejp?a8mat=DOG", "note": "犬用", "species": "dog",
            "beacon": "https://www16.a8.net/0.gif?a8mat=DOG"}
BOTH = {"title": "用品店", "url": "https://px.a8.net/svt/ejp?a8mat=BOTH", "note": "犬猫用", "beacon": "https://www10.a8.net/0.gif?a8mat=BOTH"}
PR_TEXT = "このページはアフィリエイト広告を利用しています"


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _animal(aid: str, species: str | None, kind: str = "adoption") -> dict[str, Any]:
    return {"id": aid, "source": "s1", "municipality": "テスト市", "prefecture": "徳島県", "kind": kind, "species": species,
            "source_url": "https://example.lg.jp/a", "phone": None, "address": None, "image_url": None, "name": None,
            "sex": None, "age": None, "breed": None, "color": None, "size": None, "management_no": aid, "shelter_date": None,
            "note": None, "location": None}


def _build(tmp_path: Path, items: list[dict[str, Any]]) -> dict[str, str]:
    animals = [_animal("dog000000001", "dog"), _animal("cat000000001", "cat"), _animal("non000000001", None),
               _animal("dogstray00001", "dog", "stray")]
    data = {"date": "2026-11-07", "animals": animals,
            "sources": [{"slug": "s1", "name": "テスト", "municipality": "テスト市", "prefecture": "徳島県", "url": "https://example.lg.jp/a",
                         "status": "ok", "count": 4}]}
    out = tmp_path / "dist"
    _load_build().build_site(data, {**CONFIG, "affiliate": items}, out)
    return {a["id"]: (out / "animals" / a["id"] / "index.html").read_text(encoding="utf-8") for a in animals}


def test_dog_item_only_on_dog_pages_and_no_species_item_on_every_adoption_page(tmp_path: Path):
    pages = _build(tmp_path, [DOG_ONLY, BOTH])
    assert "犬のごはん" in pages["dog000000001"] and "用品店" in pages["dog000000001"]
    assert "犬のごはん" not in pages["cat000000001"] and "用品店" in pages["cat000000001"]
    assert "犬のごはん" not in pages["non000000001"] and "用品店" in pages["non000000001"]


def test_no_box_and_no_pr_notice_when_no_item_fits_the_child(tmp_path: Path):
    pages = _build(tmp_path, [DOG_ONLY])
    assert "迎える準備" in pages["dog000000001"] and PR_TEXT in pages["dog000000001"]
    assert "迎える準備" not in pages["cat000000001"] and PR_TEXT not in pages["cat000000001"]


def test_stray_pages_still_have_no_ads(tmp_path: Path):
    pages = _build(tmp_path, [DOG_ONLY, BOTH])
    assert "迎える準備" not in pages["dogstray00001"] and PR_TEXT not in pages["dogstray00001"]
    assert "a8.net" not in pages["dogstray00001"]


def test_beacon_is_drawn_only_with_its_link_as_a_one_pixel_image(tmp_path: Path):
    pages = _build(tmp_path, [DOG_ONLY, BOTH])
    assert '<img border="0" width="1" height="1" src="https://www16.a8.net/0.gif?a8mat=DOG" alt="">' in pages["dog000000001"]
    assert "www16.a8.net" not in pages["cat000000001"]
    assert '<img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=BOTH" alt="">' in pages["cat000000001"]


def test_links_keep_sponsored_and_nofollow(tmp_path: Path):
    pages = _build(tmp_path, [BOTH])
    assert 'rel="sponsored nofollow noopener"' in pages["cat000000001"]


def test_beacon_with_a_bad_scheme_is_ignored(tmp_path: Path):
    pages = _build(tmp_path, [{**BOTH, "beacon": "javascript:alert(1)"}])
    assert "javascript:" not in pages["cat000000001"]
    assert "用品店" in pages["cat000000001"]


def test_real_config_items_are_well_formed():
    cfg = json.loads((ROOT / "site" / "config.json").read_text(encoding="utf-8"))
    items = cfg["affiliate"]
    assert items, "広告は 2026-11-07 から掲載している（おまえさん指示）"
    for item in items:
        assert item["title"].strip()
        assert urlsplit(item["url"]).hostname == "px.a8.net"
        assert item.get("species") in {None, "dog", "cat"}
        beacon = urlsplit(item["beacon"])
        assert beacon.scheme == "https" and str(beacon.hostname).endswith(".a8.net")
        # 計測用画像は同じ広告のものだけ
        assert item["url"].split("a8mat=")[1] == item["beacon"].split("a8mat=")[1]
