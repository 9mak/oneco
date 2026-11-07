"""W006（2026-11-07）全ページ監査 A 班: 監査の指摘を実ページで確かめて直した掲載元（ネットワークなし）。

fixture は 2026-11-07 に保存した実ページ（script・style を落とした。w006a_*）。沖縄県の個体ページの「保護者」（個人の姓）は 〇〇 に伏せた。
香川の PDF は、エンジンと同じ pdfplumber にかけた表を JSON にした（w006a_sanuki_kagawa_*.json）。監査が見た版（1104dog.pdf）は
公開が終わって取れないので、「譲渡済の重ね書きが続きの行にだけある」形は今日の版の行の形に合わせた合成行で確かめる（試験の中にそう書く）。
- 岡山市: 猫の一覧（保護猫情報一覧）は個別ページより遅れて更新される恐れがあり、いない猫を載せうるので辿らない（猫は個別ページだけ。犬の ID は不変）
- 松本市 犬: 見出しの「募集を停止しています」の子は募集していないので載せない（監査の指摘どおり）
- 八戸市: 指摘は誤り（印は名前の前に置かれる。アサリは募集中）
- 香川: 譲渡済の重ね書きが表の続きの行にだけある子を載せない
- 鹿児島市: 同じ管理番号が上下に 2 度載る（上が最新）。下の古い方を載せない
- 横浜市 収容犬・その他: 見出し行（th だけの tr）を行にしない
- 沖縄県 迷い込み: 「保護は出来なかった」（漢字の出来）も保護していない目撃として捨てる
- 福岡県動物愛護協会 保健所収容犬: 個体ページを辿って性別・毛色・大きさ・年齢・犬種を読む
- ワンニャピアあきた: 一覧が 2 ページあるので次のページも辿る
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import Result, build
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _collect(slug: str, pages: dict[str, str | bytes]) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher(pages))


def _single(slug: str, html: str) -> Collected:
    return _collect(slug, {SOURCES[slug].url: html})


def _res(c: Collected) -> Result:
    assert c.result is not None, c.error
    return c.result


def _swap(html: str, old: str, new: str) -> str:
    assert old in html, old
    return html.replace(old, new)


# --- 岡山市 -------------------------------------------------------------------------------------------------------
OKAYAMA = SOURCES["city_okayama"]
OKA_DOG = "https://www.city.okayama.jp/kurashi/0000060648.html"
def _okayama() -> Collected:
    return _collect("city_okayama", {
        OKAYAMA.url: _fx("w006a_city_okayama_index_20261107.html"),
        OKA_DOG: _fx("w006a_city_okayama_dog_20261107.html"),
    })   # 保護猫情報一覧・保護犬情報一覧は辿らない（辿ると FakeFetcher に無い URL で失敗する）


def test_okayama_does_not_follow_the_cat_list_and_gives_only_the_dog_page():
    c = _okayama()
    assert c.status == "ok", c.error
    assert [a["management_no"] for a in _res(c).animals] == ["1D2026065"]


def test_okayama_dog_keeps_its_id():
    by_no = {a["management_no"]: a for a in _res(_okayama()).animals}
    assert by_no["1D2026065"]["id"] == "e9e4438928a5"
    assert by_no["1D2026065"]["species"] == "dog" and by_no["1D2026065"]["shelter_date"] == "令和8年11月4日"



# --- 松本市 犬 ----------------------------------------------------------------------------------------------------
def test_matsumoto_dogs_with_stopped_recruitment_are_not_listed():
    c = _single("city_matsumoto-4", _fx("w006a_city_matsumoto-4_20261107.html"))
    # 7-3・8-1 とも見出しが「募集を停止しています」。載せない
    assert _res(c).animals == []


def test_matsumoto_dog_without_the_stop_mark_is_listed():
    html = _swap(_fx("w006a_city_matsumoto-4_20261107.html"), "保健所譲渡犬No.8-1　募集を停止しています", "保健所譲渡犬No.8-1")
    animals = {a["management_no"]: a for a in _res(_single("city_matsumoto-4", html)).animals}
    assert sorted(animals) == ["8-1"] and animals["8-1"]["note"].startswith("人懐っこく")


# --- 八戸市（指摘は誤り） -----------------------------------------------------------------------------------------
def test_hachinohe_only_asari_is_on_offer_the_mark_comes_before_the_name():
    c = _single("city_hachinohe-2", _fx("w006a_city_hachinohe-2_20261107.html"))
    assert c.status == "ok", c.error
    # 表の 2 行目（シジミ）・3 行目（ホタテ）のセルは「飼い主さんが決まりました！」から始まる。1 行目（アサリ）に印は無い
    assert [a["name"] for a in _res(c).animals] == ["アサリ"]


# --- 香川 ---------------------------------------------------------------------------------------------------------
def _sanuki(dog_extra: list[list[str]] | None = None) -> Result:
    dog = json.loads(_fx("w006a_sanuki_kagawa_dog_1107.json"))
    cat = json.loads(_fx("w006a_sanuki_kagawa_cat_1107.json"))
    if dog_extra:
        dog["pdf_tables"][2] += dog_extra
    docs = [Doc(url=f"https://x/{n}.pdf", pdf_tables=d["pdf_tables"], pdf_text=d["pdf_text"]) for n, d in (("dog", dog), ("cat", cat))]
    recipe = Recipe.load(ROOT / "recipes" / "sanuki_kagawa.yaml")
    return build(SOURCES["sanuki_kagawa"], recipe, docs)


# 監査が見た版（1104dog.pdf）の形: 本体の行は品種が「雑種」のまま、「新しい家族に迎えられました！」の重ね書きは管理番号の無い続きの行にだけある
ADOPTED_MAIN = ["８中‐D0203", "", "R8.9.1", "雑種", "", "", "", "", "", "・スタッフに美味しいご飯をもらってスクスク成 長しています"]
ADOPTED_CONT = ["", "", "", "", "", "新し黒い白家族", "に迎メスえら", "れま約し3たｋｇ！", "", ""]
NEGOTIATING_MAIN = ["８中‐D0204", "", "R8.9.1", "雑種", "", "", "", "", "", "・スタッフに美味しいご飯をもらってスクスク成 長しています"]
NEGOTIATING_CONT = ["", "", "", "", "", "望者と交渉", "黒茶白", "中でメスす。", "", ""]


def test_sanuki_dog_adopted_only_in_the_continuation_row_is_not_listed():
    res = _sanuki([ADOPTED_MAIN, ADOPTED_CONT])
    nos = [a["management_no"] for a in res.animals]
    assert "8中‐D0203" not in nos
    assert "8中‐D0205" in nos   # 交渉中の重ね書きの子は従来どおり載る


def test_sanuki_dog_under_negotiation_is_still_listed():
    # 「譲渡希望者と交渉中です」の重ね書きは決まった子ではない（これまでどおり載せる）
    res = _sanuki([NEGOTIATING_MAIN, NEGOTIATING_CONT])
    assert "8中‐D0204" in [a["management_no"] for a in res.animals]


def test_sanuki_other_animals_are_unchanged():
    base = _sanuki()
    withextra = _sanuki([ADOPTED_MAIN, ADOPTED_CONT])
    assert [a["id"] for a in base.animals] == [a["id"] for a in withextra.animals]
    assert len(base.animals) == 83


# --- 鹿児島市 -----------------------------------------------------------------------------------------------------
def test_kagoshima_the_same_management_no_listed_twice_keeps_the_top_one():
    c = _single("city_kagoshima-1", _fx("w006a_city_kagoshima-1_20261107.html"))
    assert c.status == "ok", c.error
    animals = _res(c).animals
    assert [a["management_no"] for a in animals] == ["260039", "260075", "260073"]
    top = animals[0]
    assert top["id"] == "222dcc4b6f06" and top["image_url"]
    assert "11月6日退院" not in json.dumps(top, ensure_ascii=False)   # 載せるのは項目だけ。本文は足さない
    assert any(d.reason == "同じ管理番号の行が既にある" for d in _res(c).dropped)


# --- 横浜市 -------------------------------------------------------------------------------------------------------
def test_yokohama_dogs_header_row_is_not_an_animal():
    c = _single("city_yokohama-1", _fx("w006a_city_yokohama-1_20261107.html"))
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert a["id"] == "b0a89a476dd9" and a["image_url"].endswith("C26110201.jpg")
    assert (a["breed"], a["sex"], a["color"], a["size"], a["shelter_date"]) == ("トイプードル", "オス", "茶", "小", "令和8年11月2日")


def test_yokohama_others_header_row_is_not_an_animal_when_one_is_listed():
    html = _fx("w006a_city_yokohama-3_20261107.html")
    row = ('<tr><td class="center">2026年11月6日</td><td class="center">令和8年11月5日<br>中区<br>本町</td>'
           '<td class="center"><img alt="動物の写真" src="shuyoinfo.images/X26110501.jpg"></td><td class="center">ウサギ</td>'
           '<td class="center">不明</td><td class="center">白</td><td class="center">小</td><td class="center">首輪なし</td></tr>')
    html = re.sub(r'<tr><td class="center"><p>現在、その他の動物の収容情報はありません。</p></td>.*?</tr>', row, html, count=1, flags=re.S)
    assert "X26110501" in html
    c = _single("city_yokohama-3", html)
    assert c.status == "ok", c.error
    (a,) = _res(c).animals
    assert a["image_url"].endswith("X26110501.jpg") and a["breed"] == "ウサギ"


def test_yokohama_others_zero_day_is_still_zero():
    c = _single("city_yokohama-3", _fx("w006a_city_yokohama-3_20261107.html"))
    assert c.status == "empty" and _res(c).animals == []


# --- 沖縄県 迷い込み保護犬 ----------------------------------------------------------------------------------------
def _okinawa_detail(html: str) -> Result:
    recipe = Recipe.load(ROOT / "recipes" / "aniwel_okinawa-5.yaml")
    url = "https://www.aniwel-pref.okinawa/animals/protection_view/26037"
    return build(SOURCES["aniwel_okinawa-5"], recipe, [Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_okinawa_sighting_written_with_kanji_deki_is_not_listed():
    assert _okinawa_detail(_fx("w006a_aniwel_okinawa-5_26037_20261107.html")).animals == []


def test_okinawa_sighting_written_with_hiragana_is_not_listed():
    html = _swap(_fx("w006a_aniwel_okinawa-5_26037_20261107.html"), "保護は出来なかった", "保護はできなかった")
    assert _okinawa_detail(html).animals == []


def test_okinawa_protected_dog_is_listed():
    html = _swap(_fx("w006a_aniwel_okinawa-5_26037_20261107.html"), "保護は出来なかったのですが、", "保護しました。")
    (a,) = _okinawa_detail(html).animals
    assert a["management_no"] == "2026.11.2＿No.284" or a["management_no"].endswith("No.284")


# --- 福岡県動物愛護協会 保健所収容犬 ------------------------------------------------------------------------------
ZF = SOURCES["zaidan_fukuoka_douai-1"]
ZF_BASE = "https://www.zaidan-fukuoka-douai.or.jp"
ZF_IDS = [("2bac60d9-760d-4db1-9c57-5fd21acb4e8d", "D2283"), ("a95967f6-f481-411e-a52c-9987cfa9eba1", "D2282"), ("9772df65-f205-4a91-8404-5af643124301", "D2281")]


def _fukuoka() -> Collected:
    detail = _fx("w006a_zaidan_fukuoka_douai-1_detail_20261107.html")
    pages = {ZF.url: _fx("w006a_zaidan_fukuoka_douai-1_list_20261107.html")}
    for uid, no in ZF_IDS:
        page = detail.replace(ZF_IDS[0][0], uid).replace("D2283", no)
        pages[f"{ZF_BASE}/animals/protection-detail/{uid}"] = page
    return _collect("zaidan_fukuoka_douai-1", pages)


def test_fukuoka_stray_dogs_read_the_detail_pages():
    c = _fukuoka()
    assert c.status == "ok", c.error
    a = _res(c).animals[0]
    assert (a["management_no"], a["breed"], a["sex"], a["color"], a["size"], a["age"]) == ("D2283", "ピットブル", "オス", "茶", "大型", "11歳以上")
    assert (a["shelter_date"], a["note"], a["location"]) == ("2026年11月6日", "直方市大字直方", "嘉穂・鞍手保健福祉環境事務所")
    assert a["source_url"] == f"{ZF_BASE}/animals/protection-detail/{ZF_IDS[0][0]}"


def test_fukuoka_ids_and_photos_are_the_same_as_when_read_from_the_list():
    ids = {a["management_no"]: (a["id"], a["image_url"]) for a in _res(_fukuoka()).animals}
    assert ids["D2283"] == ("6e5a039a4704", f"{ZF_BASE}/files/download/Animals/{ZF_IDS[0][0]}/image_01/title/m")
    assert ids["D2282"][0] == "e807a4a2d8be" and ids["D2281"][0] == "c626e6acccc9"


def test_fukuoka_zero_day_is_still_zero():
    html = '<html><body><h1>保健所に収容しています [犬]</h1><p>現在、掲載されている情報はありません。</p></body></html>'
    c = _single("zaidan_fukuoka_douai-1", html)
    assert c.status == "empty" and _res(c).animals == []


# --- ワンニャピアあきた -------------------------------------------------------------------------------------------
WAN = "https://wannyapia.akita.jp"


def _wannyapia(slug: str, p1: str, p2: str | None) -> Collected:
    detail = _fx("w006a_wannyapia_akita-2_detail_p2174_20261107.html")
    pages = {SOURCES[slug].url: _fx(p1)}
    texts = [_fx(p1)]
    if p2:
        pages[f"{SOURCES[slug].url}?p=2"] = _fx(p2)
        texts.append(_fx(p2))
    for n in dict.fromkeys(re.findall(r"pages/animals/p(\d+)\"", "".join(texts))):
        pages[f"{WAN}/pages/animals/p{n}"] = detail.replace("0000002174", f"{int(n):010d}")
    return _collect(slug, pages)


def test_wannyapia_cats_second_page_is_followed():
    c = _wannyapia("spec_wannyapia_akita-2", "w006a_wannyapia_akita-2_p1_20261107.html", "w006a_wannyapia_akita-2_p2_20261107.html")
    assert c.status == "ok", c.error
    urls = {a["source_url"] for a in _res(c).animals}
    assert len(urls) == 12 and f"{WAN}/pages/animals/p2113" in urls and f"{WAN}/pages/animals/p2114" in urls


def test_wannyapia_first_page_animals_keep_their_ids():
    c = _wannyapia("spec_wannyapia_akita-2", "w006a_wannyapia_akita-2_p1_20261107.html", "w006a_wannyapia_akita-2_p2_20261107.html")
    first = [a for a in _res(c).animals if a["source_url"].endswith("/p2174")]
    assert [a["id"] for a in first] == ["f7c782d40112"]


def test_wannyapia_dogs_zero_day_is_still_zero():
    c = _wannyapia("spec_wannyapia_akita-1", "w006a_wannyapia_akita-1_p1_20261107.html", None)
    assert c.status == "empty" and _res(c).animals == []
