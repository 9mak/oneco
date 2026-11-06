"""W006 T631（設計が要る 4 slug）: 子のいる日に当たる文言を 0 頭の根拠にしない。

- empty_text_each: 辿った文書の「全部」が自分の 0 頭の文を出したときだけ 0 頭（spec_pref_gifu・city_naha_pdf）
- aniwel_okinawa-1 / -2: 一覧の告知（リンクなし）と「返還しました」の子は根拠にしない。生きている子のリンクが無いことを empty_absent で見る

fixture は 2026-11-06 の収集の保存ページ（last_ok）と Wayback Machine の保存ページから、script・style を落として本文だけにしたもの。
合成したものはファイル名に synthetic を付けてある。レシピ本体 v2/recipes/<slug>.yaml をそのまま読む。
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build, empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Executor, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _recipe(slug: str) -> Recipe:
    return Recipe.load(ROOT / "recipes" / f"{slug}.yaml")


def _html(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _doc(url: str, html: str) -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


# --- エンジン: empty_text_each ------------------------------------------------
SRC = Source(
    slug="x-1",
    name="x",
    municipality="x市",
    prefecture="x県",
    url="https://www.city.example.jp/a/",
    kind="stray",
    species="mixed",
)


def _each(*docs_body: str, each=("0頭です", "登録なし"), visited_extra: str | None = None):
    recipe = Recipe.from_dict({"rows": "li.animal", "empty_text_each": list(each)})
    docs = [
        _doc(f"https://www.city.example.jp/{i}", f"<html><body>{b}</body></html>")
        for i, b in enumerate(docs_body)
    ]
    visited = list(docs)
    if visited_extra is not None:
        visited = [
            _doc("https://www.city.example.jp/hub", f"<html><body>{visited_extra}</body></html>"),
            *docs,
        ]
    return recipe, docs, visited


def test_each_confirms_zero_only_when_every_document_has_its_own_phrase():
    recipe, docs, visited = _each("<p>A 0頭です</p>", "<p>B 登録なし</p>")
    res = build(SRC, recipe, docs, visited)
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_each"


def test_each_is_not_zero_when_one_document_lacks_the_phrase():
    # 1 つの文書だけ 0 頭の文が無い（子がいる、または作りが変わった）日。他の全部が 0 頭でも 0 頭にしない
    recipe, docs, visited = _each("<p>A 0頭です</p>", "<p>B 1頭</p>", "<p>C 登録なし</p>")
    res = build(SRC, recipe, docs, visited)
    assert res.animals == [] and not res.empty_confirmed


def test_each_does_not_count_pages_only_visited_not_rows_documents():
    # 入口のハブページは 0 頭の文を持たなくてよい（rows を当てる文書だけが対象）。逆にハブにだけ文があっても足りない
    recipe, docs, visited = _each("<p>A 0頭です</p>", visited_extra="<p>ハブ</p>")
    assert build(SRC, recipe, docs, visited).empty_confirmed
    recipe, docs, visited = _each("<p>A 別の文</p>", visited_extra="<p>0頭です</p>")
    assert not build(SRC, recipe, docs, visited).empty_confirmed


def test_each_needs_at_least_one_document():
    recipe, _, _ = _each()
    res = build(SRC, recipe, [], [])
    assert not res.empty_confirmed


def test_each_counts_img_alt():
    recipe, docs, visited = _each('<img alt="登録なし" src="/n.png">', "<p>0頭です</p>")
    assert build(SRC, recipe, docs, visited).empty_confirmed


def test_each_ignored_when_animals_exist():
    recipe, docs, visited = _each(
        '<ul><li class="animal"><img src="/a.jpg"></li></ul><p>0頭です</p>', "<p>0頭です</p>"
    )
    res = build(SRC, recipe, docs, visited)
    assert len(res.animals) == 1 and not res.empty_confirmed


def test_each_audit_hit_shares_the_same_function():
    # ops/audit_empty.py は empty_hits(recipe, pool, docs) を通る。docs を渡さない呼び方（従来）では each は成立扱いにしない
    recipe, docs, visited = _each("<p>A 0頭です</p>", "<p>B 登録なし</p>")
    hits = empty_hits(recipe, visited, docs)
    assert (
        [h.kind for h in hits] == ["empty_text_each"]
        and hits[0].count == 2
        and len(hits[0].urls) == 2
    )
    assert empty_hits(recipe, visited) == []


def test_existing_kinds_unchanged_by_docs_argument():
    recipe = Recipe.from_dict({"rows": "li.animal", "empty_text": ["0頭です"]})
    d = _doc("https://www.city.example.jp/0", "<html><body><p>0頭です</p></body></html>")
    assert [h.kind for h in empty_hits(recipe, [d])] == ["empty_text"]
    assert [h.kind for h in empty_hits(recipe, [d], [d])] == ["empty_text"]


def _errs(raw):
    return validate_recipe_dict({"rows": "tr", **raw}, "https://www.city.example.jp/a/")


def test_schema_accepts_list_of_nonblank_strings():
    assert _errs({"empty_text_each": ["現在の登録0頭"]}) == []
    assert _errs({"empty_text_each": ["a", "b"]}) == []


def test_schema_rejects_blank_empty_or_non_list():
    assert any("empty_text_each" in e for e in _errs({"empty_text_each": []}))
    assert any("empty_text_each" in e for e in _errs({"empty_text_each": ["a", " "]}))
    assert any("empty_text_each" in e for e in _errs({"empty_text_each": "現在の登録0頭"}))


# --- spec_pref_gifu ----------------------------------------------------------
GIFU_IDS = [6304, 5229, 6340, 254405, 123142, 5782, 5767, 13689, 13019, 6556, 453001]


def _gifu_docs(override: dict[int, str] | None = None) -> list[Doc]:
    override = override or {}
    return [
        _doc(
            f"https://www.pref.gifu.lg.jp/page/{i}.html",
            override.get(i) or _html(f"t631d_gifu_{i}.html"),
        )
        for i in GIFU_IDS
    ]


def _gifu_build(docs: list[Doc]):
    src, recipe = _source("spec_pref_gifu"), _recipe("spec_pref_gifu")
    hub = _doc(
        src.url,
        "<html><body><table><tr><td><a href='/page/6304.html'>岐阜</a></td></tr></table></body></html>",
    )
    visited = [hub, *docs]
    return build(src, recipe, docs, visited), recipe, visited


def _gifu_zero_day() -> dict[int, str]:
    """可茂保健所（今日は 1 頭）を 0 頭の日の作りにする（合成）: 登録済みの表を外し、見出しを 0 頭に。
    Wayback 2026-03-17 の同ページは「現在の登録0頭」+ 空の雛形の表だった。"""
    soup = BeautifulSoup(_html("t631d_gifu_5229.html"), "lxml")
    soup.select("table")[0].decompose()
    for img in soup.select(
        "img[src*='uploaded/image']"
    ):  # 子の写真（残すと空の雛形の表に写真が付いて 1 頭に見える）
        img.decompose()
    return {5229: str(soup).replace("現在の登録1頭", "現在の登録0頭")}


def test_gifu_day_with_a_child_is_read_and_no_zero_evidence_applies():
    res, recipe, visited = _gifu_build(_gifu_docs())
    assert len(res.animals) == 1 and not res.empty_confirmed
    docs = visited[1:]
    # 今日の 11 文書のうち 9 つは自分の 0 頭の文を出している。それでも全部ではない（可茂は 1 頭）ので根拠は成立しない
    assert empty_hits(recipe, visited, docs) == []


def test_gifu_child_page_whose_rows_cannot_be_read_is_not_zero():
    # 可茂の表の作りが変わって行が取れない日。他の保健所の「0頭」では 0 頭にならない（failed になって通知に出る）
    broken = _html("t631d_gifu_5229.html").replace("<table", "<div").replace("</table>", "</div>")
    res, _, _ = _gifu_build(_gifu_docs({5229: broken}))
    assert res.animals == [] and not res.empty_confirmed


def test_gifu_all_offices_zero_is_zero_even_with_different_wording():
    # 揖斐センターは「現在の登録　なし」、岐阜は「現在の登録：0頭」、関は「現在の登録0頭」と書き方が保健所ごとに違う
    res, _, _ = _gifu_build(_gifu_docs(_gifu_zero_day()))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_each"


def test_gifu_one_office_without_its_zero_phrase_blocks_zero():
    day = _gifu_zero_day()
    day[123142] = _html("t631d_gifu_123142.html").replace("現在の登録0頭", "現在の登録2頭")
    res, _, _ = _gifu_build(_gifu_docs(day))
    assert not res.empty_confirmed
    day[123142] = re.sub(
        "現在の登録0頭", "", _html("t631d_gifu_123142.html")
    )  # 文言が消えた（作り替え）日
    res, _, _ = _gifu_build(_gifu_docs(day))
    assert not res.empty_confirmed


def test_gifu_skipped_404_office_does_not_block_zero():
    # skip_errors で捨てた保健所（404）は文書に入らない。残り全部が 0 頭なら 0 頭
    docs = [d for d in _gifu_docs(_gifu_zero_day()) if not d.url.endswith("/13689.html")]
    res, _, _ = _gifu_build(docs)
    assert res.empty_confirmed


def test_gifu_recipe_has_no_any_document_empty_text():
    r = _recipe("spec_pref_gifu")
    assert r.empty_text == [] and r.empty_text_each


def test_gifu_titles_with_zero_do_not_leak_to_child_day():
    # 岐阜保健所のタイトル「（登録なし）」は 0 頭の日だけ。旧 empty_text の「登録なし」は 6 文書に出ていた
    assert "登録なし" in _html("t631d_gifu_6304.html")
    r = _recipe("spec_pref_gifu")
    assert "登録なし" not in r.empty_text_each


# --- aniwel_okinawa-1（犬）・-2（猫） --------------------------------------------
BASE = "https://www.aniwel-pref.okinawa"


def _aniwel_run(slug: str, list_html: str, children: dict[str, str]):
    src, recipe = _source(slug), _recipe(slug)
    pages = {
        src.url: list_html,
        **{f"{BASE}/animals/accommodate_view/{k}": v for k, v in children.items()},
    }
    ex = Executor(FakeFetcher(pages), recipe)
    docs = ex.resolve(src.url)
    return build(src, recipe, docs, ex.visited), recipe, docs, ex.visited


def _a1_children(skip: tuple[str, ...] = ()) -> dict[str, str]:
    return {
        p.stem.rsplit("_", 1)[1]: p.read_text(encoding="utf-8")
        for p in FIX.glob("t631d_a1_child_*.html")
        if p.stem.rsplit("_", 1)[1] not in skip
    }


RETURNED = ("26022", "26019", "26017", "26016", "25999")


def test_aniwel1_day_with_children_reads_them_and_never_fetches_returned_ones():
    # 返還済みの子は FakeFetcher に渡さない。辿ろうとすると失敗するので、辿っていないことの証明になる
    res, recipe, docs, visited = _aniwel_run(
        "aniwel_okinawa-1", _html("t631d_a1_list.html"), _a1_children(RETURNED)
    )
    assert len(res.animals) == 6 and not res.empty_confirmed
    assert empty_hits(recipe, visited, docs) == []


def test_aniwel1_children_titles_with_returned_do_not_make_zero():
    # 旧: 返還済みの子のタイトル「返還しました」が empty_text に当たり、生きている子の行が読めなかった日も 0 頭に見えた
    r = _recipe("aniwel_okinawa-1")
    assert r.empty_text == []


def test_aniwel1_children_unreadable_with_live_links_is_not_zero():
    # 生きている子のリンクがあるのに、個体ページの作りが変わって行が取れない日
    broken = dict.fromkeys(_a1_children(RETURNED), "<html><body><p>作り替え</p></body></html>")
    res, _, _, _ = _aniwel_run("aniwel_okinawa-1", _html("t631d_a1_list.html"), broken)
    assert res.animals == [] and not res.empty_confirmed


def test_aniwel1_all_returned_and_notices_only_is_zero():
    # 合成: 今日の一覧から生きている子を外した（Wayback 2025-2026 の犬の一覧に全員返還の日は無かった）
    res, _, docs, _ = _aniwel_run(
        "aniwel_okinawa-1", _html("t631d_a1_list_synthetic_all_returned.html"), {}
    )
    assert (
        docs == []
        and res.animals == []
        and res.empty_confirmed
        and res.empty_evidence == "empty_absent"
    )


def test_aniwel1_list_whose_layout_vanished_is_not_zero():
    res, _, _, _ = _aniwel_run(
        "aniwel_okinawa-1", "<html><body><p>メンテナンス中</p></body></html>", {}
    )
    assert not res.empty_confirmed


def test_aniwel1_live_link_in_changed_markup_is_not_zero():
    # 一覧の作りが変わって、生きている子が div.lists 直下の a でなくなった（それでも div.lists の中のリンク）日
    html = _html("t631d_a1_list_synthetic_all_returned.html").replace(
        '<div class="lists">',
        '<div class="lists"><section><a href="/animals/accommodate_view/26063"><p>11/5 柴犬</p></a></section>',
    )
    res, _, _, _ = _aniwel_run("aniwel_okinawa-1", html, {"26063": _a1_children()["26063"]})
    assert not res.empty_confirmed or res.animals


def _a2_children() -> dict[str, str]:
    return {
        p.stem.rsplit("_", 1)[1]: p.read_text(encoding="utf-8")
        for p in FIX.glob("t631d_a2_child_*.html")
    }


def test_aniwel2_day_with_a_child_is_read():
    res, recipe, docs, visited = _aniwel_run(
        "aniwel_okinawa-2", _html("t631d_a2_list.html"), _a2_children()
    )
    assert len(res.animals) == 1 and not res.empty_confirmed
    assert empty_hits(recipe, visited, docs) == []


def test_aniwel2_real_zero_day_from_wayback_is_zero():
    # Wayback 2025-09-15 の猫の一覧: 生きている子のリンクが無く、告知だけ 6 件
    res, _, docs, _ = _aniwel_run(
        "aniwel_okinawa-2", _html("t631d_a2_list_wb20250915_zero.html"), {}
    )
    assert docs == [] and res.empty_confirmed and res.empty_evidence == "empty_absent"


def test_aniwel2_only_a_dead_record_left_is_zero_by_excluded_rows():
    # 今日のように、リンクが 1 本で、その子の備考が「死亡」で捨てられる日。告知の文言ではなく全行除外の根拠で 0 頭
    soup = BeautifulSoup(_html("t631d_a2_list.html"), "lxml")
    for a in soup.select("div.lists > a"):
        if a["href"].endswith("/26030"):
            a.decompose()
    res, _, docs, _ = _aniwel_run("aniwel_okinawa-2", str(soup), {"25972": _a2_children()["25972"]})
    assert len(docs) == 1 and res.animals == [] and res.empty_confirmed
    assert res.empty_evidence.startswith("all_excluded")


def test_aniwel2_recipe_has_no_text_root():
    assert _recipe("aniwel_okinawa-2").empty_text == []


# --- city_naha_pdf -------------------------------------------------------------
NAHA = "https://www.city.naha.okinawa.jp/_res/projects/default_project/_page_/001/002/278/"


def _pdf(name: str) -> Doc:
    j = json.loads(_html(f"t631d_naha_{name}.pdf.json"))
    return Doc(url=j["url"], pdf_tables=j["pdf_tables"], pdf_text=j["pdf_text"])


def _naha_build(dog: Doc, cat: Doc):
    src, recipe = _source("city_naha_pdf"), _recipe("city_naha_pdf")
    entry = _doc(
        src.url, "<html><body><a href='dog.pdf'>犬</a><a href='cat.pdf'>猫</a></body></html>"
    )
    docs = [dog, cat]
    return build(src, recipe, docs, [entry, *docs]), recipe, [entry, *docs]


def test_naha_cat_child_day_dog_none_phrase_is_not_a_root():
    # 今日: 犬 PDF は「犬の収容はありません」、猫 PDF に 1 頭
    res, recipe, visited = _naha_build(_pdf("dogshuyonashipdf"), _pdf("261104catpdf"))
    assert len(res.animals) == 1 and res.animals[0]["species"] == "cat" and not res.empty_confirmed
    assert empty_hits(recipe, visited, visited[1:]) == []


def test_naha_cat_pdf_unreadable_is_not_zero_even_though_dog_pdf_says_none():
    # 猫 PDF の表の作りが変わって行が取れない日（表が空配列）。犬 PDF の「犬の収容はありません」だけでは 0 頭にしない
    cat = _pdf("261104catpdf")
    cat = Doc(url=cat.url, pdf_tables=[], pdf_text=cat.pdf_text)
    res, _, _ = _naha_build(_pdf("dogshuyonashipdf"), cat)
    assert res.animals == [] and not res.empty_confirmed


def test_naha_both_pdfs_say_none_is_zero():
    # 猫の 0 頭の PDF は Wayback 2026-03-16（catshuyonashi2025.pdf）
    res, _, _ = _naha_build(_pdf("dogshuyonashipdf"), _pdf("catshuyonashi2025"))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_text_each"


def test_naha_cat_child_day_in_april_also_not_zero():
    res, _, _ = _naha_build(_pdf("dogshuyonashipdf"), _pdf("260417cat"))
    assert len(res.animals) == 1 and not res.empty_confirmed


def test_naha_unverified_phrases_removed():
    r = _recipe("city_naha_pdf")
    assert r.empty_text == []
    assert set(r.empty_text_each) == {"犬の収容はありません", "猫の収容はありません"}
