"""W006 T634（改善 4）: AI 修復の採用条件に値の検査を足す。

誤った AI 案 4 本（#64 川口・#69 福山・#76 豊田・#84 広島）が落ち、正しい 5 件（川口の人の直し #66・福山の元のレシピ・
豊田と広島の人の直し #85・広島の AI 案 #87 から empty_absent を外したもの）が通ることを、repair() 全体（AI の返答 → 実行 →
採用条件）で固定する。#87 は 11/01 16:11 の AI 案の代わり（その案の保存は無い。#87 は 11/01 の別の run の案で、足した empty_absent も同じ）。

fixture（tests/fixtures/w006_t634_*）:
- ai_pr<番号>_<slug>.yaml: その PR の AI 案そのもの（`git show pr-<番号>:v2/recipes/<slug>.yaml`）
- before_<slug>.yaml: 案が出た時点の現行レシピ（川口は #66 の前、豊田・広島は #85 の前）
- city_fukuyama-1_{entry,child}_20261104.html: 福山の last_ok（犬 1 頭の日）。script・style を落とした実ページ
川口は t519v_g4a の 2022-08-19（子ページを辿る作り・動物のいる日）と 2026-10-21（子ページが div.wysiwyg に変わった日）、
豊田は w006_city_toyota_pdf_*（pdfplumber の結果を JSON にしたもの）、広島は w006_pref_hiroshima-1_*（10/24 の last_ok と 10/31 の実ページ）を使う。
"""

import dataclasses
import json
from pathlib import Path
from urllib.parse import urljoin

import pytest
import yaml
from bs4 import BeautifulSoup
from collector import ai_repair
from collector import recipe as recipe_mod
from collector.ai_repair import (
    check_recipe_change,
    date_in_values,
    evaluate_adoption,
    heading_in_values,
    repair,
    strip_added_empty_roots,
)
from collector.extract import Result
from collector.fetch import FakeFetcher
from collector.recipe import Doc
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _animal(**kw) -> dict:
    base = {"id": "a1", "species": "dog", "image_url": "https://x.test/p.jpg", "management_no": None, "shelter_date": None,
            "location": None, "breed": None, "color": None, "sex": None, "size": None, "age": None, "note": None, "name": None}
    return {**base, **kw}


# --- v1 見出し語が値に入る ------------------------------------------------------------------------
@pytest.mark.parametrize("field,value", [
    ("location", "種類 毛色 性別 体格 特徴等"),    # 豊田 #76
    ("breed", "毛色"),
    ("color", "毛色：茶"),
    ("size", " 体格　中型"),
    ("location", "収容場所 府中市"),
    ("sex", "性別"),
])
def test_v1_heading_word_as_the_value_or_at_its_start_is_caught(field, value):
    assert heading_in_values([_animal(**{field: value})])


@pytest.mark.parametrize("field,value", [
    ("color", "全体の毛色は黒で首から腹部にかけて白。"),   # 山梨 -5: 値の途中にある語は当たりでない
    ("breed", "MIX(品種不明)"),
    ("size", "体は小さいレモンほどの大きさ。"),
    ("location", "府中市南町"),
    ("note", "収容日：10月1日"),                           # 5 項目以外は見ない
    ("age", "種類不明"),
])
def test_v1_does_not_touch_words_in_the_middle_or_other_fields(field, value):
    assert heading_in_values([_animal(**{field: value})]) == []


# --- v2 shelter_date 以外に日付が入る ----------------------------------------------------------------
@pytest.mark.parametrize("field,value", [
    ("location", "令和8年10月30日に世羅郡世羅町"),         # 広島 #84
    ("location", "10月30日 世羅町"),
    ("breed", "R8.10.30"),
    ("color", "2026/10/30"),
    ("sex", "2026-10-30"),
])
def test_v2_date_in_other_fields_is_caught(field, value):
    assert date_in_values([_animal(**{field: value})])


@pytest.mark.parametrize("field,value", [
    ("location", "府中市南町2-15-20"),                      # 住所の番地は日付でない
    ("location", "世羅郡世羅町"),
    ("shelter_date", "令和8年10月30日"),                    # 収容日は日付でよい
    ("age", "2021年4月5日生"),                              # 5 項目以外は見ない
    ("note", "10月30日に保護"),
    ("size", "5.5kg"),
])
def test_v2_does_not_touch_addresses_or_the_date_fields(field, value):
    assert date_in_values([_animal(**{field: value})]) == []


# --- v3 現行の指定を消すか狭めた案 -------------------------------------------------------------------
OLD = yaml.safe_load("""
steps:
  - follow_all: "a.child@href"
    skip_errors: true
rows: "div.row"
image: {selector: "img.photo@src", exclude: ["noimage", "logo"], strip_query: true}
row_filter:
  text_has_any: ["収容日"]
  text_lacks: ["返還されました", "譲渡済"]
  field_lacks: {name: ["探しています"]}
fields:
  location: {label: "収容場所"}
  shelter_date: {label: "収容日"}
""")


def _new(**changes) -> dict:
    new = json.loads(json.dumps(OLD))
    for k, v in changes.items():
        if v is None:
            new.pop(k)
        else:
            new[k] = v
    return new


def test_v3_unchanged_or_widened_recipe_passes():
    assert check_recipe_change(OLD, _new()) == []
    widened = _new(row_filter={"text_has_any": ["収容日", "収容された日"], "text_lacks": ["返還されました", "譲渡済", "死亡"],
                               "field_lacks": {"name": ["探しています"]}})
    assert check_recipe_change(OLD, widened) == []
    assert check_recipe_change(None, _new()) == []   # 現行レシピが無い（新規）


def test_v3_dropping_location_is_caught():
    new = _new()
    del new["fields"]["location"]
    (why,) = check_recipe_change(OLD, new)
    assert "location" in why


def test_v3_dropping_the_photo_spec_is_caught_but_a_default_photo_spec_can_be_written_out():
    assert "写真" in " ".join(check_recipe_change(OLD, _new(image=None)))
    assert "写真" in " ".join(check_recipe_change(OLD, _new(image="img@src")))
    assert "写真" in " ".join(check_recipe_change(OLD, _new(image={"selector": "img.photo@src"})))   # exclude を減らした
    # もともと既定値と同じ指定を省いただけなら消したことにならない
    old = _new(image="img@src")
    assert check_recipe_change(old, {k: v for k, v in old.items() if k != "image"}) == []


def test_v3_dropping_steps_is_caught():
    assert "steps" in " ".join(check_recipe_change(OLD, _new(steps=None)))
    assert "steps" in " ".join(check_recipe_change(OLD, _new(steps=[{"follow_all": "a.child@href"}])))   # skip_errors を外した


def test_v3_dropping_exclusions_is_caught():
    narrowed = _new(row_filter={"text_has_any": ["収容日"], "text_lacks": ["譲渡済"], "field_lacks": {"name": ["探しています"]}})
    assert "返還されました" in " ".join(check_recipe_change(OLD, narrowed))
    no_field_lacks = _new(row_filter={"text_has_any": ["収容日"], "text_lacks": ["返還されました", "譲渡済"]})
    assert "探しています" in " ".join(check_recipe_change(OLD, no_field_lacks))
    assert check_recipe_change(OLD, _new(row_filter=None))   # 絞り込みを丸ごと消した


def test_v3_dropping_the_publication_deadline_is_caught():
    old = {"rows": "tr", "row_filter": {"text_has_any": ["掲載期限", "収容日"]},
           "fields": {"location": {"label": "場所"}, "deadline": {"label": "掲載期限"}}}
    new = {"rows": "tr", "row_filter": {"text_has_any": ["収容日"]}, "fields": {"location": {"label": "場所"}}}
    why = " ".join(check_recipe_change(old, new))
    assert "掲載期限" in why


# --- AI が足した器の指定は無条件に外す -----------------------------------------------------------------
def test_added_empty_roots_are_removed_but_existing_ones_stay():
    old = {"rows": "tr", "empty_text": ["なし"], "empty_selector": ["div.keep"], "empty_container": "div.list"}
    new = {"rows": "tr", "empty_text": ["なし", "新しい文言"], "empty_selector": ["div.keep", "div.added"],
           "empty_container": "div.list", "empty_absent": {"page": "h2", "none": "tr"}}
    got, removed = strip_added_empty_roots(old, new)
    assert got["empty_text"] == ["なし", "新しい文言"]   # 文言は残す（器の型だけが対象）
    assert got["empty_selector"] == ["div.keep"] and got["empty_container"] == "div.list" and "empty_absent" not in got
    assert removed and all(isinstance(x, str) for x in removed)
    assert new["empty_absent"]                           # 引数を書き換えない


def test_new_recipe_without_old_loses_every_added_empty_root():
    got, removed = strip_added_empty_roots(None, {"rows": "tr", "empty_container": "div.list", "empty_selector": "div.x"})
    assert "empty_container" not in got and "empty_selector" not in got and len(removed) == 2


# --- evaluate_adoption に載る ---------------------------------------------------------------------
def _res(animals: list[dict]) -> Result:
    r = Result()
    r.animals = animals
    r.rows = len(animals)
    return r


def test_evaluate_adoption_reports_v1_v2_v3_and_marks_unverified_proposals_as_manual():
    bad = _res([_animal(location="令和8年10月30日に世羅町", breed="毛色")])
    ad = evaluate_adoption(bad, recipe_change=["v3 location の指定を消している"], replay=([], 0))
    text = " / ".join(ad.violations)
    assert "v1" in text and "v2" in text and "v3" in text
    clean = evaluate_adoption(_res([_animal(location="世羅町")]), recipe_change=[], replay=([], 0))
    assert clean.violations == [] and clean.manual_only and "半自動の対象外" in clean.line()
    checked = evaluate_adoption(_res([_animal(location="世羅町")]), recipe_change=[], replay=([], 2))
    assert not checked.manual_only and "半自動の対象外" not in checked.line() and any(x.startswith("v4") for x in checked.passed)


def test_evaluate_adoption_without_the_new_arguments_keeps_the_old_behaviour():
    ad = evaluate_adoption(_res([_animal(location="世羅町")]))
    assert ad.violations == [] and not ad.manual_only and not any(x.startswith(("v3", "v4")) for x in ad.skipped)


# --- repair() 全体: 誤った AI 案 4 本は落ち、正しい 5 件は通る --------------------------------------------
def _source(slug: str, before: str | None) -> object:
    """案が出た時点の現行レシピ（before 指定）を recipe に据えた台帳エントリ。"""
    return dataclasses.replace(SOURCES[slug], recipe=str(FIX / before)) if before else SOURCES[slug]


def _ask(text: str):
    return lambda prompt, schema, timeout: {"recipe_yaml": text, "note": "テスト"}


def _replay(tmp_path: Path, docs: dict[str, str], count: int) -> Path:
    """last_ok の保存（index.json と N.bin）。"""
    d = tmp_path / "last_ok" / "slug"
    d.mkdir(parents=True)
    entries = []
    for i, (url, html) in enumerate(docs.items()):
        (d / f"{i}.bin").write_bytes(html.encode("utf-8"))
        entries.append({"url": url, "final_url": url, "file": f"{i}.bin"})
    (d / "index.json").write_text(json.dumps({"date": "2026-10-24", "count": count, "docs": entries}), encoding="utf-8")
    return tmp_path / "last_ok"


def _last_ok_dir(tmp_path: Path, slug: str, docs: dict[str, str], count: int) -> Path:
    root = _replay(tmp_path, docs, count)
    (root / "slug").rename(root / slug)
    return root


def _run(slug: str, before: str | None, pages: dict, new_text: str, last_ok_dir: Path | None, redirects: dict | None = None,
         tmp_path: Path | None = None, last_ok_count: int | None = None):
    return repair(_source(slug, before), fetcher=FakeFetcher(pages, redirects), ask=_ask(new_text), save=False,
                  last_ok_dir=last_ok_dir or (tmp_path / "no_last_ok"), last_ok_count=last_ok_count)


# 川口
K1 = SOURCES["city_kawaguchi-1"]
K_BASE = K1.url.rsplit("/", 1)[0]


def _kawaguchi_pages(entry: str, child: str) -> dict[str, str]:
    soup = BeautifulSoup(_fx(entry), "lxml")
    hrefs = [a["href"] for a in soup.select("#contents-in ul.level1col2 li.page a") if "/lost/25529" not in a["href"]]
    assert len(hrefs) == 1, hrefs
    return {K1.url: _fx(entry), urljoin(K1.url, hrefs[0]): _fx(child)}


K_TODAY = ("t519v_g4a_kawaguchi-1_20261021_entry.html", "t519v_g4a_kawaguchi-1_20261021_child.html")
K_OLD_LAYOUT = ("t519v_g4a_kawaguchi-1_20220819_entry.html", "t519v_g4a_kawaguchi-1_20220819_child.html")


def test_kawaguchi_ai_pr64_is_rejected_for_dropping_steps_and_location(tmp_path):
    r = _run("city_kawaguchi-1", "w006_t634_before_city_kawaguchi-1.yaml", _kawaguchi_pages(*K_TODAY),
             _fx("w006_t634_ai_pr64_city_kawaguchi-1.yaml"), None, tmp_path=tmp_path)
    assert r.status == "failed" and "v3" in (r.error or "") and "location" in (r.error or "") and "steps" in (r.error or "")


def test_kawaguchi_ai_pr64_is_also_rejected_by_the_saved_old_layout_pages(tmp_path):
    pages = _kawaguchi_pages(*K_OLD_LAYOUT)
    root = _last_ok_dir(tmp_path, "city_kawaguchi-1", pages, 1)
    r = _run("city_kawaguchi-1", "w006_t634_before_city_kawaguchi-1.yaml", _kawaguchi_pages(*K_TODAY),
             _fx("w006_t634_ai_pr64_city_kawaguchi-1.yaml"), root)
    assert r.status == "failed" and "v4" in (r.error or "")


def test_kawaguchi_human_fix_pr66_passes_and_matches_the_old_layout(tmp_path):
    root = _last_ok_dir(tmp_path, "city_kawaguchi-1", _kawaguchi_pages(*K_OLD_LAYOUT), 1)
    r = _run("city_kawaguchi-1", "w006_t634_before_city_kawaguchi-1.yaml", _kawaguchi_pages(*K_TODAY),
             _fx("../../recipes/city_kawaguchi-1.yaml"), root)
    assert r.status == "ok", r.error


# 福山
F1 = SOURCES["city_fukuyama-1"]
F_CHILD = "https://www.city.fukuyama.hiroshima.jp/soshiki/dobutsuaigo/416232.html"
F_PAGES = {F1.url: _fx("w006_t634_city_fukuyama-1_entry_20261104.html"), F_CHILD: _fx("w006_t634_city_fukuyama-1_child_20261104.html")}


def test_fukuyama_ai_pr69_is_rejected_by_v3_and_v4(tmp_path):
    root = _last_ok_dir(tmp_path, "city_fukuyama-1", F_PAGES, 1)
    r = _run("city_fukuyama-1", None, F_PAGES, _fx("w006_t634_ai_pr69_city_fukuyama-1.yaml"), root)
    assert r.status == "failed" and "v3" in (r.error or "") and "v4" in (r.error or "")


def test_fukuyama_ai_pr69_is_rejected_by_v3_alone_without_a_saved_page(tmp_path):
    r = _run("city_fukuyama-1", None, F_PAGES, _fx("w006_t634_ai_pr69_city_fukuyama-1.yaml"), None, tmp_path=tmp_path)
    assert r.status == "failed" and "v3" in (r.error or "")


def test_fukuyama_original_recipe_passes_with_every_value_unchanged(tmp_path):
    root = _last_ok_dir(tmp_path, "city_fukuyama-1", F_PAGES, 1)
    r = _run("city_fukuyama-1", None, F_PAGES, _fx("../../recipes/city_fukuyama-1.yaml"), root)
    assert r.status == "ok", r.error


# 豊田（PDF。pdfplumber の結果を JSON から差し込む）
T1 = SOURCES["city_toyota_pdf"]
T_FINAL = "https://www.city.toyota.aichi.jp/sumaikankyo/pet/pet/1073803/1003696.html"
T_PDF = "https://www.city.toyota.aichi.jp/_res/projects/default_project/_page_/001/003/696/maigo261022.pdf"


@pytest.fixture
def toyota(monkeypatch, tmp_path):
    pdf = json.loads(_fx("w006_city_toyota_pdf_maigo261022.json"))
    monkeypatch.setattr(recipe_mod, "_make_pdf_doc",
                        lambda url, content, columns=1: Doc(url=url, pdf_tables=pdf["pdf_tables"], pdf_text=pdf["pdf_text"]))

    def run(new_text: str):
        pages = {T1.url: _fx("w006_city_toyota_pdf_entry_20261031.html"), T_PDF: b"%PDF-1.4\n"}
        return _run("city_toyota_pdf", "w006_t634_before_city_toyota_pdf.yaml", pages, new_text, None, {T1.url: T_FINAL}, tmp_path)

    return run


def test_toyota_ai_pr76_is_rejected_for_heading_words_in_the_values(toyota):
    r = toyota(_fx("w006_t634_ai_pr76_city_toyota_pdf.yaml"))
    assert r.status == "failed" and "v1" in (r.error or "")


def test_toyota_human_fix_pr85_passes_and_is_marked_manual_only(toyota):
    r = toyota(_fx("../../recipes/city_toyota_pdf.yaml"))
    assert r.status == "ok", r.error


# 広島県
H1 = SOURCES["pref_hiroshima-1"]
H_LIVE = _fx("w006_pref_hiroshima-1_live_20261031.html")


def _hiroshima(tmp_path: Path, new_text: str):
    root = _last_ok_dir(tmp_path, "pref_hiroshima-1", {H1.url: _fx("w006_pref_hiroshima-1_last_ok_20261024.html")}, 1)
    return _run("pref_hiroshima-1", "w006_t634_before_pref_hiroshima-1.yaml", {H1.url: H_LIVE}, new_text, root)


def test_hiroshima_ai_pr84_is_rejected_for_a_date_in_location_and_changed_old_values(tmp_path):
    r = _hiroshima(tmp_path, _fx("w006_t634_ai_pr84_pref_hiroshima-1.yaml"))
    assert r.status == "failed" and "v2" in (r.error or "") and "v4" in (r.error or "")


def test_hiroshima_human_fix_pr85_passes_and_reads_the_same_values_on_the_saved_page(tmp_path):
    r = _hiroshima(tmp_path, _fx("../../recipes/pref_hiroshima-1.yaml"))
    assert r.status == "ok", r.error


def test_hiroshima_ai_pr87_passes_once_its_empty_absent_is_removed(tmp_path):
    text = _fx("w006_t634_ai_pr87_pref_hiroshima-1.yaml")
    assert "empty_absent" in text
    r = _hiroshima(tmp_path, text)
    assert r.status == "ok", r.error
    assert r.recipe_text and "empty_absent" not in yaml.safe_load(r.recipe_text)
    assert yaml.safe_load(r.recipe_text)["rows"] == yaml.safe_load(text)["rows"]   # 器の指定だけを外し、ほかは変えない


def test_ai_empty_absent_cannot_turn_a_changed_page_into_zero(tmp_path):
    """#87 の案は、器の指定を外すと子のいるページで 0 頭にならない（外さないと見出しのタグが変わるだけで 0 頭が成立する）。"""
    swapped = H_LIVE.replace("<h2", "<h3").replace("</h2>", "</h3>")
    assert swapped != H_LIVE
    root = _last_ok_dir(tmp_path, "pref_hiroshima-1", {H1.url: _fx("w006_pref_hiroshima-1_last_ok_20261024.html")}, 1)
    r = repair(_source("pref_hiroshima-1", "w006_t634_before_pref_hiroshima-1.yaml"), fetcher=FakeFetcher({H1.url: swapped}),
               ask=_ask(_fx("w006_t634_ai_pr87_pref_hiroshima-1.yaml")), save=False, last_ok_dir=root)
    assert r.status == "failed" and "empty_absent" not in yaml.safe_load(r.recipe_text or "")


def test_dumped_recipe_keeps_the_leading_comment(tmp_path):
    r = _hiroshima(tmp_path, _fx("w006_t634_ai_pr87_pref_hiroshima-1.yaml"))
    assert (r.recipe_text or "").lstrip().startswith("#")


def test_module_exposes_the_check_names():
    assert hasattr(ai_repair, "HEADING_WORDS") and "収容場所" in ai_repair.HEADING_WORDS
