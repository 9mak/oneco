"""T519 グループ7: 読めないので link_only にした宮崎県（みやざきドッグ愛ランド）・鹿児島県のページ。

- 宮崎県: robots.txt が /modules/addon_module/（一覧と個体ページ）を Disallow している。収集器は robots を守るので読まない
- 鹿児島県: 一覧は anti-forgery トークン付き form の POST でしか出ない。収集器は POST を持たなかった（2026-11-07 に submit_form を足して読むようになった。下のテストが現在の状態）
どちらも「リンクだけ載せる」台帳のエントリになっていること（誤って recipe モードに戻すと毎日失敗するので固定する）。

2026-11-18: みやざきドッグ愛ランドは「サイトリニューアル準備につき、仮サイトにて情報をお届けしております」の 1 ページだけになり、
一覧の 6 URL（/modules/addon_module/?…）は HTTP 404（discover --pages の試運転で検出）。リンク先を、仮サイトを案内しているトップページにした。
電話は一覧ページのフッターにあったもので、トップページの HTML 本体には無いので載せない（T628「掲載元ページで確認できたものだけ」）。
2026-11-19（#134 reviewer）: トップに埋め込まれた仮サイト（別ホストの wixsite.com）には同じ番号が載っている。ops/verify_registry.py は
同じホストのページしか確かめないので載せないままにし、note の理由を実態どおりに直した（リンクのみの掲載元の電話はサイトに出ない）。
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
        # 電話も所在地も、トップページの HTML 本体に無いので載せない（2026-10-18 T628「推測で足さない」。仮サイトの中にはある）
        assert s.phone is None and s.address is None, slug
        assert s.recipe is None, slug   # 読まないのでレシピは無い
        assert "2026-11-18" in NOTES[slug] and "HTTP 404" in NOTES[slug], slug   # いつ・なぜ変えたかを note に残す
        assert "仮サイト" in NOTES[slug] and "今の掲載元ページ（トップ）には無い" not in NOTES[slug], slug   # 表示では仮サイトに番号がある（事実と違う理由を書かない）


def test_kagoshima_pref_indexes_are_read_since_20261107():
    # 2026-11-07 W006: POST の form を submit_form で通して読むようにしたのでリンクのみではなくなった（test_w006_pref_kagoshima_20261107.py）
    lost, jouto = SOURCES["pref_kagoshima-1"], SOURCES["pref_kagoshima-2"]
    assert (lost.mode, lost.kind, lost.url) == ("recipe", "stray", "http://dogcat.pref.kagoshima.jp/Search/Lost_index")
    assert (jouto.mode, jouto.kind, jouto.url) == ("recipe", "adoption", "http://dogcat.pref.kagoshima.jp/Search/Jouto_index")
    assert lost.recipe == "recipes/pref_kagoshima-1.yaml" and jouto.recipe == "recipes/pref_kagoshima-2.yaml"
