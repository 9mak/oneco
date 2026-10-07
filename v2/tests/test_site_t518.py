"""T518 サイト: ① 種別なし（species: null）の子の出し方、② 区分「保護中」の説明（ネットワークなし）。

① 2026-10-05 おまえさん判断「犬猫が判断できなければフィルターやデータに格納する必要はない」:
   種別なしの子は種別のバッジを出さず、犬・猫の絞り込みに入れず「すべて」でだけ出す。見出し・説明文は「保護中の子」のように
   種別の語を使わない。「その他」（犬猫以外と分かっている子）とは区別する。data.json の species は null のまま
② 保護中には市民が保護している子もいる（千葉市 -5・越谷市 個人保護）ので「自治体や市民に保護されている子」
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
    spec = importlib.util.spec_from_file_location("oneco_site_build_t518", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _data() -> dict[str, Any]:
    """徳島 20 頭（犬）・佐賀 2 頭（犬）に、佐賀の種別なし 1 頭と その他 1 頭を足す。"""
    a = json.loads((FIX / "animals_tokushima.json").read_text(encoding="utf-8"))
    b = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
    data = {"date": "2026-10-05", "animals": a["animals"] + b["animals"], "sources": a["sources"] + b["sources"]}
    base = b["animals"][0]
    data["animals"].append({**base, "id": "nosp00000001", "species": None, "kind": "sheltered", "name": None})
    data["animals"].append({**base, "id": "other0000001", "species": "other", "kind": "sheltered", "name": None})
    return data


def _build(tmp_path: Path) -> Path:
    data_path = tmp_path / "latest.json"
    data_path.write_text(json.dumps(_data(), ensure_ascii=False, indent=1), encoding="utf-8")
    out = tmp_path / "dist"
    _mod().build(data_path, out, CONFIG)
    return out


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _main(h: str) -> str:
    return h.split("<main", 1)[1].split("</main>", 1)[0]


# --- ① 種別なし ------------------------------------------------------------------------
def test_animal_page_without_species_has_no_species_badge_or_word(tmp_path: Path):
    out = _build(tmp_path)
    h = _read(out / "animals" / "nosp00000001" / "index.html")
    body = _main(h)
    assert 'class="badge sp-' not in body                       # 種別のバッジを出さない
    assert '<span class="badge kd-sheltered">保護中</span>' in body
    assert "<h1>保護中の子</h1>" in body                         # 見出しは種別の語を使わない
    assert "その他" not in body and "None" not in h
    assert re.search(r'<title>保護中の子（[^<]+）｜oneco</title>', h)
    assert re.search(r'property="og:title" content="保護中の子（', h)
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert "公開している保護中の子。" in desc and "その他" not in desc
    assert re.search(r'property="og:description" content="[^"]*保護中の子。', h)
    # 写真の alt も同じ見出し
    assert 'alt="保護中の子（' in body


def test_other_species_is_still_labelled_other(tmp_path: Path):
    out = _build(tmp_path)
    body = _main(_read(out / "animals" / "other0000001" / "index.html"))
    assert '<span class="badge sp-other">その他</span>' in body
    assert "<h1>保護中のその他</h1>" in body


def test_pref_page_card_and_counts(tmp_path: Path):
    out = _build(tmp_path)
    h = _read(out / "pref" / "佐賀県" / "index.html")
    assert 'href="/animals/nosp00000001/" data-species="none"' in h       # 犬・猫の絞り込みに当たらない
    assert 'href="/animals/other0000001/" data-species="other"' in h
    assert '<b id="count">4</b>' in h                                     # すべて = 犬 2 + その他 1 + 種別なし 1
    stats = re.search(r'<p class="stats">([^<]*)</p>', h).group(1)
    assert "犬 2 頭" in stats and "猫 0 頭" in stats and "その他 1 頭" in stats and "犬猫の区別なし 1 頭" in stats
    # 絞り込みの選択肢は すべて・犬・猫 のまま（種別なしの選択肢は作らない）
    assert 'data-filter="species" data-value="none"' not in h
    # クライアント側 JS: 種別が空の子を other 扱いにしない。バッジは種別の名前がある子だけ、見出しは「…の子」
    assert "a.species||'other'" not in h and "a.species||'none'" in h
    assert "(SP[sp]||'子')" in h
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert "保護犬 2 頭・保護猫 0 頭" in desc and "ほか 2 頭" in desc


def test_index_counts_include_unknown_only_in_total(tmp_path: Path):
    out = _build(tmp_path)
    h = _read(out / "index.html")
    li = re.search(r'<li data-pref="佐賀県"[^>]*>', h).group(0)
    assert 'data-dog="2"' in li and 'data-cat="0"' in li and 'data-other="1"' in li and 'data-total="4"' in li
    stats = re.search(r'<p class="stats">(.*?)</p>', h).group(1)
    assert "犬 <b>22</b> 頭" in stats and "その他 <b>1</b> 頭" in stats and "犬猫の区別なし <b>1</b> 頭" in stats


def test_data_json_keeps_species_null(tmp_path: Path):
    out = _build(tmp_path)
    d = json.loads(_read(out / "data.json"))
    got = {a["id"]: a["species"] for a in d["animals"] if a["id"] in ("nosp00000001", "other0000001")}
    assert got == {"nosp00000001": None, "other0000001": "other"}


def test_about_explains_animals_without_species(tmp_path: Path):
    out = _build(tmp_path)
    h = _read(out / "about" / "index.html")
    assert "犬か猫か分からない子は、種別を付けずに載せています" in h


# --- ② 保護中の説明 --------------------------------------------------------------------
def test_sheltered_help_includes_citizens(tmp_path: Path):
    mod = _mod()
    assert mod.KIND_HELP["sheltered"] == "自治体や市民に保護されている子"
    out = _build(tmp_path)
    assert "保護中（自治体や市民に保護されている子）" in _read(out / "about" / "index.html")
    assert "保護中＝自治体や市民に保護されている子" in _read(out / "index.html")
    assert '<p class="kind-help">自治体や市民に保護されている子</p>' in _read(out / "animals" / "nosp00000001" / "index.html")
