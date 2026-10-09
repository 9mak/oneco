"""W006 T605: 全行除外の 0 頭は、見出しの項目名一致かコンテナ存在の肯定的な証拠が無ければ ambiguous_empty にする。"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import _split_parent, build, expected_labels
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run_fixture(slug: str, fixture: str, replace: tuple[str, str] | None = None, subs: list[tuple[str, str]] | None = None):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    html = (FIX / fixture).read_text(encoding="utf-8")
    if replace:
        assert replace[0] in html
        html = html.replace(*replace)
    for old, new in subs or []:
        assert old in html
        html = html.replace(old, new)
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_fukushima_4_unchanged_headings_is_empty_with_headings_evidence():
    res = _run_fixture("pref_fukushima-4", "fix1009_fukushima-4_20261009_template.html")
    assert res.empty_confirmed and not res.ambiguous_empty and res.empty_evidence == "all_excluded+headings"


def test_fukushima_4_renamed_headings_is_ambiguous():
    res = _run_fixture("pref_fukushima-4", "fix1009_fukushima-4_20261009_template.html", subs=[
        ("管理番号", "整理ID"), ("保護日", "発見日"), ("保護場所", "発見場所"), ("種類", "犬種"), ("体格", "大きさ")])
    assert res.animals == [] and not res.empty_confirmed and res.ambiguous_empty
    assert "見出しの項目名が一致しない" in (res.ambiguous_reason or "") and "管理番号" in (res.ambiguous_reason or "")


def test_kitakyushu_1_unchanged_headings_is_empty_with_headings_evidence():
    res = _run_fixture("city_kitakyushu-1", "fix1009_kitakyushu-1_20261009_template.html")
    assert res.empty_confirmed and not res.ambiguous_empty and res.empty_evidence == "all_excluded+headings"


def test_kitakyushu_1_renamed_headings_is_ambiguous():
    # 項目名の半数以上が合わなくなる書き換え（1 つだけ変わった日は半数以上が残るので確定のまま）
    res = _run_fixture("city_kitakyushu-1", "fix1009_kitakyushu-1_20261009_template.html", ("<th", "<th data-x"), subs=[
        ("収容日", "日付"), ("毛色", "色"), ("性別", "sex"), ("体格", "大きさ"), ("備考", "メモ")])
    assert not res.empty_confirmed and res.ambiguous_empty


def test_expected_labels_collects_label_candidates_header_and_join():
    r = Recipe.from_dict({"fields": {
        "a": {"label": "収容日"}, "b": {"label": ["種類", "犬種"]}, "c": {"header": "毛 色"},
        "d": {"join": [{"label": "備考"}, "td.x"]}, "e": "td:nth-of-type(3)",
    }})
    assert expected_labels(r) == {"収容日", "種類", "犬種", "毛色", "備考"}


def test_split_parent():
    assert _split_parent("table tr") == "table"
    assert _split_parent("ul.list > li") == "ul.list"
    assert _split_parent("table:has(caption:-soup-contains('収容 表')) tr:has(td)") == "table:has(caption:-soup-contains('収容 表'))"
    assert _split_parent("body") is None
    assert _split_parent("a, b c") is None


def _build(recipe: dict, html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml"))
    return build(src, Recipe.from_dict(recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


_EXCLUDE = {"field_lacks": {"note": ["探しています"]}}


def test_container_evidence_when_no_table_headings():
    html = "<ul class='list'><li>探しています 迷子</li></ul>"
    r = {"rows": "ul.list > li", "row_filter": _EXCLUDE, "fields": {"note": {"selector": "."}}}
    res = _build(r, html)
    assert res.empty_confirmed and res.empty_evidence == "all_excluded+container"


def test_missing_container_is_ambiguous():
    html = "<ol class='other'><li>探しています 迷子</li></ol>"
    r = {"rows": "ol > li", "row_filter": _EXCLUDE, "fields": {"note": {"selector": "."}}}
    # 親セレクタは "ol"。文書にあるので確定する一方、無ければ ambiguous
    assert _build(r, html).empty_confirmed
    res = _build({**r, "rows": "ul.gone > li"}, "<div>探しています</div>")
    assert res.rows == 0 and not res.ambiguous_empty   # 行が 0 なら従来どおり（全行除外ではない）
    html2 = "<div><p class='row'>探しています</p></div>"
    res = _build({"rows": "p.row", "row_filter": _EXCLUDE, "fields": {"note": {"selector": "."}}}, html2)
    assert not res.empty_confirmed and res.ambiguous_empty
    assert "empty_container 未指定" in (res.ambiguous_reason or "")


def test_empty_container_key_makes_single_step_rows_confirmable():
    html = "<div><p class='row'>探しています</p></div>"
    r = {"rows": "p.row", "row_filter": _EXCLUDE, "fields": {"note": {"selector": "."}}, "empty_container": "div"}
    res = _build(r, html)
    assert res.empty_confirmed and res.empty_evidence == "all_excluded+container"
    res = _build({**r, "empty_container": "div.gone"}, html)
    assert res.ambiguous_empty and "div.gone" in (res.ambiguous_reason or "")


def test_explicit_empty_text_keeps_evidence_name():
    r = {"rows": "p.row", "empty_text": ["いません"], "fields": {"note": {"selector": "."}}}
    res = _build(r, "<p>現在いません</p>")
    assert res.empty_confirmed and res.empty_evidence == "empty_text"
