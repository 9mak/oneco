"""W006（2026-11-07）「静的に取れていないページ」B 班: 相模原市 収容犬の公示（city_sagamihara-2）など、
link_only だった掲載元を、子が載った日に読めなければ failed になる形で読む（ネットワークなし）。

city_sagamihara-2: 0 頭の日は h2「公示に基づく収容犬情報」の下に「現在、迷い犬の情報はありません。」の 1 文だけが出る。
子のいる日（Wayback 2026-09-03）はこの文が消え、p「令和…の公示」・p「整理番号　N」・ul（収容日時・収容場所・犬の種類…）が並ぶ。
"""

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector import recipe as recipe_mod
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# ---- 相模原市 収容犬の公示 ----
SAGA_ZERO = "w006_city_sagamihara-2_zero_20261107.html"
SAGA_ZERO_WB = "w006_city_sagamihara-2_zero_wb20250613.html"
SAGA_DOG = "w006_city_sagamihara-2_dog_wb20260903.html"


def test_sagamihara_is_recipe_mode():
    assert SOURCES["city_sagamihara-2"].mode == "recipe"


def test_sagamihara_zero_days_are_empty():
    for name in (SAGA_ZERO, SAGA_ZERO_WB):
        assert _zero(_single("city_sagamihara-2", _fx(name))), name


def test_sagamihara_dog_day_is_read_and_never_zero(monkeypatch):
    # 保存は 2026-09-03 の版（収容期限 令和8年9月3日）。収容期限の判定は今日の日付を使うので、保存の日に固定する
    from datetime import date

    from collector import extract

    monkeypatch.setattr(extract, "_today", lambda: date(2026, 9, 3))
    c = _single("city_sagamihara-2", _fx(SAGA_DOG))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert a["species"] == "dog"
    assert a["breed"] == "雑種" and a["color"] == "黒白" and a["sex"] == "オス"
    assert "二本松2-30" in a["location"]
    assert a["shelter_date"].startswith("令和8年8月28日")
    assert _hits("city_sagamihara-2", _fx(SAGA_DOG)) == []


def test_sagamihara_unknown_dog_layout_fails_instead_of_zero():
    # 犬が載った日にレシピで行が取れなくなった（作りが変わった）日は 0 頭にせず failed
    html = _fx(SAGA_DOG).replace("<li>収容日時", "<li>収容した日時").replace("整理番号", "番号")
    c = _single("city_sagamihara-2", html)
    assert not _zero(c)
    assert c.status == "failed"


def test_sagamihara_zero_sentence_alongside_other_content_is_not_zero():
    # 「情報はありません」の文が残ったまま別の内容（表・リスト・別の段落）が足された日は 0 頭にしない
    base = _fx(SAGA_ZERO)
    for extra in ("<ul><li>収容日時　令和8年11月8日</li></ul>", "<p>令和8年11月8日の公示</p>", "<table><tr><td>x</td></tr></table>"):
        html = base.replace("<p>現在、迷い犬の情報はありません。</p>", "<p>現在、迷い犬の情報はありません。</p>" + extra)
        assert not _zero(_single("city_sagamihara-2", html)), extra


# ---- 山形市 保護・収容の犬猫（city_yamagata-1） ----
# 入口は h2「保護・収容【犬】情報」「保護・収容【猫】情報」の 2 節。犬のいる日は節の下に p（「1　12月2日（木曜）青田二丁目地内で収容 犬種：… 性別：…」）と
# 写真の p.imagecenter が並ぶ（Wayback 2021-12・2022-01）。0 頭の日は「現在、保護している犬はいません。」（2024-05）か、中身の無い p だけ（2024-08・2026-11-07）。
# 作りが日で違う（2026-10-05 は犬の節にポスター画像 1 枚だけ）ので、0 頭は「節に文・写真・表・リストが無い日」だけ。読めない日は failed。
YM = SOURCES["city_yamagata-1"]
YM_ZERO = ["w006_city_yamagata-1_zero_20261107.html", "w006_city_yamagata-1_zero_wb20240528.html", "w006_city_yamagata-1_zero_wb20240815.html"]
YM_DOGS2 = "w006_city_yamagata-1_dogs2_wb20211207.html"
YM_DOG1 = "w006_city_yamagata-1_dog1_wb20220122.html"


def test_yamagata1_is_recipe_mode_and_photo_is_pending():
    assert YM.mode == "recipe"
    assert YM.photo == "pending"


def test_yamagata1_zero_days_are_empty():
    for name in YM_ZERO:
        assert _zero(_single("city_yamagata-1", _fx(name))), name


def test_yamagata1_dog_days_are_read_with_photos_and_never_zero():
    c = _single("city_yamagata-1", _fx(YM_DOGS2))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 2
    a, b = c.result.animals
    assert (a["species"], a["breed"], a["sex"], a["age"], a["shelter_date"]) == ("dog", "トイプードル系", "メス", "10歳くらい", "12月2日")
    assert a["location"] == "青田二丁目地内"
    assert (b["species"], b["breed"], b["sex"], b["shelter_date"]) == ("dog", "MIX(スパニエル系)", "オス", "12月6日")   # 全角かっこはエンジンが半角にそろえる
    assert a["image_url"].endswith("21toipu1.jpg") and b["image_url"].endswith("21tiwakkusu.jpg")
    assert a["id"] != b["id"]
    c1 = _single("city_yamagata-1", _fx(YM_DOG1))
    assert c1.result is not None and [(x["breed"], x["sex"], x["color"], x["shelter_date"]) for x in c1.result.animals] == [
        ("チワワ系", "オス", "白茶", "12月10日")]
    assert c1.result.animals[0]["location"] == "吉原西公園付近の路上"
    for name in (YM_DOGS2, YM_DOG1):
        assert _hits("city_yamagata-1", _fx(name)) == []


def test_yamagata1_poster_image_only_day_is_not_zero():
    # 2026-10-05 の作り: 犬の節にポスター画像が 1 枚だけ（文字で読めない）。0 頭にせず failed
    html = _fx(YM_ZERO[0])
    assert "保護・収容【犬】情報</h2>" in html
    html = html.replace("保護・収容【犬】情報</h2>", '保護・収容【犬】情報</h2><p class="imagecenter"><img src="../../../_res/projects/default_project/_page_/001/005/142/aoyagi.jpg" alt=""></p>')
    c = _single("city_yamagata-1", html)
    assert not _zero(c)
    assert c.status == "failed"


def test_yamagata1_other_animal_section_day_is_not_zero():
    # 2024-12 の作り: 「保護・収容【その他】情報」にインコの写真と文（性別の項目なし）。読まず、0 頭とも言わず failed
    html = _fx(YM_ZERO[0])
    other = ('<h2>保護・収容【その他】情報</h2><p class="imagecenter"><img src="../../../_res/projects/default_project/_page_/001/005/142/innko.jpg" alt=""></p>'
             "<p>11月29日（金曜）千歳一丁目地内でセキセイインコを保護しました。</p>")
    assert "<h2>その他自治体等ホームページ</h2>" in html
    html = html.replace("<h2>その他自治体等ホームページ</h2>", other + "<h2>その他自治体等ホームページ</h2>")
    c = _single("city_yamagata-1", html)
    assert not _zero(c)
    assert c.status == "failed"


def test_yamagata1_text_in_a_section_that_cannot_be_read_is_not_zero():
    html = _fx(YM_ZERO[0])
    html = html.replace("保護・収容【猫】情報</h2>", "保護・収容【猫】情報</h2><p>12月2日 収容しました。</p>")
    assert not _zero(_single("city_yamagata-1", html))


def test_yamagata1_returned_dog_is_not_listed():
    html = _fx(YM_DOG1)
    assert "マイクロチップなし" in html
    c = _single("city_yamagata-1", html.replace("マイクロチップなし", "マイクロチップなし 飼い主に返還しました"))
    assert c.result is None or not c.result.animals     # 全行除外は 0 頭とは言わず読めなかった扱い
    assert not _zero(c)


def test_yamagata1_missing_headings_is_not_zero():
    html = _fx(YM_ZERO[0]).replace("保護・収容【猫】情報", "保護・収容情報")
    assert not _zero(_single("city_yamagata-1", html))


# ---- 秋田県 収容犬情報（pref_akita-1） ----
# 県の「収容犬情報」（genre/18507）は 0 頭の日は見出しと説明文だけ（説明文は常に出る）。犬がいる日は説明文の下に ul.c-list--archive が出て、
# 「収容犬一覧（能代保健所）」のような子ページ（pages/archive/NNN）へのリンクが並ぶ（Wayback 2020-04-16）。子ページは写真と入れ子の表
# （捕獲場所・捕獲日・収容期限・収容場所／首輪・種類・性別・大きさ／年齢・毛の色・毛の長さ・備考）。
# 現行の作りで犬が載った日の保存は無いので、子ページの読み方は 2020 年の版で確かめたもの。読めなければ 0 頭にならず failed。
AK = SOURCES["pref_akita-1"]
AK_CHILD = "https://www.pref.akita.lg.jp/pages/archive/49089"
AK_ZERO = "w006_pref_akita-1_zero_20261107.html"
AK_ZERO_OLD = "w006_pref_akita-1_zero_wb20201124.html"
AK_LIST = "w006_pref_akita-1_list_wb20200416.html"
AK_KID = "w006_pref_akita-1_child_wb20200416.html"


def _akita(list_html: str, child_html: str | None = None) -> Collected:
    pages = {AK.url: list_html}
    if child_html is not None:
        pages[AK_CHILD] = child_html
    return collect_one(AK, FakeFetcher(pages))


def test_akita_is_recipe_mode_and_photo_is_pending():
    assert AK.mode == "recipe"
    assert AK.photo == "pending"   # 新しく読む掲載元。写真の扱いは県に未確認


def test_akita_zero_days_are_empty():
    # 説明文は常に出るので根拠にならない。ul.c-list--archive（子ページのリンクの並び）が無い日だけ 0 頭
    for name in (AK_ZERO, AK_ZERO_OLD):
        assert _zero(_akita(_fx(name))), name


def test_akita_dog_day_follows_the_child_page_and_reads_the_dog():
    c = _akita(_fx(AK_LIST), _fx(AK_KID))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert a["species"] == "dog"
    assert (a["location"], a["shelter_date"], a["breed"], a["sex"], a["size"], a["age"], a["color"]) == (
        "能代市字沼ノ上", "2020/4/15", "雑種", "雄", "中", "不明", "黒茶")
    assert a["image_url"] and a["image_url"].endswith("IMG_7559.JPG")
    recipe = Recipe.load(ROOT / "recipes" / "pref_akita-1.yaml")
    docs = [Doc(url=u, html=h, soup=BeautifulSoup(h, "lxml")) for u, h in ((AK.url, _fx(AK_LIST)), (AK_CHILD, _fx(AK_KID)))]
    assert empty_hits(recipe, docs, docs[1:]) == []


def test_akita_2021_dog_day_has_header_cells_as_td_and_is_read_too():
    # 2021-03 の大館保健所の子ページ（pages/archive/8899）は見出しのセルが th でなく td の strong。同じレシピで読める
    child = "https://www.pref.akita.lg.jp/pages/archive/8899"
    c = collect_one(AK, FakeFetcher({AK.url: _fx("w006_pref_akita-1_list_wb20210303.html"),
                                     child: _fx("w006_pref_akita-1_child_wb20210303.html")}))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["location"], a["breed"], a["sex"], a["size"], a["color"]) == ("大館市花岡町", "柴犬", "オス", "中型", "茶")
    assert a["image_url"] and a["image_url"].endswith("DSCN0430.JPG")


def test_akita_dog_day_with_unreadable_child_page_fails_instead_of_zero():
    # 子ページの表の作りが変わって行が取れない日は 0 頭にしない
    kid = _fx(AK_KID).replace("<table", "<div").replace("</table>", "</div>").replace("<tr", "<p").replace("</tr>", "</p>")
    c = _akita(_fx(AK_LIST), kid)
    assert not _zero(c)
    assert c.status == "failed"


def test_akita_list_with_links_but_no_page_frame_is_not_zero():
    # 説明文（枠）が無い日（作り替え・ブロック画面）は、リンクが無くても 0 頭にしない
    html = _fx(AK_ZERO).replace("収容している犬を掲載しています", "収容している犬を紹介しています")
    assert not _zero(_akita(html))


# ---- 神奈川県動物愛護センター その他動物（pref_kanagawa-3） ----
# 犬猫以外（カメ・インコ等）は species other で載せる方針（他の掲載元と同じ）に合わせ、link_only をやめて PDF を読む。
# 入口は PDF（acsonota.pdf）を 1 本落とすだけ。0 頭の日は PDF に「現在、収容期間中の犬・猫以外の動物はいません」の 1 文だけ、
# 子のいる日（Wayback 2025-06・2026-10-23）の PDF にはその文が無く表の行がある。
KG = SOURCES["pref_kanagawa-3"]
KG_PDF = "https://www.pref.kanagawa.jp/osirase/1594/awc/assets/pdf/lost/acsonota.pdf"


def _kg(monkeypatch, name: str, tables: list | None = None) -> Collected:
    pdf = json.loads(_fx(name))
    rows = pdf["pdf_tables"] if tables is None else tables
    monkeypatch.setattr(recipe_mod, "_make_pdf_doc",
                        lambda url, content, columns=1: Doc(url=url, pdf_tables=rows, pdf_text=pdf["pdf_text"]))
    pages = {KG.url: _fx("w006_pref_kanagawa-3_entry_20261107.html"), KG_PDF: b"%PDF-1.4\n"}
    return collect_one(KG, FakeFetcher(pages))


def test_kanagawa_other_is_recipe_mode_and_photo_stays_pending():
    assert KG.mode == "recipe"
    assert KG.photo == "pending"


def test_kanagawa_other_zero_day_is_empty(monkeypatch):
    assert _zero(_kg(monkeypatch, "w006_pref_kanagawa-3_zero_20261107.json"))


@pytest.mark.parametrize("name,n", [("w006_pref_kanagawa-3_wb20261023.json", 1), ("w006_pref_kanagawa-3_wb20250602.json", 2)])
def test_kanagawa_other_animal_days_are_read_as_other_and_never_zero(monkeypatch, name, n):
    c = _kg(monkeypatch, name)
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == n
    assert {a["species"] for a in c.result.animals} == {"other"}


def test_kanagawa_other_table_without_rows_and_without_the_zero_sentence_is_not_zero(monkeypatch):
    # 表の作りが変わって行が取れず、0 頭の文も無い日は 0 頭にしない
    assert not _zero(_kg(monkeypatch, "w006_pref_kanagawa-3_wb20261023.json", tables=[]))
