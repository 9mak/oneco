"""サイトの文言と絞り込み（2026-11-09。agy の指摘を実ページで確かめて直した分。ネットワークなし）。

- 名前の無い「探してます」の子の見出しが「探してますの犬」にならない。犬猫以外は「その他」でなく「動物」と呼ぶ
- 問い合わせ先（operator）の住所を、子のいる場所と思って訪ねないように注意書きを出す
- 画面の ID はサイトの中だけの番号で、自治体には通じないと書く
- 都道府県ページの絞り込みは data.json を読まず、ページにあるカードの表示を切り替える（並び順が崩れない）
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_copy", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _build(tmp_path: Path) -> Path:
    b = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
    base: dict[str, Any] = b["animals"][0]
    extra = [
        {**base, "id": "lostdog00001", "kind": "lost", "species": "dog", "name": None},
        {**base, "id": "lostother001", "kind": "lost", "species": "other", "name": None},
        {**base, "id": "lostnone0001", "kind": "lost", "species": None, "name": None},
        {**base, "id": "shelother001", "kind": "sheltered", "species": "other", "name": None},
        {**base, "id": "operator0001", "kind": "adoption", "species": "cat", "name": None, "contact_scope": "operator",
         "phone": "03-0000-0000", "address": "東京都どこか"},
        {**base, "id": "facility0001", "kind": "adoption", "species": "cat", "name": None, "contact_scope": "facility",
         "phone": "03-0000-0000", "address": "東京都どこか"},
        {**base, "id": "nophone00001", "kind": "adoption", "species": "cat", "name": None, "phone": None},
    ]
    data = {"date": "2026-11-09", "animals": b["animals"] + extra, "sources": b["sources"]}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    _mod().build(p, out, CONFIG)
    return out


def _page(out: Path, id_: str) -> str:
    return (out / "animals" / id_ / "index.html").read_text(encoding="utf-8")


def test_nameless_lost_animal_reads_naturally(tmp_path: Path):
    out = _build(tmp_path)
    for id_, word in (("lostdog00001", "探している犬"), ("lostother001", "探している動物"), ("lostnone0001", "探している子")):
        h = _page(out, id_)
        assert f"<h1>{word}</h1>" in h
        assert re.search(rf"<title>{word}（", h)
        assert f"飼い主さんが{word}。" in re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
        assert "探してますの" not in h
        assert ">探してます<" in h      # 区分のバッジの呼び方は変えない


def test_other_species_is_called_animal_in_sentences(tmp_path: Path):
    h = _page(_build(tmp_path), "shelother001")
    assert "<h1>保護中の動物</h1>" in h and "保護中のその他" not in h


def test_operator_address_warns_against_visiting_only_for_operator(tmp_path: Path):
    out = _build(tmp_path)
    note = "子がいる場所とは限りません"
    assert note in _page(out, "operator0001")
    assert note not in _page(out, "facility0001")


def test_page_says_id_is_internal_and_what_to_tell_the_municipality(tmp_path: Path):
    h = _page(_build(tmp_path), "facility0001")
    assert "このサイトの中だけの番号" in h and "管理番号" in h
    assert "<code>facility0001</code>" in h


def test_missing_phone_row_is_labelled_phone_under_contact_heading(tmp_path: Path):
    h = _page(_build(tmp_path), "nophone00001")
    assert "<dt>電話</dt><dd>電話番号は自治体のページでご確認ください。</dd>" in h
    assert "<dt>連絡先</dt>" not in h


def test_about_wording(tmp_path: Path):
    about = (_build(tmp_path) / "about" / "index.html").read_text(encoding="utf-8")
    assert "自動に" not in about and "自動で読み取っている" in about
    assert "本日は確認できませんでした" not in about and "本日は読めませんでした" in about


def test_pref_filter_does_not_fetch_data_json_and_toggles_rendered_cards(tmp_path: Path):
    out = _build(tmp_path)
    pref = next(p for p in out.rglob("index.html") if "の保護犬・保護猫</h1>" in p.read_text(encoding="utf-8"))
    h = pref.read_text(encoding="utf-8")
    assert "/data.json" not in h and "fetch(" not in h
    assert "c.hidden=!s" in h
    # ページのカードは 里親募集→保護中→迷子→探してます の順
    kinds = re.findall(r'class="card"[^>]*data-kind="(\w+)"', h)
    order = {"adoption": 0, "sheltered": 1, "stray": 2, "lost": 3}
    assert [order[k] for k in kinds] == sorted(order[k] for k in kinds) and "lost" in kinds


def test_tokyo_municipality_is_not_the_page_name():
    src = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    for s in src:
        if s["slug"].startswith("shuyojoho_tokyo"):
            assert s["municipality"] == "東京都"
            assert "収容動物情報" in s["name"]    # 掲載元の名前（固有名）はそのまま
