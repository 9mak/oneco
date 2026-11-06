"""W006 T631: 子のいる日にも常に出る文字を 0 頭の根拠にしていた 12 slug の直し（ネットワークなし）。

empty は ok と同じ扱いで通知も修復も止まる。だから子がいる日に当たる文言を 0 頭の根拠にすると、行の読み方が崩れた日に
子がいるのに「本日は 0 頭」と黙って出る。ここでは各 slug について次を確かめる。
- 子のいる版の fixture（2026-10-22〜11-06 に保存した実ページから script・style を落としたもの）で、0 頭の根拠（collector.extract の empty_hits）が成立しない
- 0 頭の日の fixture（実ページ・Wayback）は、直した後も 0 頭と確定する
- 器・枠を根拠にした slug は、行のタグや class が変わった合成ページで 0 頭にならない（広島 #84 の教訓）
徳島 -1 は 3 つの一覧の空の文を見分ける道具が無いので根拠を持たない（fail closed）。
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector import recipe as recipe_mod
from collector.extract import build, empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _doc(url: str, html: str) -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _hits(slug: str, html: str, url: str | None = None):
    """入口 1 枚だけのプールに、レシピの 0 頭の根拠が成立するか。"""
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [_doc(url or SOURCES[slug].url, html)])


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _swap(html: str, old: str, new: str) -> str:
    """実ページの一部を置き換えた合成ページ。置き換えが実際に効いたことを確かめる（効かないと試験が素通りする）。"""
    assert old in html, old
    out = html.replace(old, new)
    assert out != html
    return out


def _zero_of(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 千葉県 動愛センター（pref_chiba-1・-2・-4・-5） ----------------------------------------------------------------
# 「種類・毛色・オスメス」は雛形ブロック（h2「テンプレート【収容日】…」と no_gazou.png の写真）の文字で、子のいる日にも末尾に毎日残る。
# 0 頭の日は雛形ブロックしか無い（見出しもテンプレートだけ）。0 頭は empty_absent で決める。
CHIBA_KIDS = {
    "pref_chiba-1": ("t631_pref_chiba-1_children_20261106.html", 4),
    "pref_chiba-2": ("t631_pref_chiba-2_children_20261031.html", 1),
    "pref_chiba-4": ("t631_pref_chiba-4_children_20261106.html", 1),
    "pref_chiba-5": ("t631_pref_chiba-5_children_20261106.html", 1),
}
CHIBA_ZERO = "t631_pref_chiba-2_zero_20261106.html"


@pytest.mark.parametrize("slug", list(CHIBA_KIDS))
def test_chiba_children_day_has_the_template_text_but_no_zero_evidence(slug):
    name, n = CHIBA_KIDS[slug]
    html = _fx(name)
    assert "種類・毛色・オスメス" in html  # 雛形の文字は子のいる日にも出る（これを根拠にしていた）
    assert _hits(slug, html) == []
    c = _single(slug, html)
    assert c.status == "ok" and len(c.result.animals) == n


@pytest.mark.parametrize("slug", list(CHIBA_KIDS))
def test_chiba_template_only_page_is_zero(slug):
    c = _single(slug, _fx(CHIBA_ZERO))
    assert _zero_of(c), c.error
    assert c.result.empty_evidence in {"empty_absent", "all_excluded+container"}


@pytest.mark.parametrize("slug", list(CHIBA_KIDS))
def test_chiba_rows_container_renamed_with_children_present_is_not_zero(slug):
    # 行の入れ物（div.col2）の class が変わり、子の行を取れなくなった日。子の見出し・写真が残るので 0 頭にしない
    name, _ = CHIBA_KIDS[slug]
    html = _fx(name).replace('class="col2"', 'class="colTwo"')
    assert html != _fx(name)
    c = _single(slug, html)
    assert c.status == "failed" and c.result is not None and c.result.animals == []


@pytest.mark.parametrize("slug", list(CHIBA_KIDS))
def test_chiba_children_heading_tag_changed_is_not_zero(slug):
    # 子の収容日の見出し h2 が h3 に変わり、行も読めない日。写真が残るので 0 頭にしない
    name, _ = CHIBA_KIDS[slug]
    html = (
        _fx(name)
        .replace('class="col2"', 'class="colTwo"')
        .replace("<h2>", "<h3>")
        .replace("</h2>", "</h3>")
    )
    c = _single(slug, html)
    assert c.status == "failed" and c.result.animals == []


def test_chiba_zero_page_without_the_template_frame_is_not_zero():
    # 枠（雛形の見出し）が無い日はブロック画面・作り替えとみなして 0 頭にしない
    html = _swap(_fx(CHIBA_ZERO), "テンプレート【", "別の見出し【")
    assert _single("pref_chiba-2", html).status == "failed"


def test_chiba_zero_page_with_a_real_photo_is_not_zero():
    html = _swap(
        _fx(CHIBA_ZERO),
        '<div class="col2R">',
        '<div class="col2R"><img alt="犬" src="/aigo/pet/inu-neko/shuuyou/documents/261105-001.jpg"/>',
    )
    assert _single("pref_chiba-2", html).status == "failed"


# --- さいたま市（city_saitama-2）: 雛形カード「管理番号 R08-」 -------------------------------------------------------
# 雛形カードは子のいる日にも末尾に残る（R08-58・R08-60 の後ろに「R08-」）。「R08-」の後ろに数字が付いた管理番号と、値の入った収容日があれば 0 頭にしない。
SAITAMA_KIDS = "t631_city_saitama-2_children_20261106.html"
SAITAMA_ZERO = (
    "t521_saitama-2_wb20250209.html"  # Wayback 2025-02-09: 雛形カード「R06-」だけの 0 頭の日
)


def test_saitama_children_day_has_the_template_card_but_no_zero_evidence():
    html = _fx(SAITAMA_KIDS)
    assert "管理番号 R08-</p>" in html
    assert _hits("city_saitama-2", html) == []
    c = _single("city_saitama-2", html)
    assert c.status == "ok" and len(c.result.animals) == 2


def test_saitama_template_only_day_is_zero():
    c = _single("city_saitama-2", _fx(SAITAMA_ZERO))
    assert _zero_of(c), c.error
    assert c.result.empty_evidence == "empty_absent"


def test_saitama_card_markup_changed_with_numbers_left_is_not_zero():
    # 管理番号の段落が p でなく div になり行を取れない日。番号が残っているので 0 頭にしない（タグ指定をしていないため）
    html = _fx(SAITAMA_KIDS)
    html = html.replace("<p>管理番号 R08-58</p>", "<div>管理番号 R08-58</div>").replace(
        "<p>管理番号 R08-60</p>", "<div>管理番号 R08-60</div>"
    )
    assert "<div>管理番号 R08-58</div>" in html
    html = html.replace("<p>収容日", "<span>収容日")
    c = _single("city_saitama-2", html)
    assert c.status != "empty"


def test_saitama_zero_page_with_a_numbered_card_is_not_zero():
    html = _swap(_fx(SAITAMA_ZERO), "管理番号 R06-", "管理番号 R06-12")
    assert _single("city_saitama-2", html).status != "empty"


# --- 枚方市（city_hirakata）: 案内文「掲載情報が無い場合でも」 ------------------------------------------------------
# 犬・猫それぞれの見出しの下に毎日出る案内文。子のいる日（猫 1 頭）にも犬・猫の両方に出る。
HIRAKATA_KIDS = "t631_city_hirakata_children_20261106.html"


def _hirakata_zero() -> str:
    soup = BeautifulSoup(_fx(HIRAKATA_KIDS), "lxml")
    for el in soup.select("div.mol_imageblock, div.mol_tableblock"):
        el.decompose()
    return str(soup)


def test_hirakata_children_day_has_the_notice_but_no_zero_evidence():
    html = _fx(HIRAKATA_KIDS)
    assert html.count("掲載情報が無い場合でも") == 2
    assert _hits("city_hirakata", html) == []
    c = _single("city_hirakata", html)
    assert c.status == "ok" and len(c.result.animals) == 1


def test_hirakata_notices_only_day_is_zero():
    html = _hirakata_zero()
    assert "<table" not in html and "ten1.jpeg" not in html
    c = _single("city_hirakata", html)
    assert _zero_of(c), c.error
    assert c.result.empty_evidence == "empty_absent"


def test_hirakata_card_class_renamed_is_not_zero():
    # 写真のカードの class（mol_imageblock）が変わった日。表と写真が残るので 0 頭にしない
    html = _swap(_fx(HIRAKATA_KIDS), "mol_imageblock", "mol_pictureblock").replace(
        "mol_tableblock", "mol_gridblock"
    )
    c = _single("city_hirakata", html)
    assert c.status != "empty"


def test_hirakata_table_only_page_is_not_zero():
    soup = BeautifulSoup(_hirakata_zero(), "lxml")
    soup.select_one("div.block_index_6").insert_before(
        BeautifulSoup("<table><tr><td>雑種</td></tr></table>", "lxml").table
    )
    assert _single("city_hirakata", str(soup)).status != "empty"


def test_hirakata_page_without_the_cat_heading_is_not_zero():
    html = _swap(_hirakata_zero(), "収容猫</h4>", "収容</h4>")
    assert _single("city_hirakata", html).status == "failed"


# --- 新潟県（pref_niigata） ---------------------------------------------------------------------------------------------
# 冒頭の h2「…迷子の動物の情報を掲載しています。」は子のいる日にも毎日出る。0 頭の日は動物ブロックが消えて「いません」の画像 1 枚（Wayback 2026-04-10）。
# 11/06 の実ページは h3 が管理番号、本文も「保護した日時：…」に変わっていて子 2 頭を取れていない。案内文があるので以前は「0 頭」と出ていた。
NIIGATA_OLD = "t631_pref_niigata_children_20261022.html"
NIIGATA_NEW = "t631_pref_niigata_children_20261106.html"
NIIGATA_ZERO = "t631_pref_niigata_zero_wb20260410.html"


@pytest.mark.parametrize("name", [NIIGATA_OLD, NIIGATA_NEW])
def test_niigata_children_days_have_the_intro_but_no_zero_evidence(name):
    html = _fx(name)
    assert "迷子の動物の情報を掲載しています" in html
    assert _hits("pref_niigata", html) == []


def test_niigata_old_format_day_is_read_as_before():
    c = _single("pref_niigata", _fx(NIIGATA_OLD))
    assert c.status == "ok" and len(c.result.animals) == 1


def test_niigata_new_format_day_is_not_zero():
    # 新しい書式の値は test_w006_niigata_akita_20261106.py で固定する
    c = _single("pref_niigata", _fx(NIIGATA_NEW))
    assert c.status == "ok" and len(c.result.animals) == 2


def test_niigata_no_animal_block_day_is_zero():
    c = _single("pref_niigata", _fx(NIIGATA_ZERO))
    assert _zero_of(c), c.error
    assert c.result.empty_evidence == "empty_absent"


@pytest.mark.parametrize(
    "extra",
    [
        "<h3>26長FC010</h3>",
        "<p>10月30日 長岡市で保護</p>",
        "<p>保護した日時：2026年11月5日</p>",
        "<p>雑種、オス、黒、体重 5.2Kg</p>",
    ],
)
def test_niigata_zero_page_with_a_child_in_any_form_is_not_zero(extra):
    html = _swap(
        _fx(NIIGATA_ZERO),
        "<h3>返還の際に必要な物</h3>",
        f'<div class="detail_free">{extra}</div><h3>返還の際に必要な物</h3>',
    )
    # h3 の管理番号だけの子は 1 頭として読めるので ok、行にならない形は failed。どちらも 0 頭にしない
    assert not _zero_of(_single("pref_niigata", html))


# --- 鳥取県（pref_tottori） ---------------------------------------------------------------------------------------------
# 案内文「迷い犬、迷い猫等を探している飼い主のため情報提供を目的とするもの」は子のいる日にも毎日出る。0 頭の日は専用の文言が無く、
# 収容動物の表が見出し行・返還しました等の行・空の行だけになる。
TOTTORI_KIDS = "t631_pref_tottori_children_20261030.html"
TOTTORI_RETURNED = "t631_pref_tottori_returned_only_20261106.html"


def test_tottori_children_day_has_the_notice_but_no_zero_evidence():
    html = _fx(TOTTORI_KIDS)
    assert html.count("迷い犬、迷い猫等を探している飼い主のため情報提供を目的とするもの") >= 1
    assert _hits("pref_tottori", html) == []
    c = _single("pref_tottori", html)
    assert c.status == "ok" and len(c.result.animals) == 1


def test_tottori_returned_only_day_is_zero():
    c = _single("pref_tottori", _fx(TOTTORI_RETURNED))
    assert _zero_of(c), c.error
    assert c.result.empty_evidence == "empty_absent"


def test_tottori_returned_wording_changed_is_not_zero():
    # 返還済みの行の言い回しが変わった日は、収容日つきの行が子なのか返還済みなのか分からないので 0 頭にしない
    html = _swap(_fx(TOTTORI_RETURNED), "返還しました", "飼い主へ引き渡し")
    assert _single("pref_tottori", html).status != "empty"


def test_tottori_table_heading_gone_is_not_zero():
    html = _swap(_fx(TOTTORI_RETURNED), "収容動物", "保護動物")
    assert _single("pref_tottori", html).status == "failed"


# --- 熊本市 迷子犬（city_kumamoto-1） ------------------------------------------------------------------------------------
# 見出し「迷子犬を保護しています」はサイト共通のメニューにも子ページにも毎日出る（一覧で 13 か所）。猫版 city_kumamoto-2 と同じく、
# 0 頭の日は div.kijiArea ごと消える作りを empty_absent で見る。
KUMA_LIST = "https://www.city.kumamoto.jp/doubutuaigo/list03612.html"
KUMA_LIST_FX = "t631_city_kumamoto-1_list_3dogs_20261106.html"
KUMA_KIJI_FX = "t631_city_kumamoto-1_kiji00373653_20261106.html"
KUMA_KIJI = "https://www.city.kumamoto.jp/doubutuaigo/kiji00373653/index.html"


def _kuma_zero() -> str:
    soup = BeautifulSoup(_fx(KUMA_LIST_FX), "lxml")
    for el in soup.select("div.kijiArea, div#newAreaWaku, div.newArea"):
        el.decompose()
    return str(soup)


def test_kumamoto_children_pages_have_the_heading_but_no_zero_evidence():
    assert _fx(KUMA_LIST_FX).count("迷子犬を保護しています") >= 2
    assert _hits("city_kumamoto-1", _fx(KUMA_LIST_FX), KUMA_LIST) == []
    assert _hits("city_kumamoto-1", _fx(KUMA_KIJI_FX), KUMA_KIJI) == []


def test_kumamoto_unreadable_articles_listed_is_not_zero():
    # 一覧に記事が並ぶのに記事ページを読めなかった日
    c = collect_one(SOURCES["city_kumamoto-1"], FakeFetcher({KUMA_LIST: _fx(KUMA_LIST_FX)}))
    assert c.status == "failed"


def test_kumamoto_list_without_the_article_area_is_zero():
    html = _kuma_zero()
    assert "kijiArea" not in html and "loadbox" not in html
    c = _single("city_kumamoto-1", html)
    assert _zero_of(c), c.error
    assert c.result.empty_evidence == "empty_absent"


def test_kumamoto_zero_page_without_the_heading_frame_is_not_zero():
    html = _swap(_kuma_zero(), '<h1 class="classTitle">', '<h1 class="otherTitle">')
    assert "迷子犬を保護しています" in html  # メニューには同じ文言が残る
    assert _single("city_kumamoto-1", html).status == "failed"


def test_kumamoto_container_renamed_with_article_links_is_not_zero():
    # kijiArea の class が変わっても、記事へのリンク（kiji…）が残れば 0 頭にしない
    html = (
        _fx(KUMA_LIST_FX)
        .replace("kijiArea", "articleArea")
        .replace("kijilist", "articlelist")
        .replace("loadbox", "box")
    )
    c = collect_one(SOURCES["city_kumamoto-1"], FakeFetcher({KUMA_LIST: html}))
    assert c.status != "empty"


# --- 茨城県 PDF（pref_ibaraki_pdf-2・-3） ----------------------------------------------------------------------------
# 公示 PDF の見出し「… 公表分」は子のいる PDF にも毎日印字される。-3 の「収容はありません」は 7 日分のうち収容の無い日の行で、子のいる日にも出る。
# 0 頭の日は入口ページの 7 日分の行が全部「公表はありません」「収容はありません」になり、PDF のリンクが 1 本も無い。
IBARAKI_PDF_TEXT = (
    "令和8年(2026年)11月4日 (水)\n"
    "26-0822 市町村地区名 大子町大生瀬\n収容日 2026/11/4 公表期限 2026/11/13\n種類 雑種 犬猫種 犬\n毛色 茶黒 性別 メス\n体格 中 首輪 赤\n備考\n"
    "市町村地区名\n収容日 公表期限\n種類 犬猫種\n毛色 性別\n体格 首輪\n備考\n公表分 1/1ページ\n"
)
IBARAKI = {
    "pref_ibaraki_pdf-2": ("t631_pref_ibaraki_pdf-2_entry_children_20261106.html", "kouhyou", 5),
    "pref_ibaraki_pdf-3": ("t631_pref_ibaraki_pdf-3_entry_children_20261106.html", "koinu", 3),
}


@pytest.fixture
def ibaraki(monkeypatch):
    def fake_pdf(url, content, columns=1):
        return Doc(url=url, pdf_tables=[], pdf_text=IBARAKI_PDF_TEXT)

    monkeypatch.setattr(recipe_mod, "_make_pdf_doc", fake_pdf)

    def run(slug: str, html: str) -> Collected:
        pages: dict[str, str | bytes] = {SOURCES[slug].url: html}
        for href in BeautifulSoup(html, "lxml").select("a[href$='.pdf']"):
            h = href["href"]
            if "toubora" not in h:
                pages["https://www.pref.ibaraki.jp" + h] = b"%PDF-1.4\n"
        return collect_one(SOURCES[slug], FakeFetcher(pages))

    return run


def _ibaraki_zero(slug: str) -> str:
    name, key, _ = IBARAKI[slug]
    soup = BeautifulSoup(_fx(name), "lxml")
    for a in soup.select(f"a[href*='{key}']"):
        a.parent.decompose()
    return str(soup)


@pytest.mark.parametrize("slug", list(IBARAKI))
def test_ibaraki_entry_with_pdf_links_has_no_zero_evidence_and_the_pdf_text_is_not_a_reason(
    ibaraki, slug
):
    name, key, n = IBARAKI[slug]
    html = _fx(name)
    assert html.count(f"documents/{key}") >= n
    assert "公表分" in IBARAKI_PDF_TEXT  # PDF 側の見出し。以前はこれを根拠にしていた
    assert _hits(slug, html) == []
    c = ibaraki(slug, html)
    # PDF 1 本につき 1 行（どの PDF にも同じ文字を返すので ID は 1 つにまとまる）
    assert c.status == "ok" and c.result.rows == n and len(c.result.animals) == 1


@pytest.mark.parametrize("slug", list(IBARAKI))
def test_ibaraki_all_days_without_a_pdf_is_zero(ibaraki, slug):
    html = _ibaraki_zero(slug)
    assert f"documents/{IBARAKI[slug][1]}" not in html
    assert "はありません" in html
    c = ibaraki(slug, html)
    assert _zero_of(c), c.error
    assert c.result.empty_evidence == "empty_absent"


@pytest.mark.parametrize("slug", list(IBARAKI))
def test_ibaraki_link_markup_changed_but_pdf_line_remains_is_not_zero(ibaraki, slug):
    # PDF へのリンクが a でなくなり pdf_links が 1 本も取れない日。「（PDF：…KB）」の行が残るので 0 頭にしない
    name, key, _ = IBARAKI[slug]
    soup = BeautifulSoup(_fx(name), "lxml")
    for a in soup.select(f"a[href*='{key}']"):
        a.name = "span"
        del a["href"]
        del a["class"]
    html = str(soup)
    assert f"documents/{key}" not in html and "（PDF：" in html
    c = ibaraki(slug, html)
    assert c.status == "failed"


@pytest.mark.parametrize("slug", list(IBARAKI))
def test_ibaraki_page_without_the_list_heading_is_not_zero(ibaraki, slug):
    html = _ibaraki_zero(slug)
    html = html.replace("公表（7日分は毎日更新)", "お知らせ").replace(
        "子犬・子猫の収容状況", "お知らせ"
    )
    assert ibaraki(slug, html).status == "failed"


def test_ibaraki_koinu_volunteer_pdf_alone_does_not_block_zero(ibaraki):
    # 譲渡対象登録ボランティア一覧 PDF（toubora）は収容の有無に関係なく常に載る
    html = _ibaraki_zero("pref_ibaraki_pdf-3")
    assert "toubora" in html
    assert _zero_of(ibaraki("pref_ibaraki_pdf-3", html))


# --- 徳島県（douai_tokushima-1） -----------------------------------------------------------------------------------------
# 「現在、掲載されている情報はありません」は犬・猫・その他の 3 つの一覧のうち空の一覧に出る文で、犬 74 頭の日にも「その他」の一覧に出ていた。
# 3 つとも空の日を見分けられない（同じ文が 3 回出ても 1 つの一覧が空なだけと区別できない）ので根拠を持たない。
TOKUSHIMA_KIDS = "t631_douai_tokushima-1_list1_1_children_20261106.html"
TOKUSHIMA_EMPTY_LIST = "t631_douai_tokushima-1_list1_3_zero_20261106.html"


def test_tokushima_has_no_zero_evidence_even_when_the_empty_list_sentence_is_on_the_page():
    recipe = Recipe.load(ROOT / "recipes" / "douai_tokushima-1.yaml")
    assert (
        not recipe.empty_text
        and not recipe.empty_text_all
        and not recipe.empty_absent
        and not recipe.empty_selector
    )
    kids = _doc("https://www.douai-tokushima.com/animalinfo/list1_1/", _fx(TOKUSHIMA_KIDS))
    empty = _doc("https://www.douai-tokushima.com/animalinfo/list1_3/", _fx(TOKUSHIMA_EMPTY_LIST))
    assert "現在、掲載されている情報はありません" in empty.text()
    assert empty_hits(recipe, [kids, empty]) == []
    assert empty_hits(recipe, [empty]) == []


def test_tokushima_children_in_one_list_and_empty_other_list_is_read_as_children():
    recipe = Recipe.load(ROOT / "recipes" / "douai_tokushima-1.yaml")
    kids = _doc("https://www.douai-tokushima.com/animalinfo/list1_1/", _fx(TOKUSHIMA_KIDS))
    empty = _doc("https://www.douai-tokushima.com/animalinfo/list1_3/", _fx(TOKUSHIMA_EMPTY_LIST))
    res = build(SOURCES["douai_tokushima-1"], recipe, [kids, empty])
    assert len(res.animals) == 2 and not res.empty_confirmed


def test_tokushima_all_lists_empty_is_failed_not_zero():
    recipe = Recipe.load(ROOT / "recipes" / "douai_tokushima-1.yaml")
    empty = _doc("https://www.douai-tokushima.com/animalinfo/list1_3/", _fx(TOKUSHIMA_EMPTY_LIST))
    res = build(SOURCES["douai_tokushima-1"], recipe, [empty])
    assert res.animals == [] and not res.empty_confirmed
