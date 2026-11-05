"""W006 T631: empty_text_all（列挙した 0 頭の文が全部出たときだけ 0 頭）と、その指定の schema 検査。"""

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import Source

SRC = Source(
    slug="x-1",
    name="x",
    municipality="x市",
    prefecture="x県",
    url="https://www.city.example.jp/a/",
    kind="stray",
    species="mixed",
)
DOG = "現在、迷子犬の保護情報はありません"
CAT = "現在、迷子猫の保護情報はありません"


def _doc(body: str) -> Doc:
    html = f"<html><body>{body}</body></html>"
    return Doc(url=SRC.url, html=html, soup=BeautifulSoup(html, "lxml"))


def _recipe(**kw) -> Recipe:
    return Recipe.from_dict({"rows": "li.animal", **kw})


def test_all_phrases_present_confirms_zero_with_own_evidence():
    res = build(
        SRC,
        _recipe(empty_text_all=[DOG, CAT]),
        [_doc(f"<h2>犬</h2><p>{DOG}</p><h2>猫</h2><p>{CAT}</p>")],
    )
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_all"


def test_only_one_section_phrase_is_not_zero():
    # 犬の節だけ 0 頭の文が出ていて、猫の節は読めていない（行が取れなかった）日。0 頭にしない
    res = build(SRC, _recipe(empty_text_all=[DOG, CAT]), [_doc(f"<p>{DOG}</p><div>猫の節</div>")])
    assert res.animals == [] and not res.empty_confirmed


def test_no_phrase_is_not_zero():
    res = build(SRC, _recipe(empty_text_all=[DOG, CAT]), [_doc("<p>別の文</p>")])
    assert not res.empty_confirmed


def test_phrases_may_come_from_different_visited_documents():
    d1, d2 = _doc(f"<p>{DOG}</p>"), _doc(f"<p>{CAT}</p>")
    d2.url = "https://www.city.example.jp/b/"
    res = build(SRC, _recipe(empty_text_all=[DOG, CAT]), [d1], [d1, d2])
    assert res.empty_confirmed and res.empty_evidence == "empty_text_all"


def test_img_alt_counts_for_all_phrases():
    res = build(
        SRC,
        _recipe(empty_text_all=[DOG, CAT]),
        [_doc(f'<p>{DOG}</p><img alt="{CAT}" src="/n.png">')],
    )
    assert res.empty_confirmed


def test_existing_empty_text_unchanged_any_phrase_is_enough():
    res = build(SRC, _recipe(empty_text=[DOG, CAT]), [_doc(f"<p>{DOG}</p>")])
    assert res.empty_confirmed and res.empty_evidence == "empty_text"


def test_empty_text_all_ignored_when_animals_exist():
    body = f'<ul><li class="animal"><img src="/a.jpg"></li></ul><p>{DOG}</p><p>{CAT}</p>'
    res = build(SRC, _recipe(empty_text_all=[DOG, CAT]), [_doc(body)])
    assert len(res.animals) == 1 and not res.empty_confirmed


# --- schema -----------------------------------------------------------------
def _errs(raw):
    return validate_recipe_dict({"rows": "tr", **raw}, "https://www.city.example.jp/a/")


def test_schema_accepts_empty_text_all_list():
    assert _errs({"empty_text_all": [DOG, CAT]}) == []


def test_schema_rejects_non_list_and_non_string_items():
    assert any("empty_text_all" in e for e in _errs({"empty_text_all": 1}))
    assert any("empty_text_all" in e for e in _errs({"empty_text_all": [DOG, 2]}))


def test_schema_rejects_single_phrase_and_empty_string():
    # 1 つなら empty_text で足りる（全部一致の意味が無い）。空文字はどの文書にも含まれるので 0 頭の根拠にならない
    assert any("2 個以上" in e for e in _errs({"empty_text_all": [DOG]}))
    assert any("空" in e for e in _errs({"empty_text_all": [DOG, ""]}))


def test_schema_still_rejects_unknown_keys():
    assert any("未知のキー" in e for e in _errs({"empty_text_every": [DOG, CAT]}))
