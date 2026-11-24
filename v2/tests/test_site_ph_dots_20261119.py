"""写真なしの枠の絵を、ロゴと同じ色の丸 2 つにする（2026-11-19 おまえさん「agy の丸 2 つに差し替えて」。ネットワークなし）。

agy と作った試作プレビュー（2026-11-15 の UI 刷新の見た目の元）の写真なしの枠は、ロゴ「ふたつの円」を小さくした
コーラル（犬のポム）とブルーグリーン（猫のビリー）の丸 2 つ（.ph-dots）だった。UI 刷新のときにここだけ
2026-11-13 の灰色の犬・猫のシルエット（それ以外は肉球）が残っていたので、プレビューに合わせる。

- 絵は種別で変えない（犬・猫・その他・種別なしのどれも丸 2 つ）。枠の class は ph だけ
- 丸は 14px・4px 重ねる・半透明。飾りなので読み上げない（aria-hidden）
- 丸と文（と「自治体のページで写真を見る」ボタン）をひとまとまりで枠の中央に置く
- 文言・文字の大きさと色・枠の色・ボタンは変えない
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_ph_dots_1119", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
SAGA = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = SAGA["animals"][0]   # 佐賀県・保護中の犬・写真あり
PENDING = SAGA["sources"] + [{**SAGA["sources"][0], "slug": "pref_saga-pending", "photo": "pending"}]


def _a(id_: str, **kw: Any) -> dict[str, Any]:
    return {**BASE, "id": id_, **kw}


def _build(tmp_path: Path, animals: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None) -> Path:
    data = {"date": "2026-11-19", "animals": animals, "sources": sources or SAGA["sources"]}
    out = tmp_path / "dist"
    B.build_site(data, CONFIG, out)
    return out


def _animal(out: Path, id_: str) -> str:
    return (out / "animals" / id_ / "index.html").read_text(encoding="utf-8")


def _card(out: Path, id_: str) -> str:
    html = (out / "pref" / "佐賀県" / "index.html").read_text(encoding="utf-8")
    m = re.search(rf'<a class="card" href="/animals/{id_}/".*?</a>\n', html, re.S)
    assert m, id_
    return m.group(0)


def _ph(html: str, box: str) -> Tag:
    ph = BeautifulSoup(html, "lxml").select_one(f"{box} .ph")
    assert ph is not None, box
    return ph


def _children(el: Tag) -> list[tuple[str, list[str] | None]]:
    return [(c.name, c.get("class")) for c in el.find_all(recursive=False)]


def _rule(sel: str) -> str:
    assert sel in B.CSS, sel
    return B.CSS.split(sel, 1)[1].split("}", 1)[0]


# --- 絵は丸 2 つ（種別で変えない）-------------------------------------------------------------------------------
@pytest.mark.parametrize("species", ["dog", "cat", "other", None])
def test_placeholder_is_two_dots_whatever_the_species(tmp_path: Path, species: str | None):
    out = _build(tmp_path, [_a("nophoto00001", species=species, image_url=None)])
    for html, box in ((_animal(out, "nophoto00001"), ".detail-media"), (_card(out, "nophoto00001"), ".thumb")):
        ph = _ph(html, box)
        assert ph["class"] == ["ph"], box                                   # ph-dog・ph-cat は付けない
        assert _children(ph) == [("div", ["ph-dots"]), ("span", None)], box  # 丸 → 文 の順
        dots = ph.select_one(".ph-dots")
        assert dots is not None and _children(dots) == [("i", None), ("i", None)], box
        assert dots.get("aria-hidden") == "true" and dots.get_text() == "", box   # 飾りなので読み上げない
        assert "ph-dog" not in html and "ph-cat" not in html, box


def test_placeholder_still_reads_as_one_image_with_the_same_words(tmp_path: Path):
    out = _build(tmp_path, [_a("nophoto00001", image_url=None)])
    big, small = _ph(_animal(out, "nophoto00001"), ".detail-media"), _ph(_card(out, "nophoto00001"), ".thumb")
    for ph in (big, small):
        assert ph.get("role") == "img" and ph.get("aria-label") == "写真は自治体のページでご確認ください"
    assert big.select_one("span").get_text() == "写真は自治体のページでご確認ください"
    assert small.select_one("span").decode_contents() == "写真は自治体の<br/>ページでご確認<br/>ください"


def test_withheld_photo_keeps_the_button_under_the_dots_and_the_words(tmp_path: Path):
    out = _build(tmp_path, [_a("withheld0001", source="pref_saga-pending")], PENDING)
    ph = _ph(_animal(out, "withheld0001"), ".detail-media")
    assert _children(ph) == [("div", ["ph-dots"]), ("span", None), ("a", ["ph-btn"])]
    assert ph.get("role") is None                                           # 中にリンクがあるので role="img" にしない
    assert ph.select_one(".ph-dots").get("aria-hidden") == "true"
    assert ph.select_one("span").get_text() == "写真は自治体のページでご確認ください"


def test_fallback_for_a_photo_that_fails_to_load_has_the_dots_too(tmp_path: Path):
    out = _build(tmp_path, [_a("photo0000001")])
    for html, box in ((_animal(out, "photo0000001"), ".detail-media"), (_card(out, "photo0000001"), ".thumb")):
        frame = BeautifulSoup(html, "lxml").select_one(box)
        img = frame.select_one("img") if frame is not None else None
        assert img is not None and "classList.add('noimg')" in str(img.get("onerror") or ""), box
        assert frame.select_one("img + .ph > .ph-dots") is not None, box   # 読み込めなかったときに出す枠（onerror）


# --- CSS ----------------------------------------------------------------------------------------------------------
def test_css_draws_the_dots_in_the_two_logo_colours():
    assert "--coral:#E8826E" in B.CSS and "--teal:#6FAEBB" in B.CSS
    dot = _rule(".ph-dots i{")
    for decl in ("width:14px", "height:14px", "border-radius:50%", "opacity:.65"):
        assert decl in dot, decl
    first, last = _rule(".ph-dots i:first-child{"), _rule(".ph-dots i:last-child{")
    assert "background:var(--coral)" in first and "margin-right:-4px" in first   # 左がコーラル。4px 重ねる
    assert "background:var(--teal)" in last
    assert "margin-bottom:4px" in _rule(".ph-dots{")                              # 丸のすぐ下に文


def test_css_centres_the_dots_and_the_words_in_the_frame():
    ph = _rule("\n.ph{")
    for decl in ("position:absolute", "inset:0",   # 写真の枠（.thumb・.detail-media）いっぱいに重ねる
                 "display:flex", "flex-direction:column", "align-items:center", "justify-content:center"):
        assert decl in ph, decl
    assert "background:linear-gradient(160deg,#e8edf2,#d3dbe3)" in ph and "color:#5b6775" in ph   # 枠と文字の色は変えない


def test_css_shows_the_frame_only_without_a_photo_or_when_it_failed_to_load():
    # 写真があるあいだは隠し、読み込めなかったとき（onerror が .noimg を付ける）だけ出す（#137 reviewer F-2）
    assert ".thumb img+.ph,.detail-media img+.ph{display:none}" in B.CSS
    assert ".thumb.noimg .ph,.detail-media.noimg .ph{display:flex}" in B.CSS


def test_css_no_longer_has_the_silhouettes_or_the_paw(tmp_path: Path):
    css = (_build(tmp_path, [_a("nophoto00001", image_url=None)]) / "style.css").read_text(encoding="utf-8")
    assert css == B.CSS.strip() + "\n" and ".ph-dots i{" in css
    for gone in (".ph::before", ".ph::after", ".ph-dog", ".ph-cat", "data:image/svg+xml", "--ph:", "var(--ph)"):
        assert gone not in css, gone
    assert not hasattr(B, "_PH_SVG")
    # 絵の大きさを枠の幅に合わせるための指定（cqw と、その基準になる container-type）も要らなくなった
    assert "cqw" not in css and "container-type" not in css
