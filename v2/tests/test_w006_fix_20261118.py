"""W006 2026-11-18 の収集で読めなかった 4 掲載元を直す（ネットワークなし）。

fixture は 2026-11-18 に取得した実ページ（script・style・コメントを落とした）。船橋の子のいる日だけ 11/17 0:05 の収集の保存ページ。
- 船橋 収容犬猫（city_funabashi-1）: 0 頭の日に「※現在公示中の動物はいません。」の文が出ず、表が見出し行だけになった
- 富山県 氷見支所・小矢部支所（pref_toyama_himi・pref_toyama_oyabe。レシピは 8 ページ共用の pref_toyama_center）:
  11/17 から収容日が西暦（2026年11月17日）、写真が .png（20261117cat1.png・20261117a.png）で載る。レシピは和暦だけを読み、
  .png は全部「いません」の仮画像として捨てていたので、氷見の猫 1 頭が載らず、小矢部の猫は写真なしで載っていた
- 北海道 宗谷総合振興局（hokkaido_souya-1）: ネットワーク事業の節に初めて子の表が載った（猫 3 行。1 行は子猫 4 頭をまとめた行）
- 福岡市の暫定ページ 猫（city_fukuoka_interim-2）: 0 頭の日の文「現在、センターに収容されている猫はいません。」が初めて出た
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from collector.extract import Result, build, empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.recipe_schema import validate_recipe_dict
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

FUNABASHI = "city_funabashi-1"
FUNABASHI_ZERO = "w006_city_funabashi-1_zero_20261118.html"   # 表は見出し行だけ・0 頭の文なし
FUNABASHI_DOG = "w006_city_funabashi-1_20261117.html"         # 犬 1 頭（D-261109-01）
HIMI = "pref_toyama_himi"
HIMI_CAT = "w006_pref_toyama_himi_20261118.html"              # 猫 1 頭（保護猫8-1・西暦の収容日・.png の写真 2 枚）
OYABE = "pref_toyama_oyabe"
OYABE_CAT = "w006_pref_toyama_oyabe_20261118.html"            # 猫 1 頭（小矢部8-c-1・和暦の収容日・.png の写真）
SOUYA = "hokkaido_souya-1"
SOUYA_CATS = "w006_hokkaido_souya-1_20261118.html"            # 稚内保健所：6（表は 3 行）・ほか 3 か所は 0
FUK_CAT = "city_fukuoka_interim-2"
FUK_CAT_ZERO = "w006_city_fukuoka_cathoused_zero_20261118.html"
FUK_CAT_SENTENCE = "現在、センターに収容されている猫はいません。"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _doc(slug: str, html: str) -> Doc:
    return Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))


def _recipe(slug: str) -> Recipe:
    return Recipe.load(ROOT / SOURCES[slug].recipe)


def _run(slug: str, html: str) -> Result:
    return build(SOURCES[slug], _recipe(slug), [_doc(slug, html)])


def _collect(slug: str, html: str) -> Collected:
    # 福岡市は 2026-11-19 の返事で台帳がリンクのみ（T630）。レシピは残すので mode を recipe にして読み続ける
    src = dataclasses.replace(SOURCES[slug], enabled=True, mode="recipe")
    return collect_one(src, FakeFetcher({src.url: html}))


def _zero_evidence(slug: str, html: str) -> list[str]:
    """0 頭の根拠のうち、このページで成立するもの（ops/audit_empty.py が子のいる日の保存ページに当てるのと同じ関数）。"""
    doc = _doc(slug, html)
    return [h.kind for h in empty_hits(_recipe(slug), [doc], [doc])]


def _swap(html: str, old: str, new: str, count: int = -1) -> str:
    assert old in html, old
    return html.replace(old, new, count)


@pytest.mark.parametrize("slug", [FUNABASHI, HIMI, OYABE, SOUYA, FUK_CAT])
def test_changed_recipes_pass_the_strict_schema(slug: str) -> None:
    raw = yaml.safe_load((ROOT / SOURCES[slug].recipe).read_text(encoding="utf-8"))
    assert validate_recipe_dict(raw, SOURCES[slug].url) == []


# --- 船橋 収容犬猫: 0 頭の日に文が出ず、表が見出し行だけ -----------------------------------------------------------------
def test_funabashi_header_only_table_without_the_sentence_is_a_zero_day() -> None:
    html = _fx(FUNABASHI_ZERO)
    assert "公示中の動物はいません" not in html
    c = _collect(FUNABASHI, html)
    assert c.status == "empty", c.error
    assert c.result is not None and c.result.animals == [] and c.result.empty_evidence == "empty_absent"


def test_funabashi_day_with_a_dog_is_read_and_no_zero_evidence_holds() -> None:
    html = _fx(FUNABASHI_DOG)
    res = _run(FUNABASHI, html)
    assert [(a["management_no"], a["species"], a["shelter_date"]) for a in res.animals] == [("D-261109-01", "dog", "令和8年11月9日")]
    assert _zero_evidence(FUNABASHI, html) == []


def test_funabashi_row_that_cannot_be_read_is_not_zero() -> None:
    # 見出し行の下に、番号も収容日も読めない行が足された日（作りが変わった・書き方が変わった）。0 頭にせず failed で通知する
    soup = BeautifulSoup(_fx(FUNABASHI_ZERO), "lxml")
    head = soup.select_one("div.boxEntryFreeform table tr")
    assert head is not None
    row = soup.new_tag("tr")
    for text in ["（番号なし）", "", "", "潮見町", "犬", "雑種", "茶", "オス", "中", "", ""]:
        td = soup.new_tag("td")
        td.string = text
        row.append(td)
    head.insert_after(row)
    c = _collect(FUNABASHI, str(soup))
    assert c.status == "failed", c.status


def test_funabashi_second_heading_row_is_not_zero() -> None:
    # 子の行を th で書いた日も 0 頭にしない（見出し行の下に行が 1 つでもあれば根拠にしない）
    soup = BeautifulSoup(_fx(FUNABASHI_ZERO), "lxml")
    head = soup.select_one("div.boxEntryFreeform table tr")
    assert head is not None
    row = soup.new_tag("tr")
    th = soup.new_tag("th")
    th.string = "D-261118-01"
    row.append(th)
    head.insert_after(row)
    assert _zero_evidence(FUNABASHI, str(soup)) == []


def test_funabashi_table_with_other_headings_is_not_zero() -> None:
    # 表の見出しが変わった（別の表に差し替わった）日は 0 頭にしない
    html = _swap(_fx(FUNABASHI_ZERO), "公示<br />", "掲示<br />")
    c = _collect(FUNABASHI, html)
    assert c.status == "failed", c.status


def test_funabashi_table_gone_is_not_zero() -> None:
    soup = BeautifulSoup(_fx(FUNABASHI_ZERO), "lxml")
    table = soup.select_one("div.boxEntryFreeform table")
    assert table is not None
    table.decompose()
    c = _collect(FUNABASHI, str(soup))
    assert c.status == "failed", c.status


# --- 富山県 氷見支所・小矢部支所: 西暦の収容日と .png の写真 --------------------------------------------------------------
def test_himi_cat_with_western_date_and_png_photo_is_read() -> None:
    c = _collect(HIMI, _fx(HIMI_CAT))
    assert c.status == "ok", c.error
    assert c.result is not None
    assert len(c.result.animals) == 1
    a = c.result.animals[0]
    assert a["species"] == "cat"
    assert a["management_no"] == "保護猫8-1"
    assert a["shelter_date"] == "2026年11月17日"
    assert a["location"] == "氷見市朝日丘3-10前路上"
    assert (a["breed"], a["size"], a["sex"], a["color"]) == ("雑種", "中", "メス", "灰・白")
    assert a["note"] == "眼があまり見えていない"
    assert a["image_url"] == "https://www.pref.toyama.jp/images/14793/20261117cat1.png"


def test_himi_empty_dog_block_does_not_become_a_dog_with_the_cats_number() -> None:
    # 氷見は閉じタグの崩れで、犬の枠が猫の枠まで飲み込む。猫の管理番号が番号らしい形でも、空の犬の枠を犬にしない
    html = _swap(_fx(HIMI_CAT), "保護猫8-1", "R8-123")
    res = _run(HIMI, html)
    assert [(a["species"], a["management_no"]) for a in res.animals] == [("cat", "R8-123")]


def test_himi_japanese_era_date_is_still_read() -> None:
    res = _run(HIMI, _swap(_fx(HIMI_CAT), "2026年11月17日", "令和8年11月17日"))
    assert [a["shelter_date"] for a in res.animals] == ["令和8年11月17日"]


def test_himi_blank_shelter_date_does_not_take_the_notice_period() -> None:
    # 収容日が空欄の日に、後ろの「掲載期間 2026年11月24日」を収容日にしない（写真があるので子は載る）
    res = _run(HIMI, _swap(_fx(HIMI_CAT), ">2026年11月17日<", "><"))
    assert len(res.animals) == 1
    assert res.animals[0]["shelter_date"] is None


def test_oyabe_cat_gets_its_png_photo() -> None:
    res = _run(OYABE, _fx(OYABE_CAT))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["management_no"], a["shelter_date"]) == ("cat", "小矢部8-c-1", "令和8年11月17日")
    assert a["image_url"] == "https://www.pref.toyama.jp/images/14795/20261117a.png"


# 2026-11-18 の 8 ページに実在した「いません」の仮画像の名前。写真にしない
@pytest.mark.parametrize("name", ["dog.png", "cat.png", "cat_1.png", "inai.png", "inu00.png", "neko00.png", "img_purpose_01.png"])
def test_toyama_placeholder_png_is_not_a_photo(name: str) -> None:
    html = _swap(_fx(HIMI_CAT), "20261117cat1.png", name)
    html = _swap(html, "20261117cat2.png", name)
    res = _run(HIMI, html)
    assert [(a["management_no"], a["image_url"]) for a in res.animals] == [("保護猫8-1", None)]


@pytest.mark.parametrize("src", ["dog.png", "./cat.png", "../images/inai.png"])
def test_toyama_placeholder_png_with_a_relative_path_is_not_a_photo(src: str) -> None:
    # 仮画像の src が「/」で始まらない書き方でも写真にしない（#133 reviewer P5）
    html = _swap(_fx(HIMI_CAT), "/images/14793/20261117cat1.png", src)
    html = _swap(html, "/images/14793/20261117cat2.png", src)
    res = _run(HIMI, html)
    assert [(a["management_no"], a["image_url"]) for a in res.animals] == [("保護猫8-1", None)]


# --- 北海道 宗谷総合振興局: ネットワーク事業の表に初めて子が載った -----------------------------------------------------
def test_souya_reads_the_three_rows_of_the_network_table() -> None:
    c = _collect(SOUYA, _fx(SOUYA_CATS))
    assert c.status == "ok", c.error
    assert c.result is not None
    got = [(a["management_no"], a["species"], a["sex"], a["age"], a["color"], a["location"]) for a in c.result.animals]
    # 値はエンジンが NFKC にそろえる（掲載元は「R8-3～6」「ブチ（白黒）：オス、…」「2ヶ月齢（推定）」と全角で書いている）
    assert got == [
        ("R8-1", "cat", "オス", "不明", "黒", "稚内保健所"),
        ("R8-2", "cat", "メス", "高齢", "白・グレー", "稚内保健所"),
        ("R8-3~6", "cat", "ブチ(白黒):オス、その他の子猫:メス", "2ヶ月齢(推定)", None, "稚内保健所"),
    ]
    assert c.result.animals[0]["note"] == "人懐っこい、甘えん坊、穏やか"
    # 写真はポスターの PDF の中にしか無い。元ページのリンクは掲載のページ
    assert {a["image_url"] for a in c.result.animals} == {None}
    assert {a["source_url"] for a in c.result.animals} == {SOURCES[SOUYA].url}
    assert len({a["id"] for a in c.result.animals}) == 3


def test_souya_does_not_read_the_owners_note_section() -> None:
    # 「飼い主さがしノート」の節は飼い主個人の掲載（保健所にはいない）。写真の p は行にしない。
    # 行になるのはネットワーク事業の表の 4 行（見出し行 + 3 掲載）だけで、見出し行は動物にならない
    html = _fx(SOUYA_CATS)
    assert "あんみつ" in html
    res = _run(SOUYA, html)
    assert res.rows == 4
    assert [a["management_no"] for a in res.animals] == ["R8-1", "R8-2", "R8-3~6"]
    assert [d.reason for d in res.dropped] == ["必須項目が読めない（species）"]


def _souya_table_rows(soup: BeautifulSoup) -> list:
    trs = soup.select("table:has(caption) tr")
    assert len(trs) == 4
    return trs


@pytest.mark.parametrize("at", [0, 3, 6, 7])
def test_souya_inserted_column_is_not_read_with_shifted_values(at: int) -> None:
    # 列が 1 つ増えた日（先頭・途中・収容場所の手前）。位置で読むので、ずれた値（収容場所に日付など）で載せず failed で通知する
    soup = BeautifulSoup(_fx(SOUYA_CATS), "lxml")
    for i, tr in enumerate(_souya_table_rows(soup)):
        td = soup.new_tag("td")
        td.string = "体格" if i == 0 else "2026-12-01"
        tr.insert(at, td)
    c = _collect(SOUYA, str(soup))
    assert c.status == "failed", c.status
    assert c.result is not None and c.result.animals == []


def test_souya_swapped_columns_are_not_read() -> None:
    # 年齢と毛色の列が入れ替わった日も、入れ替わった値のまま載せない
    soup = BeautifulSoup(_fx(SOUYA_CATS), "lxml")
    for tr in _souya_table_rows(soup):
        tds = tr.find_all("td", recursive=False)
        age, color = tds[3], tds[4]
        color.extract()
        age.insert_before(color)
    c = _collect(SOUYA, str(soup))
    assert c.status == "failed", c.status


def test_souya_heading_row_in_thead_does_not_drop_the_first_cat() -> None:
    # 見出し行だけ thead に包まれた日も、tbody の 1 行目（R8-1）を見出し扱いで落とさない
    soup = BeautifulSoup(_fx(SOUYA_CATS), "lxml")
    table = soup.select_one("table:has(caption)")
    assert table is not None
    head = _souya_table_rows(soup)[0].extract()
    thead = soup.new_tag("thead")
    thead.append(head)
    tbody = table.find("tbody")
    assert tbody is not None
    tbody.insert_before(thead)
    res = _run(SOUYA, str(soup))
    assert [a["management_no"] for a in res.animals] == ["R8-1", "R8-2", "R8-3~6"]


def test_souya_row_with_a_missing_cell_is_not_listed_with_a_wrong_place() -> None:
    # 2 行目（R8-2）の公開期限のセルが欠けた日。8 列目がポスターのリンク文字になるので、その行は載せない（#133 reviewer R1）
    soup = BeautifulSoup(_fx(SOUYA_CATS), "lxml")
    cells = _souya_table_rows(soup)[2].find_all("td", recursive=False)
    assert len(cells) == 9
    cells[6].extract()
    res = _run(SOUYA, str(soup))
    assert [(a["management_no"], a["location"]) for a in res.animals] == [("R8-1", "稚内保健所"), ("R8-3~6", "稚内保健所")]


def test_souya_note_row_is_not_an_animal() -> None:
    # 表の末尾に注記の行（列をまたぐ 1 セル）が足された日も、動物にしない
    soup = BeautifulSoup(_fx(SOUYA_CATS), "lxml")
    last = _souya_table_rows(soup)[-1]
    row = soup.new_tag("tr")
    td = soup.new_tag("td", attrs={"colspan": "9"})
    td.string = "※見学は予約が必要です。犬猫の状態により公開を終えることがあります。"
    row.append(td)
    last.insert_after(row)
    res = _run(SOUYA, str(soup))
    assert [a["management_no"] for a in res.animals] == ["R8-1", "R8-2", "R8-3~6"]


def test_souya_day_with_cats_has_no_zero_evidence() -> None:
    assert _zero_evidence(SOUYA, _fx(SOUYA_CATS)) == []


def test_souya_zero_day_is_still_zero() -> None:
    c = _collect(SOUYA, _fx("w006_hokkaido_zero_souya-1_20261107.html"))
    assert c.status == "empty", c.error


# --- 福岡市の暫定ページ 猫: 0 頭の日の文 -----------------------------------------------------------------------------
def test_fukuoka_cat_zero_sentence_alone_is_a_zero_day() -> None:
    html = _fx(FUK_CAT_ZERO)
    assert FUK_CAT_SENTENCE in html
    c = _collect(FUK_CAT, html)
    assert c.status == "empty", c.error
    assert c.result is not None and c.result.empty_evidence == "empty_absent"


@pytest.mark.parametrize("name", ["w006_city_fukuoka_cathoused_20261113.html", "w006_city_fukuoka_cathoused_20261031.html"])
def test_fukuoka_cat_days_with_cats_have_no_zero_evidence(name: str) -> None:
    html = _fx(name)
    assert FUK_CAT_SENTENCE not in html
    assert _zero_evidence(FUK_CAT, html) == []


def test_fukuoka_cat_stale_sentence_with_a_cat_block_is_not_zero() -> None:
    # 手編集で文を消し忘れたまま子の枠（表）が足された日は 0 頭にしない
    child = BeautifulSoup(_fx("w006_city_fukuoka_cathoused_20261113.html"), "lxml").select_one("div.f_parallel2:has(table)")
    assert child is not None
    soup = BeautifulSoup(_fx(FUK_CAT_ZERO), "lxml")
    box = soup.select_one("div.f_parallel2")
    assert box is not None
    box.insert_after(BeautifulSoup(str(child), "lxml").select_one("div.f_parallel2"))
    assert _zero_evidence(FUK_CAT, str(soup)) == []


def test_fukuoka_cat_sentence_gone_is_not_zero() -> None:
    c = _collect(FUK_CAT, _swap(_fx(FUK_CAT_ZERO), FUK_CAT_SENTENCE, ""))
    assert c.status == "failed", c.status


def test_fukuoka_dog_zero_day_is_still_zero() -> None:
    res = _run("city_fukuoka_interim-1", _fx("w006_city_fukuoka_doghoused_zero_20261106.html"))
    assert res.animals == [] and res.empty_confirmed and res.empty_evidence == "empty_absent"
