"""W006 T624 見守り運転: 2026-10-31 の収集で読めなかった掲載元 9 件のレシピの直し（ネットワークなし）。

fixture は 2026-10-24〜11-01 に保存した実ページから script・style を落としたもの。ガードが落とす形のメール（@example・*.lg.jp・*.go.jp 以外。
滋賀 sapca の協会のアドレスだけ）は masked@example.jp に伏せた。名前は w006_<slug>_<状態>_<日付>.html（zero はその日の 0 頭、last_ok などは
直前まで正常に読めていた日で、直した後も頭数・項目が同じ）。豊田市の PDF は、エンジンと同じ pdfplumber にかけた文字と表を JSON にした
（w006_city_toyota_pdf_*.json。PDF そのものは動物の写真と作成者などのメタデータを持ち、pii-scan も html しか見ないので入れていない）。
どの試験も、台帳の url から入口を辿って読む collect_one を FakeFetcher で動かす（本番の収集と同じ流れ。status は ok・empty・failed・ambiguous_empty）。
- 豊田市 迷子動物: PDF が罫線の表に変わっていた（10/23 0 時から failed）。mode: table で見出しの名前から項目を引く
- 広島県 迷い犬: 属性 p が「センター収容日：令和8年10月30日に世羅郡世羅町で保護されました。」の 1 行に変わった（行 0）
- 長野市 保護情報: 0 頭の日の h2 が「現在、迷い犬や負傷動物等は保護していません」に変わった
- 滋賀 sapca・一関: 残った子が全部「戻りました」「死亡」の日は全行除外になり、コンテナの根拠が無く ambiguous_empty だった
- いわき市: 犬の節の頭数の文から句点が消えた（「現在、０頭です」＋空の雛形）
- 熊本市 迷子猫: 0 頭の日は div.kijiArea ごと消える（文言が出ない）
- 群馬県 東部・前橋市: 0 頭の文言が empty_text に当たっていなかった
"""

import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector import recipe as recipe_mod
from collector.extract import Result
from collector.fetch import FakeFetcher
from collector.recipe import Doc
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _collect(slug: str, pages: dict[str, str | bytes], redirects: dict[str, str] | None = None) -> Collected:
    """台帳の url から入口を辿り、レシピで読む（本番の収集 collect_one と同じ流れ）。"""
    return collect_one(SOURCES[slug], FakeFetcher(pages, redirects))


def _single(slug: str, html: str) -> Collected:
    """入口 1 枚で読むレシピ。"""
    return _collect(slug, {SOURCES[slug].url: html})


def _res(c: Collected) -> Result:
    assert c.result is not None, c.error
    return c.result


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def _text(html: str) -> str:
    """empty_text を照合する本文（Doc.text() と同じ）。"""
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def _swap(html: str, old: str, new: str, count: int = -1) -> str:
    """実ページの一部を置き換えた合成ページ。置き換えが実際に効いたことを確かめる（効かないと試験が素通りする）。"""
    assert old in html, old
    out = html.replace(old, new, count)
    assert out != html
    return out


# --- 豊田市 迷子動物（city_toyota_pdf） ---------------------------------------------------------------------------
# 入口ページの PDF（maigo261022.pdf）が「写真 収容日 収容場所 種類 毛色 性別 体格 特徴等」の罫線の表になっていた。文字（mode: text）で読むと
# 性別のセルが「オス」「（去勢済）」に割れて値が前後の行にずれ、見出しの語を値に取り、収容日は西暦 4 桁しか取らないので 0 頭・捨てた 1 の failed。
# 管理番号も写真も無いので ID は収容日だけで決まる（同じ収容日の 2 頭目は捨てる。エンジンの制約）。犬猫は表の外の節見出しにしか無いので、
# 種類・毛色の犬だけ・猫だけの語（キジ 等）で決め、決まらない子は種別なしで載せる。
TOYOTA = SOURCES["city_toyota_pdf"]
TOYOTA_FINAL = "https://www.city.toyota.aichi.jp/sumaikankyo/pet/pet/1073803/1003696.html"   # 台帳の url は 302 でここへ移った
TOYOTA_PDF = "https://www.city.toyota.aichi.jp/_res/projects/default_project/_page_/001/003/696/maigo261022.pdf"
TOYOTA_TODAY = "w006_city_toyota_pdf_maigo261022.json"           # 10/22 版: 猫の節に表が 1 つ（猫 1 頭）
TOYOTA_2019 = "w006_city_toyota_pdf_wb20190331_maigo0328.json"   # 2019-03-28 版: 犬の表 1 頭 + 猫の節に「保護しておりません」
TOYOTA_ZERO_2025 = "w006_city_toyota_pdf_wb20251211_maigo251002.json"   # 2025-10-02 版: 0 頭の 2 文だけ
TOYOTA_ZERO_2023 = "w006_city_toyota_pdf_wb20230619_230503maigo.json"   # 2023-05-03 版: 「・犬」「・猫」の節見出し付きの 0 頭


def _pdf(name: str) -> dict:
    return json.loads(_fx(name))


@pytest.fixture
def toyota(monkeypatch):
    """入口 HTML（実ページ）→ pdf_links → PDF。PDF の中身は pdfplumber の結果（文字と表）を JSON から差し込む。"""

    def run(pdf: dict) -> Collected:
        monkeypatch.setattr(recipe_mod, "_make_pdf_doc",
                            lambda url, content, columns=1: Doc(url=url, pdf_tables=pdf["pdf_tables"], pdf_text=pdf["pdf_text"]))
        pages = {TOYOTA.url: _fx("w006_city_toyota_pdf_entry_20261031.html"), TOYOTA_PDF: b"%PDF-1.4\n"}
        return _collect("city_toyota_pdf", pages, {TOYOTA.url: TOYOTA_FINAL})

    return run


def test_toyota_table_pdf_today_is_read_as_the_one_cat(toyota):
    c = toyota(_pdf(TOYOTA_TODAY))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "shelter_date", "location", "breed", "color", "sex", "size", "note", "management_no", "image_url") == {
        "species": "cat", "shelter_date": "10月20日", "location": "畝部東町", "breed": "雑種", "color": "キジ",
        "sex": "オス (去勢済)", "size": "大", "note": "緑色の首輪", "management_no": None, "image_url": None}
    assert a["source_url"] == TOYOTA.url     # PDF は日次で名前が変わるので入口ページを指す


def test_toyota_2019_table_with_a_dog_row_is_read_without_a_species(toyota):
    # 犬の語が毛色・種類に無い（雑種・白）ので種別なし。犬は表の外の節見出し「・犬」にしか書かれない
    c = toyota(_pdf(TOYOTA_2019))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "shelter_date", "location", "breed", "color", "sex", "size", "note") == {
        "species": None, "shelter_date": "3月26日", "location": "幸町", "breed": "雑種", "color": "白",
        "sex": "メス", "size": "中型", "note": "首輪なし"}


def test_toyota_species_is_decided_by_the_row_words_not_by_the_section(toyota):
    pdf = _pdf(TOYOTA_TODAY)
    pdf["pdf_tables"][0] += [["", "10月21日", "吉原町", "柴", "茶", "メス", "中", ""],
                             ["", "10月22日", "幸町", "雑種", "白", "オス", "中", ""]]
    c = toyota(pdf)
    assert [(a["shelter_date"], a["species"]) for a in _res(c).animals] == [("10月20日", "cat"), ("10月21日", "dog"), ("10月22日", None)]


@pytest.mark.parametrize("name", [TOYOTA_ZERO_2025, TOYOTA_ZERO_2023])
def test_toyota_zero_days_in_both_wordings_are_zero(toyota, name):
    c = toyota(_pdf(name))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "empty_text"


def test_toyota_one_zero_sentence_alone_is_not_zero(toyota):
    # 犬の文だけ（猫の文が続かない）。表が読めなくなった日を 0 頭に見せない（2019 年は犬の表と同じ PDF に猫の「保護しておりません」を出していた）
    pdf = _pdf(TOYOTA_ZERO_2025)
    pdf["pdf_text"] = pdf["pdf_text"].splitlines()[0]
    assert pdf["pdf_text"] == "現在、豊田市では迷子の犬を収容していません。"
    c = toyota(pdf)
    assert c.status == "failed" and _res(c).animals == []


def test_toyota_table_gone_without_a_zero_sentence_is_not_zero(toyota):
    pdf = _pdf(TOYOTA_TODAY)
    pdf["pdf_tables"] = []
    c = toyota(pdf)
    assert c.status == "failed" and _res(c).animals == []


def test_toyota_same_shelter_date_gives_the_same_id_so_the_second_animal_is_dropped(toyota):
    """制約（エンジンの make_id の作り。レシピでは直せない）: 管理番号も写真も無い行の ID は収容日で決まる。status は ok のまま dropped にだけ出る。"""
    pdf = _pdf(TOYOTA_TODAY)
    pdf["pdf_tables"][0].append(["", "10月20日", "吉原町", "柴", "茶", "メス", "中", ""])
    c = toyota(pdf)
    assert c.status == "ok" and len(_res(c).animals) == 1
    assert [d.reason for d in _res(c).dropped] == ["同じ ID の行が既にある"]


# --- 広島県 迷い犬（pref_hiroshima-1） --------------------------------------------------------------------------------
# 10/31 の 1 頭（1HD20260244）は属性 p が「…雌<br>センター収容日：令和8年10月30日に世羅郡世羅町で保護されました。<br>搬入時首輪を…」になった。
# 以前の「センターに収容された日：…／保護された状況：…」の 2 行が 1 行にまとまり語も「収容日」に変わったので、row_filter の「収容された日」に
# 当たらず行 0・捨てた 0（empty_text も出ない）の failed。10/25〜10/30 0 時のページは保存が無く、0 頭の日の書き方は未確認（empty_text は足さない）。
HIROSHIMA_FIELDS = ("species", "management_no", "breed", "age", "sex", "shelter_date", "location", "note", "image_url")


def test_hiroshima_new_one_line_wording_is_read():
    c = _single("pref_hiroshima-1", _fx("w006_pref_hiroshima-1_live_20261031.html"))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, *HIROSHIMA_FIELDS) == {
        "species": "dog", "management_no": "1HD20260244", "breed": "ビーグル風", "age": "推定9歳", "sex": "雌",
        "shelter_date": "令和8年10月30日", "location": "世羅郡世羅町", "note": "搬入時首輪を着用していませんでした。",
        "image_url": "https://www.pref.hiroshima.lg.jp/uploaded/image/511929.jpg"}


def test_hiroshima_old_two_line_wording_is_read_as_before():
    # 10/24 保存（掲載日 10/20）。直す前も後も同じ 1 頭
    c = _single("pref_hiroshima-1", _fx("w006_pref_hiroshima-1_last_ok_20261024.html"))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, *HIROSHIMA_FIELDS) == {
        "species": "dog", "management_no": "1HD20260229", "breed": "雑種", "age": "推定5歳", "sex": "雄",
        "shelter_date": "令和8年10月9日", "location": "廿日市市原付近", "note": None,
        "image_url": "https://www.pref.hiroshima.lg.jp/uploaded/image/510403.jpg"}


def test_hiroshima_returned_dog_in_the_new_wording_is_not_listed():
    html = _swap(_fx("w006_pref_hiroshima-1_live_20261031.html"),
                 "搬入時首輪を着用していませんでした。", "搬入時首輪を着用していませんでした。飼い主さんに返還されました。")
    assert "返還されました" in _text(html)
    assert _res(_single("pref_hiroshima-1", html)).animals == []


# --- 長野市 保護情報（city_nagano-2） --------------------------------------------------------------------------------
# 10/30 まで動物の節だった位置が、0 頭の日は h2「現在、迷い犬や負傷動物等は保護していません」1 つに置き換わった（前後の案内と「ご協力ください」は同じ）。
# 今の empty_text 3 本（迷い犬は収容していません・迷い犬・負傷猫などはいません・迷い犬、負傷動物は保護していません）のどれにも当たらず failed だった。
NAGANO_ZERO = "迷い犬や負傷動物等は保護していません"


def test_nagano_new_zero_heading_confirms_zero():
    c = _single("city_nagano-2", _fx("w006_city_nagano-2_zero_20261031.html"))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "empty_text"


def test_nagano_zero_heading_gone_is_not_zero():
    changed = _swap(_fx("w006_city_nagano-2_zero_20261031.html"), NAGANO_ZERO, "お知らせ")
    assert NAGANO_ZERO not in _text(changed)
    c = _single("city_nagano-2", changed)
    assert c.status == "failed" and _res(c).animals == []


def test_nagano_injured_cat_day_is_read_as_before_and_never_has_the_zero_heading():
    # 10/30 0:49 保存（更新日 10/22）の負傷猫 第13号。子がいる日（この日・2025-09 の迷い犬 第7号）のページに 0 頭の h2 は無い
    html = _fx("w006_city_nagano-2_last_ok_20261030.html")
    assert NAGANO_ZERO not in _text(html) and NAGANO_ZERO not in _text(_fx("t519v_g5_nagano2_20250909.html"))
    c = _single("city_nagano-2", html)
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "management_no", "breed", "color", "sex", "age", "size", "shelter_date", "location", "image_url") == {
        "species": "cat", "management_no": "第13号", "breed": "雑種", "color": "キジ白", "sex": "オス(去勢手術済み)", "age": "5才",
        "size": "大", "shelter_date": "令和8年10月19日14時10分", "location": "長野市浅川西条浅川西条団地ちびっこ広場付近",
        "image_url": "https://www.city.nagano.nagano.jp/images/2514/08213pica02.jpg"}


# --- 滋賀県動物保護管理センター（spec_sapca） ----------------------------------------------------------------------------
# 10/31 の一覧に残ったのは 22137 の 1 頭で、その個体ページに「飼い主さんのところへ 戻りました」。status の除外語で全行除外になるが、
# rows: body は表の中に無く見出しを読めず、rows が単一段で empty_container も無かったので 0 頭の根拠が取れず ambiguous_empty だった
# （まだいる子が 0 頭になる日に毎回。10/10〜13・10/15〜20 も同じ）。済みの個体ページは div.sumidetail の直下に項目表 table.dogcat がある
# （まだいる子のページは class の無い div の直下）。それを全行除外の 0 頭の根拠にする。
SAPCA_LIST = "https://www.sapca.jp/lost"
SAPCA_22137 = "https://www.sapca.jp/lost/22137.html"
SAPCA_22078 = "https://www.sapca.jp/lost/22078.html"


def _sapca_zero(returned: str) -> Collected:
    return _collect("spec_sapca", {SAPCA_LIST: _fx("w006_spec_sapca_list_20261031.html"), SAPCA_22137: returned})


def test_sapca_only_a_returned_dog_left_is_zero_by_the_done_frame():
    c = _sapca_zero(_fx("w006_spec_sapca_22137_returned_20261031.html"))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "all_excluded+container"
    assert [d.reason for d in _res(c).dropped] == ["除外語（status: 戻りました）"]


def test_sapca_only_a_dead_dog_left_is_zero_by_the_done_frame():
    # 22078 は「残念ながら 10/27 に 亡くなりました」。一覧の 1 件がこのページだった日として読ませる
    c = _sapca_zero(_fx("w006_spec_sapca_22078_died_20261030.html"))
    assert c.status == "empty", c.error
    assert [d.reason for d in _res(c).dropped] == ["除外語（status: 亡くなりました）"]


def test_sapca_done_frame_renamed_is_not_zero():
    returned = _fx("w006_spec_sapca_22137_returned_20261031.html")
    for broken in (_swap(returned, "sumidetail", "donedetail"), _swap(returned, 'class="dogcat"', 'class="dogcat2"')):
        c = _sapca_zero(broken)
        assert c.status == "ambiguous_empty" and _res(c).animals == []


def test_sapca_a_status_word_in_a_fixed_area_of_a_live_dog_page_is_not_zero():
    # まだいる子のページ（枠が無い）のメニューに「戻りました」が出ても、済みの枠が無いので 0 頭にしない
    active = _swap(_fx("w006_spec_sapca_22137_active_20261030.html"), '<ul class="mainmenu">', '<ul class="mainmenu"><li>戻りました</li>', 1)
    assert "戻りました" in _text(active)
    c = _sapca_zero(active)
    assert c.status == "ambiguous_empty" and _res(c).animals == []


def test_sapca_a_live_dog_and_a_dead_dog_day_keeps_the_live_dog():
    # 10/30 の保存（一覧 4 件のうち 22137 はまだいる子、22078 は亡くなった子）から 2 件。頭数・項目は直す前と同じ
    index = ('<ul class="list"><li><a href="https://www.sapca.jp/lost/22137.html">22137</a></li>'
             '<li><a href="https://www.sapca.jp/lost/22078.html">22078</a></li></ul>')
    c = _collect("spec_sapca", {SAPCA_LIST: index, SAPCA_22137: _fx("w006_spec_sapca_22137_active_20261030.html"),
                                SAPCA_22078: _fx("w006_spec_sapca_22078_died_20261030.html")})
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "shelter_date", "location", "breed", "sex", "color", "size", "note") == {
        "species": None, "shelter_date": "10月29日(木)", "location": "愛荘町安孫子", "breed": "雑種", "sex": "オス",
        "color": "茶", "size": "中", "note": None}
    assert [d.reason for d in _res(c).dropped] == ["除外語（status: 亡くなりました）"]


# --- 岩手県 一関保健所 迷子（pref_iwate_ichinoseki） ----------------------------------------------------------------------
# 10/29 更新のページは R8-2-6 の 1 件だけで、備考に「猫は発見時、既に死亡していました」。row_filter（note に「死亡」）で全行除外になるが、
# 行は p で表が無く見出しを読めず、rows が単一段で empty_container も無いので ambiguous_empty だった（生きた子がいない日に毎回）。
# 行の p の親（本文の枠 div#voice）を全行除外の 0 頭の根拠にする。あわせて、R8-2-6 から書き方が「収容場所：」に変わったので location の label に足す。
ICHI_INDEX = "https://www.pref.iwate.jp/kennan/ichi_hoken/doubutsu/index.html"
ICHI_STRAY = "https://www.pref.iwate.jp/kennan/ichi_hoken/doubutsu/1013648.html"
ICHI_INDEX_HTML = f'<main><h1>一関保健所　動物情報</h1><ul><li><a href="{ICHI_STRAY}">一関保健所　保護動物情報</a></li></ul></main>'
ICHI_DEATH = "猫は発見時、既に死亡していました。"


def _ichinoseki(stray: str) -> Collected:
    return _collect("pref_iwate_ichinoseki", {ICHI_INDEX: ICHI_INDEX_HTML, ICHI_STRAY: stray})


def test_ichinoseki_only_a_dead_animal_left_is_zero_by_the_body_frame():
    c = _ichinoseki(_fx("w006_pref_iwate_ichinoseki_dead_only_20261031.html"))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "all_excluded+container"
    (d,) = _res(c).dropped
    assert d.reason == "除外語（note: 死亡）" and d.text.startswith("管理番号：R8-2-6")


def test_ichinoseki_body_frame_renamed_is_not_zero():
    html = _swap(_fx("w006_pref_iwate_ichinoseki_dead_only_20261031.html"), 'id="voice"', 'id="voice2"')
    c = _ichinoseki(html)
    assert c.status == "ambiguous_empty" and _res(c).animals == []


def test_ichinoseki_a_live_kitten_and_a_dead_cat_day_keeps_the_live_kitten():
    # 10/29 朝の保存（ページの更新日 10/26）。生きている 103-12 と、死亡の R8-2-6。直す前も後も 1 頭
    c = _ichinoseki(_fx("w006_pref_iwate_ichinoseki_alive_and_dead_20261029.html"))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "species", "management_no", "shelter_date", "location", "size", "breed", "sex", "age", "color") == {
        "species": "cat", "management_no": "103-12", "shelter_date": "2026.10.23", "location": "一関市宮坂町地内",
        "size": "子猫", "breed": "雑種", "sex": "オス", "age": "推定3ヶ月", "color": "黒"}
    (d,) = _res(c).dropped
    assert d.reason == "除外語（note: 死亡）" and d.text.startswith("管理番号：R8-2-6")


def test_ichinoseki_location_is_read_in_the_new_wording_too():
    # 今日のページから死亡の文だけ消した合成。「収容場所：」の書き方でも location が取れる（以前は null）。生きた子がこの書き方で載った日は未確認
    c = _ichinoseki(_swap(_fx("w006_pref_iwate_ichinoseki_dead_only_20261031.html"), ICHI_DEATH, ""))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "management_no", "shelter_date", "location", "sex", "species") == {
        "management_no": "R8-2-6", "shelter_date": "令和8年10月21日", "location": "一関市中里南白幡", "sex": "メス", "species": None}


# --- いわき市保健所（city_iwaki-1） ----------------------------------------------------------------------------------------
# 犬の節の頭数の文から句点が消えた（10/27 更新の「現在、２頭です」、10/29 更新の 0 頭の日は「現在、０頭です」＋項目名だけの空の雛形「No. 捕獲月日 …」）。
# empty_text は句点つき「０頭です。 No. 捕獲月日」だけで当たらず、雛形 2 表は写真・番号・日付が無いので捨てて failed（行 2・捨てた 2）。猫の節は今も「０頭です。」。
IWAKI_ZERO = "０頭です No. 捕獲月日"


def test_iwaki_dog_zero_sentence_without_the_full_stop_confirms_zero():
    c = _single("city_iwaki-1", _fx("w006_city_iwaki-1_zero_20261031.html"))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "empty_text"
    assert len(_res(c).dropped) == 2     # 犬・猫の空の雛形の表


def test_iwaki_two_dogs_day_is_read_as_before():
    # 10/29 朝の保存（ページの更新日 10/27）。犬 2 頭（8-26・8-12）、猫は 0 頭の雛形。この日の本文に 0 頭の文字列は無い
    html = _fx("w006_city_iwaki-1_two_dogs_20261029.html")
    assert IWAKI_ZERO not in _text(html)
    c = _single("city_iwaki-1", html)
    assert c.status == "ok", c.error
    assert [_pick(a, "species", "management_no", "shelter_date", "location", "breed", "color", "sex", "size", "note")
            for a in _res(c).animals] == [
        {"species": "dog", "management_no": "8-26", "shelter_date": "10月23日", "location": "勿来町関田入田羽", "breed": "甲斐犬",
         "color": "黒", "sex": "雄", "size": "中", "note": "鎖首輪"},
        {"species": "dog", "management_no": "8-12", "shelter_date": "8月12日", "location": "遠野町入遠野字越台", "breed": "雑種",
         "color": "薄茶白", "sex": "雄", "size": "中", "note": "赤革首輪"}]


def test_iwaki_dog_count_not_zero_beside_an_empty_template_is_not_zero():
    # 犬の頭数の文が 2 頭なのに雛形しか読めない日。猫の節の「０頭です。 No. 保護月日」には当たらない
    changed = _swap(_fx("w006_city_iwaki-1_zero_20261031.html"), "<p>現在、０頭です</p>", "<p>現在、２頭です</p>", 1)
    assert "現在、２頭です No. 捕獲月日" in _text(changed)
    c = _single("city_iwaki-1", changed)
    assert c.status == "failed" and _res(c).animals == []


def test_iwaki_zero_template_with_a_year_number_and_no_full_stop_is_not_zero():
    # 句点なしで「No.」に年の番号の残り（８-）がある雛形は見ていないので足さない（読めなかった扱い＝通知に出る側）
    html = _fx("w006_city_iwaki-1_zero_20261031.html")
    broken, n = re.subn(r"(No\.\s*</td>\s*<td[^>]*>\s*<p>)&nbsp;(</p>)", r"\1８-\2", html, count=1)
    assert n == 1 and "No. ８- 捕獲月日" in _text(broken)
    c = _single("city_iwaki-1", broken)
    assert c.status == "failed" and _res(c).animals == []


# --- 熊本市 迷子猫（city_kumamoto-2） ----------------------------------------------------------------------------------------
# 0 頭の日は「いません」等の文言が出ず、div.kijiArea（「全N件」と記事の並び）ごと消える（10/26〜30 は follow_all が 0 件で failed。10/31・11/01 の実ページで
# 構造を確認。10/25 の最後の 2 記事 kiji00373112・kiji00373021 は 404）。見出し「迷子猫を保護しています」はサイト共通のメニューにも毎ページ出るので
# empty_text に使えず、本文（#cont_body）の h1.classTitle を枠にした empty_absent で 0 頭を確定する。器・記事リンク・wideMenu 内のリンクが 1 つでもあれば 0 頭にしない。
KUMAMOTO_LIST = "https://www.city.kumamoto.jp/doubutuaigo/list03615.html"
KUMAMOTO_KIJI_1 = "https://www.city.kumamoto.jp/doubutuaigo/kiji00373112/index.html"
KUMAMOTO_KIJI_2 = "https://www.city.kumamoto.jp/doubutuaigo/kiji00373021/index.html"


def test_kumamoto_list_without_the_article_area_is_zero():
    c = _single("city_kumamoto-2", _fx("w006_city_kumamoto-2_zero_20261031.html"))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "empty_absent"


def test_kumamoto_two_cats_day_is_read_as_before():
    # 10/25 の保存（一覧「全2件」＋記事 2 本）。直す前も後も 2 頭で ID・項目が同じ
    c = _collect("city_kumamoto-2", {KUMAMOTO_LIST: _fx("w006_city_kumamoto-2_list_2cats_20261025.html"),
                                     KUMAMOTO_KIJI_1: _fx("w006_city_kumamoto-2_kiji00373112_20261025.html"),
                                     KUMAMOTO_KIJI_2: _fx("w006_city_kumamoto-2_kiji00373021_20261025.html")})
    assert c.status == "ok", c.error
    assert [_pick(a, "id", "species", "breed", "color", "sex", "age", "size", "shelter_date", "location", "note")
            for a in _res(c).animals] == [
        {"id": "d746a749a308", "species": "cat", "breed": "雑種", "color": "黒白", "sex": "オス(去勢済み)", "age": "不明", "size": "中~大",
         "shelter_date": "2026年09月30日", "location": "西区 城山下代4丁目", "note": "耳カットなし"},
        {"id": "1cb7843007c6", "species": "cat", "breed": "雑種", "color": "キジ白", "sex": "不明", "age": "1歳未満(推定)", "size": None,
         "shelter_date": "2026年9月21日午前8時頃", "location": "北区打越町(永浦橋付近、遊水池公園近く)", "note": None}]


def test_kumamoto_articles_listed_but_unreadable_is_not_zero():
    # 一覧に記事が並ぶ（kijiArea・記事リンクがある）のに記事ページを読めなかった日
    c = _collect("city_kumamoto-2", {KUMAMOTO_LIST: _fx("w006_city_kumamoto-2_list_2cats_20261025.html"),
                                     KUMAMOTO_KIJI_1: "<html><body><p>読めないページ</p></body></html>",
                                     KUMAMOTO_KIJI_2: "<html><body><p>読めないページ</p></body></html>"})
    assert c.status == "failed" and _res(c).animals == []


def test_kumamoto_broken_page_without_the_heading_frame_is_not_zero():
    # Wayback 2026-01-22 のように本文に h1 も記事も無い崩れた版（メニューには同じ文言が残る）を 0 頭にしない
    zero = _fx("w006_city_kumamoto-2_zero_20261031.html")
    assert zero.count("迷子猫を保護しています") >= 3      # 見出し・左のメニュー・パンくず
    c = _single("city_kumamoto-2", _swap(zero, '<h1 class="classTitle">', '<h1 class="otherTitle">'))
    assert c.status == "failed" and _res(c).animals == []


def test_kumamoto_empty_article_container_is_not_zero():
    zero = _fx("w006_city_kumamoto-2_zero_20261031.html")
    c = _single("city_kumamoto-2", _swap(zero, '<div class="newArea">', '<div class="newArea"><div class="kijiArea"></div>', 1))
    assert c.status == "failed" and _res(c).animals == []


def test_kumamoto_parent_category_with_only_sub_category_links_is_not_zero():
    # 同じ見出しで下位分類へのリンクだけを並べる親分類（list03597）が返った日
    zero = _fx("w006_city_kumamoto-2_zero_20261031.html")
    links = '<ul><li><a href="//www.city.kumamoto.jp/doubutuaigo/list03616.html">下位分類</a></li></ul>'
    c = _single("city_kumamoto-2", _swap(zero, '<div class="newArea">', links + '<div class="newArea">', 1))
    assert c.status == "failed" and _res(c).animals == []


# --- 群馬県 東部（pref_gunma-2） -------------------------------------------------------------------------------------------
# 「収容情報」の節に担当者が手書きする 0 頭の文が「現在、保管期間中の動物はおりません。」になった（10/28 から行 0 で failed。保存して確かめたのは 10/31・11/01）。
# 今の empty_text 3 本（保管期間中の犬はおりません・負傷猫はいません・猫はいません）は「動物はおりません」に当たらない。Wayback 2025-10-09・2026-05-17 は
# 「現在、保護している動物はいません。」だった。どちらも子がいる日（10/27 の管理番号 26-123）には出ない。
GUNMA_ZERO = ("保管期間中の動物はおりません", "保護している動物はいません")


@pytest.mark.parametrize("name", ["w006_pref_gunma-2_zero_20261031.html", "w006_pref_gunma-2_zero_wb20251009.html"])
def test_gunma_zero_sentence_in_either_wording_confirms_zero(name):
    c = _single("pref_gunma-2", _fx(name))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "empty_text"


def test_gunma_zero_sentence_gone_is_not_zero():
    changed = _swap(_fx("w006_pref_gunma-2_zero_20261031.html"), "現在、保管期間中の動物はおりません。", "お知らせ")
    assert not [s for s in GUNMA_ZERO if s in _text(changed)]
    c = _single("pref_gunma-2", changed)
    assert c.status == "failed" and _res(c).animals == []


def test_gunma_one_dog_day_is_read_as_before_and_never_has_the_zero_sentences():
    html = _fx("w006_pref_gunma-2_1dog_20261027.html")
    assert not [s for s in GUNMA_ZERO if s in _text(html)]
    c = _single("pref_gunma-2", html)
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "id", "species", "management_no", "location") == {
        "id": "3b1a27fdd14c", "species": "dog", "management_no": "26-123", "location": "太田市安良岡町"}


# --- 前橋市（city_maebashi） -----------------------------------------------------------------------------------------------
# 0 頭の日は表に 5 セルとも空の雛形行が 1 行残り（写真・管理番号が無いので捨てる）、表の上の文が「現在、前橋市保健所で収容(保護)している犬はいません。」になる
# （子がいる日は「…している犬は1頭です。」）。今の empty_text「現在いません」「現在収容している犬はいません」はこのページに一度も出ていない死文だったので、
# 実際の文に入れ替えた。括弧は半角のまま照合する（全角に変わった日は failed で通知される）。
MAEBASHI_ZERO = "収容(保護)している犬はいません"


def test_maebashi_zero_sentence_with_a_blank_template_row_confirms_zero():
    c = _single("city_maebashi", _fx("w006_city_maebashi_zero_20261031.html"))
    assert c.status == "empty", c.error
    assert _res(c).animals == [] and _res(c).empty_evidence == "empty_text"
    assert len(_res(c).dropped) == 1      # 5 セルとも空の雛形行


def test_maebashi_one_dog_day_is_read_as_before_and_never_has_the_zero_sentence():
    html = _fx("w006_city_maebashi_1dog_20261030.html")
    assert MAEBASHI_ZERO not in _text(html) and "犬は1頭です" in _text(html)
    c = _single("city_maebashi", html)
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert _pick(a, "id", "species", "management_no", "shelter_date", "location", "breed", "sex", "image_url") == {
        "id": "fa060783dafb", "species": "dog", "management_no": "2026-10-02", "shelter_date": "2026年10月13日", "location": "粕川町女渕",
        "breed": "雑種", "sex": "メス",
        "image_url": "https://www.city.maebashi.gunma.jp/material/images/group/43/vga2026-10-13kasukawamachionabuchi1.jpg"}


def test_maebashi_count_sentence_with_only_a_blank_row_is_not_zero():
    # 文が「犬は1頭です」なのに表が雛形行だけ（表が読めない日）は 0 頭にしない
    zero = _fx("w006_city_maebashi_zero_20261031.html")
    assert MAEBASHI_ZERO in _text(zero)
    changed = _swap(zero, "犬はいません", "犬は1頭です")      # 本文の p と og:description の 2 か所
    assert MAEBASHI_ZERO not in _text(changed) and "犬は1頭です" in _text(changed)
    c = _single("city_maebashi", changed)
    assert c.status == "failed" and _res(c).animals == []


def test_maebashi_full_width_parentheses_are_not_zero():
    zero = _fx("w006_city_maebashi_zero_20261031.html")
    changed = _swap(zero, "収容(保護)している犬はいません", "収容（保護）している犬はいません")
    assert "収容（保護）している犬はいません" in _text(changed)
    c = _single("city_maebashi", changed)
    assert c.status == "failed" and _res(c).animals == []
