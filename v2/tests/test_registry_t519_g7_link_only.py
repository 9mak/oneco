"""T519 グループ7: 読めないので link_only にした宮崎県（みやざきドッグ愛ランド）・鹿児島県のページ。

- 宮崎県: robots.txt が /modules/addon_module/（一覧と個体ページ）を Disallow している。収集器は robots を守るので読まない
- 鹿児島県: 一覧は anti-forgery トークン付き form の POST でしか出ない。収集器は POST を持たない
どちらも「リンクだけ載せる」台帳のエントリになっていること（誤って recipe モードに戻すと毎日失敗するので固定する）。
"""

from pathlib import Path

from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

MIYAZAKI = {
    "pref_miyazaki-1": ("sheltered", "dog", "id1=1&id2=3"),
    "pref_miyazaki-2": ("adoption", "dog", "id1=1&id2=1"),
    "pref_miyazaki-3": ("lost", "dog", "id1=1&id2=2"),
    "pref_miyazaki-4": ("sheltered", "cat", "id1=2&id2=3"),
    "pref_miyazaki-5": ("adoption", "cat", "id1=2&id2=1"),
    "pref_miyazaki-6": ("lost", "cat", "id1=2&id2=2"),
}


def test_miyazaki_six_lists_are_link_only_with_matching_kind_and_species():
    for slug, (kind, species, query) in MIYAZAKI.items():
        s = SOURCES[slug]
        assert (s.mode, s.kind, s.species, s.enabled) == ("link_only", kind, species, True), slug
        assert s.url.startswith("https://dog.pref.miyazaki.lg.jp/modules/addon_module/?a=doglove&p=search_list&") and s.url.endswith(query), slug
        assert s.phone == "0985-84-2600" and "宮崎市清武町木原4543番地8" in (s.address or ""), slug
        assert s.recipe is None, slug   # 読まないのでレシピは無い


def test_kagoshima_pref_indexes_are_link_only():
    lost, jouto = SOURCES["pref_kagoshima-1"], SOURCES["pref_kagoshima-2"]
    assert (lost.mode, lost.kind, lost.url) == ("link_only", "stray", "http://dogcat.pref.kagoshima.jp/Search/Lost_index")
    assert (jouto.mode, jouto.kind, jouto.url) == ("link_only", "adoption", "http://dogcat.pref.kagoshima.jp/Search/Jouto_index")
    assert lost.recipe is None and jouto.recipe is None
