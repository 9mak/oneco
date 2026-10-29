"""T629（A8 の提携条件・ステマ規制）: 広告を載せるページは、広告であることをファーストビューに表示する。

広告（「迎える準備」枠）が出る里親募集の子のページだけ、パンくずのすぐ下（写真より上）に
「PR このページはアフィリエイト広告を利用しています」を出す。広告が無いページ（広告未設定・保護中・迷子・探してます）には出さない。
A8.net の方針（2023-10 施行の景品表示法の指定告示）: 「ファーストビュー等、一般消費者が認識できる位置にわかりやすく表示」。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}
AFF = [{"title": "ケージ", "url": "https://example.com/cage", "note": ""}]
PR_TEXT = "このページはアフィリエイト広告を利用しています"


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _data() -> dict[str, Any]:
    a = json.loads((FIX / "animals_tokushima.json").read_text(encoding="utf-8"))
    b = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
    data = {"date": "2026-09-28", "animals": a["animals"] + b["animals"], "sources": a["sources"] + b["sources"]}
    base = next(x for x in data["animals"] if x["kind"] == "adoption")
    for kind in ("stray", "lost"):
        x = dict(base)
        x.update({"id": f"{kind}00000001", "kind": kind})
        data["animals"].append(x)
    return data


def _pages(out: Path, data: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {a["id"]: (a["kind"], (out / "animals" / a["id"] / "index.html").read_text(encoding="utf-8"))
            for a in data["animals"]}


def test_no_pr_notice_anywhere_while_no_affiliate_is_configured(tmp_path: Path):
    data = _data()
    out = tmp_path / "d"
    _load_build().build_site(data, CONFIG, out)
    for aid, (_, h) in _pages(out, data).items():
        assert PR_TEXT not in h, aid
    assert PR_TEXT not in (out / "index.html").read_text(encoding="utf-8")


def test_pr_notice_only_on_pages_that_show_the_affiliate_box(tmp_path: Path):
    data = _data()
    out = tmp_path / "d"
    _load_build().build_site(data, {**CONFIG, "affiliate": AFF}, out)
    pages = _pages(out, data)
    assert {k for k, _ in pages.values()} == {"adoption", "sheltered", "stray", "lost"}
    for aid, (kind, h) in pages.items():
        assert (PR_TEXT in h) is (kind == "adoption"), (aid, kind)
        assert (PR_TEXT in h) is ("迎える準備" in h), aid


def test_pr_notice_is_in_the_first_view_above_the_photo_and_the_box(tmp_path: Path):
    data = _data()
    out = tmp_path / "d"
    _load_build().build_site(data, {**CONFIG, "affiliate": AFF}, out)
    aid = next(a["id"] for a in data["animals"] if a["kind"] == "adoption")
    h = (out / "animals" / aid / "index.html").read_text(encoding="utf-8")
    i = h.index(PR_TEXT)
    assert i < h.index('<article class="detail"')     # 写真（article の先頭）より上
    assert i < h.index("迎える準備")
    assert "PR" in h[max(0, i - 80):i]                # 「PR」の文字を添える（広告と分かる表現）
