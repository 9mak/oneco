"""W006 T630: リンクのみの掲載元の電話・所在地を、公開する data.json に載せない（2026-11-21）。

リンクのみ（台帳 mode: link_only、または収集の status: link_only）は、自治体から文章や画像の転載を断られた
（久留米市・福岡市・北海道）か、個人の掲載などで、サイトのページには名前とリンクしか出していない。
一方で公開の data.json（/data.json）には、台帳から写した電話・所在地がそのまま入っていた。
ページの表示は変えず、data.json からだけ外す（電話・所在地と、その根拠の URL）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}
KEYS = ("phone", "address", "verified_phone_url", "verified_address_url")


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build_linkonly", ROOT / "site" / "build.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _animal(aid: str) -> dict[str, Any]:
    return {"id": aid, "source": "s1", "municipality": "テスト市", "prefecture": "徳島県", "kind": "adoption", "species": "dog",
            "source_url": "https://example.lg.jp/a", "phone": "088-000-0000", "address": "徳島県テスト市1-1", "image_url": None,
            "name": None, "sex": None, "age": None, "breed": None, "color": None, "size": None, "management_no": aid,
            "shelter_date": None, "note": None, "location": None}


def _source(slug: str, mode: str, status: str, phone: str, address: str) -> dict[str, Any]:
    return {"slug": slug, "name": f"テスト（{slug}）", "municipality": "テスト市", "prefecture": "徳島県",
            "url": f"https://example.lg.jp/{slug}", "mode": mode, "status": status, "count": 1 if status == "ok" else 0,
            "phone": phone, "address": address,
            "verified_phone_url": f"https://example.lg.jp/{slug}", "verified_address_url": f"https://example.lg.jp/{slug}",
            "photo": "ok"}  # 収集は台帳の photo を必ず書く（書いていなければ pending。2026-11-22 方針 1・2）


def _data() -> dict[str, Any]:
    return {"date": "2026-11-21", "animals": [_animal("dog000000001")],
            "sources": [_source("s1", "recipe", "ok", "088-000-0000", "徳島県テスト市1-1"),
                        _source("lo1", "link_only", "link_only", "099-111-1111", "北海道テスト町2-2"),
                        _source("lo2", "recipe", "link_only", "099-222-2222", "北海道テスト町3-3")]}


def _public_sources(out: Path) -> dict[str, dict[str, Any]]:
    d = json.loads((out / "data.json").read_text(encoding="utf-8"))
    return {s["slug"]: s for s in d["sources"]}


def test_link_only_sources_have_no_contacts_in_public_data_json(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    _load_build().build_site(_data(), CONFIG, out)
    src = _public_sources(out)
    for slug in ("lo1", "lo2"):
        for k in KEYS:
            assert src[slug].get(k) is None, (slug, k)
        assert src[slug]["url"] == f"https://example.lg.jp/{slug}"  # リンクは残す
        assert src[slug]["name"] == f"テスト（{slug}）"
    # 読めている掲載元はそのまま
    assert src["s1"]["phone"] == "088-000-0000" and src["s1"]["address"] == "徳島県テスト市1-1"


def test_same_when_built_from_the_data_file(tmp_path: Path) -> None:
    # 本番は data_path（latest.json）から data.json をコピーしていた。その経路でも外れること
    f = tmp_path / "latest.json"
    f.write_text(json.dumps(_data(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    _load_build().build_site(json.loads(f.read_text(encoding="utf-8")), CONFIG, out, data_path=f)
    src = _public_sources(out)
    assert src["lo1"]["phone"] is None and src["lo1"]["address"] is None
    assert src["s1"]["phone"] == "088-000-0000"
    # 元のファイルは変えない
    assert json.loads(f.read_text(encoding="utf-8"))["sources"][1]["phone"] == "099-111-1111"


def test_pages_do_not_show_link_only_contacts(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    _load_build().build_site(_data(), CONFIG, out)
    html = "".join(p.read_text(encoding="utf-8") for p in out.rglob("*.html"))
    for v in ("099-111-1111", "北海道テスト町2-2", "099-222-2222", "北海道テスト町3-3"):
        assert v not in html, v


def test_data_file_is_copied_as_is_when_there_is_nothing_to_strip(tmp_path: Path) -> None:
    d = _data()
    d["sources"] = d["sources"][:1]
    f = tmp_path / "latest.json"
    raw = json.dumps(d, ensure_ascii=False)
    f.write_text(raw, encoding="utf-8")
    out = tmp_path / "dist"
    _load_build().build_site(json.loads(raw), CONFIG, out, data_path=f)
    assert (out / "data.json").read_text(encoding="utf-8") == raw
