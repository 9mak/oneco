"""W006 T630: 自治体の規約が「転載は要申請」または規約が見当たらない掲載元は、許諾の返事が来るまで写真を出さない。

台帳の `photo`（ok | pending | no）を掲載元の行に引き継ぎ、サイト生成時に ok 以外の掲載元の子は
image_url を落として「写真はありません」の枠にする。data.json（ページ内 JS が読む）からも落とす。

2026-11-22（POLICY.md 方針 1・2）: 写真を出してよいのは、規約で可か自治体が可と言った掲載元だけ。
台帳に photo を書いていない掲載元は pending（確認が取れるまで出さない）として扱い、ok は根拠のある掲載元にだけ書く。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import yaml
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
BUILD_PY = ROOT / "site" / "build.py"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build_t630", BUILD_PY)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _data() -> dict[str, Any]:
    a = json.loads((FIX / "animals_tokushima.json").read_text(encoding="utf-8"))
    b = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
    return {"date": "2026-09-28", "animals": a["animals"] + b["animals"], "sources": a["sources"] + b["sources"]}


def test_registry_photo_defaults_to_pending_and_accepts_ok(tmp_path: Path):
    """方針 1・2: photo を書いていない掲載元は、確認が取れるまで写真を出さない（pending）。"""
    assert Source.__dataclass_fields__["photo"].default == "pending"
    y = tmp_path / "sources.yaml"
    y.write_text(
        "sources:\n"
        "- slug: a\n  name: A\n  municipality: A市\n  prefecture: X県\n  url: https://a.example/\n  kind: sheltered\n"
        "- slug: b\n  name: B\n  municipality: B市\n  prefecture: X県\n  url: https://b.example/\n  kind: sheltered\n  photo: ok\n",
        encoding="utf-8")
    srcs = {s.slug: s for s in load_sources(y)}
    assert srcs["a"].photo == "pending"
    assert srcs["b"].photo == "ok"


# 台帳で photo: ok にしてよい根拠（note に書く）: 自治体の可の返事、規約の判定、POLICY.md の決定（岡山市の譲渡 2 ページは方針 43）
OK_BASIS = re.compile(r"返事|規約で二次利用可|方針 ?43")


def test_real_registry_photo_ok_has_basis_in_note():
    """photo: ok の掲載元は、note に根拠（可の返事・規約の判定・方針 43）が書いてある。根拠の無い ok を作らない（11/22 新潟県 -2・-3）。"""
    raw = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    no_basis = [s["slug"] for s in raw if str(s.get("photo")) == "ok" and not OK_BASIS.search(str(s.get("note") or ""))]
    assert no_basis == []


def test_real_registry_photo_decisions_20261122():
    """11/22 に確かめた掲載元: 奈良市の譲渡（11/17 に可の返事）と神戸市（規約で二次利用可）は出す。
    新潟県 -2・-3 は規約が無断転載禁止で可の返事が無いので止める（T655 で聞く）。"""
    srcs = {s.slug: s for s in load_sources()}
    assert srcs["city_nara-2"].photo == "ok"
    assert srcs["city_kobe"].photo == "ok"
    assert srcs["pref_niigata-2"].photo == "pending"
    assert srcs["pref_niigata-3"].photo == "pending"


def test_real_registry_photo_values_are_known():
    for s in load_sources():
        assert s.photo in ("ok", "pending", "no"), s.slug


def test_site_hides_photos_of_pending_sources(tmp_path: Path):
    data = _data()
    saga = [a for a in data["animals"] if a["source"].startswith("pref_saga")]
    toku = [a for a in data["animals"] if not a["source"].startswith("pref_saga")]
    assert saga and toku and all(a.get("image_url") for a in saga[:1])
    for s in data["sources"]:
        if s["slug"].startswith("pref_saga"):
            s["photo"] = "pending"
    data_path = tmp_path / "animals.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    _load_build().build_site(data, CONFIG, out, data_path=data_path)

    h = (out / "animals" / saga[0]["id"] / "index.html").read_text(encoding="utf-8")
    main = h.split("<main")[1].split("</main>")[0]
    assert "<img" not in main
    assert 'class="ph"' in main   # 写真なしの枠が出ている（2026-11-19: 絵は種別で変えないので class は ph だけ）
    assert 'property="og:image" content="https://oneco.pages.dev/brand/oneco-avatar-512.png"' in h
    assert saga[0]["image_url"] not in h
    # 佐賀以外は今までどおり
    with_img = next(a for a in toku if a.get("image_url"))
    h2 = (out / "animals" / with_img["id"] / "index.html").read_text(encoding="utf-8")
    assert with_img["image_url"] in h2
    # 一覧と data.json からも落ちている
    index = (out / "index.html").read_text(encoding="utf-8")
    assert saga[0]["image_url"] not in index
    dj = json.loads((out / "data.json").read_text(encoding="utf-8"))
    by_id = {a["id"]: a for a in dj["animals"]}
    assert not by_id[saga[0]["id"]].get("image_url")
    assert by_id[with_img["id"]]["image_url"] == with_img["image_url"]
    # 掲載元一覧に「確認が取れるまで出していない」と出る（まだお伺いしていない自治体もあるので「返事待ち」とは書かない。11/22）
    srcs = (out / "sources" / "index.html").read_text(encoding="utf-8")
    assert "写真は自治体の確認が取れるまで出していません" in srcs
    assert "返事待ち" not in srcs


def test_build_merges_photo_from_registry(tmp_path: Path):
    """収集済みの data に photo が無くても、--registry で台帳の photo を slug ごとに合流させて写真を落とす。"""
    data = _data()
    saga = next(a for a in data["animals"] if a["source"].startswith("pref_saga") and a.get("image_url"))
    data_path = tmp_path / "animals.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    reg = tmp_path / "sources.yaml"
    reg.write_text(
        "sources:\n"
        f"- slug: {saga['source']}\n  name: S\n  municipality: 佐賀県\n  prefecture: 佐賀県\n  url: https://s.example/\n"
        "  kind: sheltered\n  photo: pending\n",
        encoding="utf-8")
    out = tmp_path / "dist"
    _load_build().build(data_path, out, CONFIG, registry=reg)
    h = (out / "animals" / saga["id"] / "index.html").read_text(encoding="utf-8")
    assert saga["image_url"] not in h
    dj = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert not next(a for a in dj["animals"] if a["id"] == saga["id"]).get("image_url")
    assert next(s for s in dj["sources"] if s["slug"] == saga["source"])["photo"] == "pending"


def test_build_treats_registry_source_without_photo_as_pending(tmp_path: Path):
    """方針 1・2: 台帳に photo を書いていない掲載元は、収集済みの data が ok と言っていても、--registry で写真を落とす。
    （11/22 までの収集は既定 ok で data に "photo": "ok" を書いているので、台帳を合わせる側でも既定を pending にする）"""
    data = _data()
    saga = next(a for a in data["animals"] if a["source"].startswith("pref_saga") and a.get("image_url"))
    for s in data["sources"]:
        s["photo"] = "ok"
    data_path = tmp_path / "animals.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    reg = tmp_path / "sources.yaml"
    reg.write_text(
        "sources:\n"
        f"- slug: {saga['source']}\n  name: S\n  municipality: 佐賀県\n  prefecture: 佐賀県\n  url: https://s.example/\n"
        "  kind: sheltered\n",
        encoding="utf-8")
    out = tmp_path / "dist"
    _load_build().build(data_path, out, CONFIG, registry=reg)
    h = (out / "animals" / saga["id"] / "index.html").read_text(encoding="utf-8")
    assert saga["image_url"] not in h
    dj = json.loads((out / "data.json").read_text(encoding="utf-8"))
    assert not next(a for a in dj["animals"] if a["id"] == saga["id"]).get("image_url")
    assert next(s for s in dj["sources"] if s["slug"] == saga["source"])["photo"] == "pending"


def test_site_data_json_is_byte_copy_when_nothing_is_pending(tmp_path: Path):
    data = _data()
    data_path = tmp_path / "animals.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    _load_build().build_site(data, CONFIG, out, data_path=data_path)
    assert (out / "data.json").read_bytes() == data_path.read_bytes()
