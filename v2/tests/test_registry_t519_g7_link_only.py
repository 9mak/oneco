"""T519 グループ7: 読めないので link_only にした宮崎県（みやざきドッグ愛ランド）・鹿児島県のページ。

- 宮崎県: robots.txt が /modules/addon_module/（一覧と個体ページ）を Disallow している。収集器は robots を守るので読まない
- 鹿児島県: 一覧は anti-forgery トークン付き form の POST でしか出ない。収集器は POST を持たなかった（2026-11-07 に submit_form を足して読むようになった。下のテストが現在の状態）
どちらも「リンクだけ載せる」台帳のエントリになっていること（誤って recipe モードに戻すと毎日失敗するので固定する）。

2026-11-18: みやざきドッグ愛ランドは「サイトリニューアル準備につき、仮サイトにて情報をお届けしております」の 1 ページだけになり、
一覧の 6 URL（/modules/addon_module/?…）は HTTP 404（discover --pages の試運転で検出）。リンク先を、仮サイトを案内しているトップページにした。
電話は一覧ページのフッターにあったもので、今の掲載元ページ（トップ）には無いので載せない（T628「掲載元ページで確認できたものだけ」）。
"""

from pathlib import Path

import yaml
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
_RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))
NOTES = {e["slug"]: str(e.get("note") or "") for e in (_RAW["sources"] if isinstance(_RAW, dict) else _RAW)}

MIYAZAKI_TOP = "https://dog.pref.miyazaki.lg.jp/"
MIYAZAKI = {
    "pref_miyazaki-1": ("sheltered", "dog"),
    "pref_miyazaki-2": ("adoption", "dog"),
    "pref_miyazaki-3": ("lost", "dog"),
    "pref_miyazaki-4": ("sheltered", "cat"),
    "pref_miyazaki-5": ("adoption", "cat"),
    "pref_miyazaki-6": ("lost", "cat"),
}


def test_miyazaki_six_lists_are_link_only_with_matching_kind_and_species():
    for slug, (kind, species) in MIYAZAKI.items():
        s = SOURCES[slug]
        assert (s.mode, s.kind, s.species, s.enabled) == ("link_only", kind, species, True), slug
        # 一覧の URL は 404。仮サイトを案内しているトップページへ送る（リニューアルが済んだら一覧の URL に戻す）
        assert s.url == MIYAZAKI_TOP, slug
        # 電話も所在地も、今の掲載元ページ（トップ）に無いので載せない（2026-10-18 T628「推測で足さない」）
        assert s.phone is None and s.address is None, slug
        assert s.recipe is None, slug   # 読まないのでレシピは無い
        assert "2026-11-18" in NOTES[slug] and "HTTP 404" in NOTES[slug], slug   # いつ・なぜ変えたかを note に残す


def test_kagoshima_pref_indexes_are_read_since_20261107():
    # 2026-11-07 W006: POST の form を submit_form で通して読むようにしたのでリンクのみではなくなった（test_w006_pref_kagoshima_20261107.py）
    lost, jouto = SOURCES["pref_kagoshima-1"], SOURCES["pref_kagoshima-2"]
    assert (lost.mode, lost.kind, lost.url) == ("recipe", "stray", "http://dogcat.pref.kagoshima.jp/Search/Lost_index")
    assert (jouto.mode, jouto.kind, jouto.url) == ("recipe", "adoption", "http://dogcat.pref.kagoshima.jp/Search/Jouto_index")
    assert lost.recipe == "recipes/pref_kagoshima-1.yaml" and jouto.recipe == "recipes/pref_kagoshima-2.yaml"
