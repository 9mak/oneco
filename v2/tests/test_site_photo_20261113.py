"""写真の出ない子が多い件（2026-11-13 おまえさん「写真のある子を先に並べる」「写真なしの絵を変える」。ネットワークなし）。

- 都道府県ページの並びは、区分の順（里親募集 → 保護中 → 迷子 → 探してます）を保ったまま、同じ区分の中では写真のある子を先に出す
  （写真を止めている子は写真なしとして後ろ。元の並びは区分・写真の有無ごとに保つ）
- 写真なしの枠の絵は、犬は犬・猫は猫のシルエット（それ以外は今の肉球）
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_photo_1113", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
SAGA = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = SAGA["animals"][0]


def _a(id_: str, **kw: Any) -> dict[str, Any]:
    return {**BASE, "id": id_, **kw}


def _build(tmp_path: Path, animals: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None) -> Path:
    data = {"date": "2026-11-13", "animals": animals, "sources": sources or SAGA["sources"]}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    B.build(p, out, CONFIG)
    return out


def _order(out: Path) -> list[str]:
    h = (out / "pref" / "佐賀県" / "index.html").read_text(encoding="utf-8")
    return re.findall(r'href="/animals/([^/]+)/"', h)


def test_cards_with_photos_come_first_within_each_kind(tmp_path: Path):
    animals = [
        _a("shel_nophoto", kind="sheltered", image_url=None),
        _a("adop_nophoto", kind="adoption", image_url=None),
        _a("shel_photo01", kind="sheltered"),
        _a("adop_photo01", kind="adoption"),
        _a("adop_nophot2", kind="adoption", image_url=None),
        _a("adop_photo02", kind="adoption"),
        _a("lost_photo01", kind="lost"),
    ]
    assert _order(_build(tmp_path, animals)) == [
        "adop_photo01", "adop_photo02", "adop_nophoto", "adop_nophot2",   # 里親募集: 写真あり → なし（それぞれ元の順）
        "shel_photo01", "shel_nophoto",                                    # 保護中
        "lost_photo01",                                                    # 探してます
    ]


def test_withheld_photos_count_as_no_photo(tmp_path: Path):
    sources = SAGA["sources"] + [{**SAGA["sources"][0], "slug": "pref_saga-pending", "photo": "pending"}]
    animals = [_a("withheld0001", kind="adoption", source="pref_saga-pending"), _a("shown0000001", kind="adoption")]
    assert _order(_build(tmp_path, animals, sources)) == ["shown0000001", "withheld0001"]


def test_placeholder_shows_a_dog_or_cat_silhouette(tmp_path: Path):
    out = _build(tmp_path, [_a("dognophoto01", species="dog", image_url=None), _a("catnophoto01", species="cat", image_url=None),
                            _a("othnophoto01", species="other", image_url=None)])
    assert 'class="ph ph-dog"' in (out / "animals" / "dognophoto01" / "index.html").read_text(encoding="utf-8")
    assert 'class="ph ph-cat"' in (out / "animals" / "catnophoto01" / "index.html").read_text(encoding="utf-8")
    oth = (out / "animals" / "othnophoto01" / "index.html").read_text(encoding="utf-8")
    assert 'class="ph"' in oth and "ph-dog" not in oth and "ph-cat" not in oth
    css = (out / "style.css").read_text(encoding="utf-8")
    for sp in ("dog", "cat"):
        assert re.search(rf'\.ph-{sp}::before\{{[^}}]*url\("data:image/svg\+xml,', css), sp
        assert f".ph-{sp}::after" in css           # 肉球の指は消す
