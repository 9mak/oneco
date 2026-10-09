"""T519 G4: 埼玉県（保健所 13・動物指導センター 2・個人保護 8・譲渡 3）のレシピ（ネットワークなし）。

fixture は実ページの本文（div#tmp_contents）。2026-10-05〜06 の取得。県のページは職員が手で更新する作りで、
0 頭の日は空欄の雛形 table（管理番号「2026-」・収容日「2026年月日」等）が残り、新着情報に「収容犬情報はありません」と書く。
- 動物が載っていた日: 本庄（1 頭・写真 2 枚）・熊谷（1 頭・写真 3 枚）・幸手（1 頭＋お問い合わせの table）・センター南支所の収容猫（写真なし）・個人保護猫 南支所（写真は表の中）・譲渡 3 ページ
- 0 頭の日: 上記以外の保健所・個人保護犬・センター本所
動物が載った日の保存ページが無い slug（個人保護犬 6 本など）は、雛形の空欄を埋めた書き換えで確かめる。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
IMG = "https://www.pref.saitama.lg.jp/images/"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(slug: str, html: str):
    src = _source(slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return build(src, recipe, [doc])


def _fixture(slug: str) -> str:
    return (FIX / f"t519_{slug}.html").read_text(encoding="utf-8")


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def _fill(html: str, values: dict[str, str], table: int = 0) -> str:
    """表（table）の見出しセルの隣のセルに値を入れる。雛形の空欄を埋めて「動物が載った日」を作る。"""
    soup = BeautifulSoup(html, "lxml")
    t = [x for x in soup.select("table") if "番号" in x.get_text()][table]
    for tr in t.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        head = cells[0].get_text(strip=True)
        for label, value in values.items():
            if label in head:
                cells[1].clear()
                cells[1].append(value)
    return str(soup)


HOKEN = ["nanbu", "asaka", "kasukabe", "souka", "konosu", "higashimatsuyama", "sakado", "sayama", "kazo", "satte", "kumagaya", "honjo", "chichibu"]
HOKEN_EMPTY = [k for k in HOKEN if k not in ("satte", "kumagaya", "honjo")]


# --- 台帳 -------------------------------------------------------------------------------------------------------
def test_registry_has_26_saitama_pages_with_unique_slugs_and_urls():
    srcs = [s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug.startswith("pref_saitama")]
    assert len(srcs) == 26
    assert len({s.slug for s in srcs}) == 26 and len({s.url for s in srcs}) == 26
    assert all(s.mode == "recipe" and s.enabled and s.phone and s.prefecture == "埼玉県" for s in srcs)
    kinds = {}
    for s in srcs:
        kinds.setdefault(s.kind, []).append(s.slug)
    assert len(kinds["adoption"]) == 3 and len(kinds["sheltered"]) == 23


# --- 保健所 収容犬（13 か所は同じ作り） ----------------------------------------------------------------------------
def test_hoken_zero_days_are_zero_not_failed_and_templates_are_not_animals():
    for k in HOKEN_EMPTY:
        res = _run(f"pref_saitama_{k}", _fixture(f"saitama_{k}"))
        assert res.animals == [], k
        assert res.empty_confirmed, k


def test_hoken_honjo_reads_the_animal_and_both_photos_come_from_the_paragraph_before_the_table():
    res = _run("pref_saitama_honjo", _fixture("saitama_honjo"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "species", "management_no", "shelter_date", "location", "size", "breed", "sex", "age", "color", "note") == {
        "species": "dog", "management_no": "2026-13", "shelter_date": "令和8年10月5日", "location": "児玉郡神川町二ノ宮", "size": "中",
        "breed": "フレンチ・ブルドッグ", "sex": "めす", "age": "7歳以上", "color": "灰黒", "note": None}
    assert a["image_url"] == IMG + "146677/img_2552.jpg"


def test_hoken_kumagaya_takes_the_first_photo_not_the_new_gif_in_the_heading():
    res = _run("pref_saitama_kumagaya", _fixture("saitama_kumagaya"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["image_url"] == IMG + "146348/p9280007.jpg"
    assert _pick(a, "management_no", "shelter_date", "location", "color", "age", "note") == {
        "management_no": "2026-19", "shelter_date": "令和8年9月28日", "location": "深谷市武蔵野", "color": "白", "age": "老犬",
        "note": "令和8年9月27日午後6時30分頃 寄居警察署保護"}


def test_hoken_satte_inquiry_table_with_a_phone_number_is_not_an_animal():
    # 幸手の 2 つ目の table はお問い合わせ欄（電話 0480-42-1101）。管理番号の無い table は行にしない
    res = _run("pref_saitama_satte", _fixture("saitama_satte"))
    assert [a["management_no"] for a in res.animals] == ["2026-06"]
    assert res.animals[0]["location"] == "宮代町和戸" and res.animals[0]["image_url"] == IMG + "273685/dsc02630.jpg"


def test_hoken_two_animals_each_keep_their_own_photo():
    html = _fixture("saitama_honjo")
    start = html.index("<h2><img")
    end = html.index("</table>", start) + len("</table>")
    block = html[start:end]
    second = block.replace("2026-13", "2026-14").replace("img_2552.jpg", "x14a.jpg").replace("img_2551.jpg", "x14b.jpg").replace("令和8年10月5日", "令和8年10月6日")
    res = _run("pref_saitama_honjo", html.replace(block, block + second))
    assert [(a["management_no"], a["image_url"].rsplit("/", 1)[1]) for a in res.animals] == [("2026-13", "img_2552.jpg"), ("2026-14", "x14a.jpg")]


def test_hoken_animal_without_photo_is_still_listed():
    # 負傷・凶暴で写真を載せない子（県のページの注意書き）
    html = _fixture("saitama_honjo")
    soup = BeautifulSoup(html, "lxml")
    for img in soup.select("img[src*='/images/146677/']"):
        img.decompose()
    res = _run("pref_saitama_honjo", str(soup))
    assert len(res.animals) == 1 and res.animals[0]["image_url"] is None and res.animals[0]["management_no"] == "2026-13"


def test_hoken_zero_day_news_line_gone_is_failed_not_zero():
    # 新着情報の文言が無く動物も取れない日（構造が変わった日）は 0 頭に見せない
    html = _fixture("saitama_souka").replace("現在収容犬情報はありません。", "調整中")
    res = _run("pref_saitama_souka", html)
    assert res.animals == [] and not res.empty_confirmed


def test_hoken_partly_filled_template_is_not_an_animal():
    # 東松山の雛形の 1 つは「収容場所 比企郡」だけ埋まっている（番号も日付も写真も無い）
    res = _run("pref_saitama_higashimatsuyama", _fixture("saitama_higashimatsuyama"))
    assert res.animals == []


# --- 動物指導センター 収容猫等 -----------------------------------------------------------------------------------
def test_center_minami_reads_the_cat_without_a_photo():
    res = _run("pref_saitama_center_minami", _fixture("saitama_center_minami"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "species", "management_no", "shelter_date", "location", "breed", "color", "sex", "age", "image_url") == {
        "species": "cat", "management_no": "2026-79", "shelter_date": "令和8年10月5日", "location": "北本市古市場", "breed": "雑種",
        "color": "キジ白", "sex": "オス(未去勢)", "age": "7~10歳", "image_url": None}
    assert "写真の掲載はありません" in a["note"]


def test_center_honsho_zero_day_template_with_2026_H_number_is_not_an_animal():
    res = _run("pref_saitama_center_honsho", _fixture("saitama_center_honsho"))
    assert res.animals == [] and res.empty_confirmed


def test_center_honsho_filled_template_reads_h_numbers_and_species_from_the_table():
    html = _fill(_fixture("saitama_center_honsho"), {"管理番号": "2026-H-03", "収容日": "令和8年10月6日", "収容場所": "熊谷市", "種類": "雑種", "毛色": "三毛"})
    res = _run("pref_saitama_center_honsho", html)
    assert len(res.animals) == 1
    assert _pick(res.animals[0], "species", "management_no", "shelter_date", "breed", "color") == {
        "species": "cat", "management_no": "2026-H-03", "shelter_date": "令和8年10月6日", "breed": "雑種", "color": "三毛"}


# --- 個人保護 --------------------------------------------------------------------------------------------------
def test_kojin_dog_zero_days():
    for k in ["nanbu", "asaka", "chichibu", "kazo", "kumagaya", "sakado"]:
        res = _run(f"pref_saitama_{k}-2", _fixture(f"saitama_{k}-2"))
        assert res.animals == [] and res.empty_confirmed, k


def test_kojin_dog_filled_template_is_read():
    # 熊谷の個人保護犬の雛形（番号「2026-」・保護日「2026年月日」）に 1 頭分を埋めた日
    html = _fill(_fixture("saitama_kumagaya-2"), {"管理番号": "2026-3", "保護日": "2026年10月1日", "保護場所": "深谷市", "種類": "柴", "性別": "オス", "毛色": "茶"})
    res = _run("pref_saitama_kumagaya-2", html)
    assert len(res.animals) == 1
    assert _pick(res.animals[0], "species", "kind", "management_no", "shelter_date", "location", "breed", "sex", "color") == {
        "species": "dog", "kind": "sheltered", "management_no": "2026-3", "shelter_date": "2026年10月1日", "location": "深谷市", "breed": "柴", "sex": "オス", "color": "茶"}


def test_kojin_cat_minami_photos_are_inside_the_table_and_first_one_is_taken():
    res = _run("pref_saitama_center_minami-2", _fixture("saitama_center_minami-2"))
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["image_url"] == IMG + "146427/benngaru1.jpg"
    assert _pick(a, "species", "management_no", "shelter_date", "location", "breed", "sex", "age", "color") == {
        "species": "cat", "management_no": "2026-1061", "shelter_date": "令和8年9月10日", "location": "草加市青柳", "breed": "ベンガル",
        "sex": "メス(不妊手術不明)", "age": "2~3才", "color": "ブラウン"}


def test_kojin_cat_honsho_zero_day_uses_the_uketsuke_number_label():
    res = _run("pref_saitama_center_honsho-2", _fixture("saitama_center_honsho-2"))
    assert res.animals == [] and res.empty_confirmed
    html = _fill(_fixture("saitama_center_honsho-2"), {"受付番号": "2026-5", "保護日": "令和8年10月6日", "保護場所": "行田市", "種類": "雑種"})
    res = _run("pref_saitama_center_honsho-2", html)
    assert [a["management_no"] for a in res.animals] == ["2026-5"]


# --- 譲渡 -------------------------------------------------------------------------------------------------------
def test_joto_inu_five_dogs_with_names_from_the_h3_and_photos():
    res = _run("pref_saitama_joto_inu", _fixture("saitama_joto_inu"))
    assert [(a["management_no"], a["name"]) for a in res.animals] == [
        ("D2026-05", "ロッキー"), ("D2026-06", "ぽんた"), ("D2026-07", "アッシュ"), ("D2026-08", "モカ"), ("南D2026-02", "もっくん")]
    assert all(a["species"] == "dog" and a["kind"] == "adoption" for a in res.animals)
    assert res.animals[0]["image_url"] == IMG + "21445/rokki-.jpeg"
    assert _pick(res.animals[4], "breed", "sex", "age", "color") == {"breed": "雑種", "sex": "オス(去勢手術未実施)", "age": "7歳", "color": "茶"}


def test_joto_inu_decided_dog_is_dropped():
    html = _fixture("saitama_joto_inu").replace("D2026-06</td>", "D2026-06<p>譲渡されました！</p></td>", 1)
    assert "D2026-06<p>譲渡" in html
    res = _run("pref_saitama_joto_inu", html)
    assert [a["name"] for a in res.animals] == ["ロッキー", "アッシュ", "モカ", "もっくん"]


def test_joto_neko_honsho_two_open_cats_and_the_decided_one_is_dropped():
    res = _run("pref_saitama_joto_neko_honsho", _fixture("saitama_joto_neko_honsho"))
    assert [(a["management_no"], a["name"]) for a in res.animals] == [("2026-C-008", "ハッチ"), ("2026-C-007", "ソウ")]
    assert res.animals[0]["image_url"] == IMG + "21418/hacchi1.jpg"
    assert _pick(res.animals[0], "species", "breed", "sex", "color", "age") == {
        "species": "cat", "breed": "雑種", "sex": "オス(去勢手術 未実施)", "color": "白黒", "age": "2才6か月程度"}


def test_joto_neko_minami_only_a_decided_cat_is_zero():
    res = _run("pref_saitama_joto_neko_minami", _fixture("saitama_joto_neko_minami"))
    assert res.animals == [] and res.empty_confirmed


def test_joto_neko_minami_new_cat_without_the_decided_mark_is_read_with_the_provisional_name():
    html = _fixture("saitama_joto_neko_minami").replace("譲渡されました！</span>", "募集中です</span>")
    res = _run("pref_saitama_joto_neko_minami", html)
    assert len(res.animals) == 1
    a = res.animals[0]
    assert _pick(a, "management_no", "name", "color", "age") == {"management_no": "南2026-C67", "name": "くろまめ", "color": "黒(短カギ尾)", "age": "推定1歳"}
    assert a["image_url"] == IMG + "21438/img_1595.jpg"
