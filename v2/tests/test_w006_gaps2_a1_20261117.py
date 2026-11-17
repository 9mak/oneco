"""W006 T640 掲載漏れ 2 回目 A-1: 福山市・水戸市・尼崎市・那覇市・宇都宮市・東大阪市の譲渡ページ（2026-11-17・ネットワークなし）。

台帳には同じ自治体の迷子・収容のページしか無く、里親募集（譲渡）のページが抜けていた。
- 福山市: 里親募集中の犬（今日 36 頭）・猫（今日 0 頭。「現在、譲渡対象の猫はいません。」は子のいる日にも…は確かめられないので文言を根拠にしない）
"""

from pathlib import Path

from bs4 import BeautifulSoup
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


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 福山市 ---------------------------------------------------------------
FUK_DOG, FUK_CAT = "city_fukuyama-3", "city_fukuyama-4"


def test_fukuyama_registry():
    for slug, species in ((FUK_DOG, "dog"), (FUK_CAT, "cat")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "広島県", slug
        assert s.species == species and s.phone == "084-970-1201" and s.address, slug
        assert s.photo == "ok", slug  # 福山市の規約は無断転載禁止のみ（T630 の規約確認）
        assert s.recipe_path.exists(), slug


def test_fukuyama_dog_today_reads_36():
    c = _run(FUK_DOG, _fx("w006_city_fukuyama-3_20261117.html"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 36 and not c.result.dropped
    first = animals[0]
    assert (first["management_no"], first["name"], first["sex"], first["breed"], first["color"], first["age"]) == (
        "1-25", "かず", "オス", "雑種", "白黒", "3才齢")
    assert first["species"] == "dog" and first["image_url"] and "1匹で保護されました" in first["note"]
    assert len({a["id"] for a in animals}) == 36 and all(a["image_url"] for a in animals)
    assert _hits(FUK_DOG, _fx("w006_city_fukuyama-3_20261117.html")) == []


def test_fukuyama_dog_other_day_in_wayback():
    html = _fx("w006_city_fukuyama-3_child_wb20260602.html")
    c = _run(FUK_DOG, html)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 15 and c.result.animals[0]["management_no"] == "1-12"
    assert _hits(FUK_DOG, html) == []


def test_fukuyama_cat_today_is_zero():
    html = _fx("w006_city_fukuyama-4_20261117.html")
    assert "現在、譲渡対象の猫はいません" in html
    assert _zero(_run(FUK_CAT, html))


def test_fukuyama_cat_zero_day_in_wayback_is_zero_without_the_sentence():
    # 2026-03 の 0 頭の日は「現在、譲渡対象の猫はいません」の文が無く表も無い → 文言でなく表の有無で 0 頭を決める
    html = _fx("w006_city_fukuyama-4_zero_wb20260314.html")
    assert "譲渡対象の猫はいません" not in html
    assert _zero(_run(FUK_CAT, html))


def test_fukuyama_cat_child_days_in_wayback_never_zero():
    for name, n, first in (("w006_city_fukuyama-4_child_wb20251113.html", 4, "フ7-11"),
                           ("w006_city_fukuyama-4_child_wb20251008.html", 9, "フ7-11")):
        html = _fx(name)
        c = _run(FUK_CAT, html)
        assert c.status == "ok", (name, c.error)
        assert len(c.result.animals) == n and c.result.animals[0]["management_no"] == first, name
        assert all(a["species"] == "cat" and a["image_url"] for a in c.result.animals), name
        assert _hits(FUK_CAT, html) == [], name


def test_fukuyama_structure_change_is_not_zero():
    html = _fx("w006_city_fukuyama-4_child_wb20251113.html").replace("里親募集の犬猫の情報", "里親募集の動物")
    assert not _zero(_run(FUK_CAT, html))
    html = _fx("w006_city_fukuyama-3_20261117.html").replace("里親募集の犬猫の情報", "里親募集の動物")
    assert not _zero(_run(FUK_DOG, html))


# --- 水戸市 ---------------------------------------------------------------
MITO_CAT, MITO_DOG = "city_mito-3", "city_mito-4"


def test_mito_registry():
    for slug, species in ((MITO_CAT, "cat"), (MITO_DOG, "dog")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "茨城県", slug
        assert s.species == species and s.phone == "029-350-3800" and s.address, slug
        assert s.photo == "ok", slug  # 水戸市の規約は無断転載禁止のみ
        assert s.recipe_path.exists(), slug


def test_mito_cat_today_reads_5_and_skips_the_adopted_one():
    html = _fx("w006_city_mito-3_20261117.html")
    assert "里親募集中の猫（子猫3頭、成猫2頭）" in html and "R8-23" in html
    c = _run(MITO_CAT, html)
    assert c.status == "ok", c.error
    got = [(a["management_no"], a["name"]) for a in c.result.animals]
    assert got == [("R8-29", "キキ"), ("R8-30", "ララ"), ("R8-20", "エーディー"), ("R6-43", "マル"), ("34", "しー")]
    assert all(a["species"] == "cat" and a["image_url"] for a in c.result.animals)
    assert c.result.animals[0]["sex"].startswith("オス") and c.result.animals[1]["sex"].startswith("メス")
    assert len({a["id"] for a in c.result.animals}) == 5  # ページの「子猫3頭、成猫2頭」と合う
    assert not any(a["name"] == "マオマオ" for a in c.result.animals)  # 「※譲渡が決まりました。」


def test_mito_cat_two_cats_in_one_table_both_read():
    # 1 つの表に 2 頭が横に並ぶ（キキ・ララ）。2 頭目が落ちず、写真がそれぞれの子の写真になる
    c = _run(MITO_CAT, _fx("w006_city_mito-3_20261117.html"))
    a, b = c.result.animals[0], c.result.animals[1]
    assert a["image_url"] != b["image_url"] and a["id"] != b["id"]
    assert "55130" in a["image_url"] and "55131" in b["image_url"]


def test_mito_cat_other_days_in_wayback():
    html = _fx("w006_city_mito-3_child_wb20260714.html")
    c = _run(MITO_CAT, html)
    assert c.status == "ok", c.error
    assert [a["name"] for a in c.result.animals] == ["マル", "しー"]  # ページの「成猫2頭」
    html = _fx("w006_city_mito-3_child_wb20260314.html")
    c = _run(MITO_CAT, html)
    assert c.status == "ok", c.error
    names = [a["name"] for a in c.result.animals]
    assert names[:3] == ["エリ", "はなお", "ロング"] and "マル" in names and "タマ" in names  # 2 頭 1 表（マル・タマ）の 2 頭目も読む
    assert any("トライアル希望" in (a["note"] or "") for a in c.result.animals)


def test_mito_dog_today_reads_one_and_skips_the_adopted_one():
    html = _fx("w006_city_mito-4_20261117.html")
    assert "里親募集中の犬（成犬1件）" in html
    c = _run(MITO_DOG, html)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1 and c.result.rows == 1  # R7-20 ごま（譲渡が決まりました）は行の段階で外れる
    a = c.result.animals[0]
    assert (a["management_no"], a["name"], a["breed"], a["color"], a["age"], a["species"]) == (
        "R7-36", "ノンタ", "雑種", "薄茶", "推定6才", "dog")
    assert a["sex"].startswith("メス") and a["image_url"]
    assert _hits(MITO_DOG, html) == []


def test_mito_dog_zero_day_in_wayback_is_zero_by_the_count_heading():
    # 0 頭の日は「里親募集中の犬（0件）」の下に、譲渡が決まった子の表だけが残る
    html = _fx("w006_city_mito-4_zero_wb20250730.html")
    assert "里親募集中の犬（0件）" in html and "譲渡が決まりました" in html
    assert _zero(_run(MITO_DOG, html))
    assert "里親募集中の犬（0件）" not in _fx("w006_city_mito-4_20261117.html")  # 子のいる日には出ない


def test_mito_zero_is_not_guessed_when_the_heading_changes():
    html = _fx("w006_city_mito-4_zero_wb20250730.html").replace("（0件）", "")
    assert not _zero(_run(MITO_DOG, html))
    soup = BeautifulSoup(_fx("w006_city_mito-3_20261117.html"), "lxml")
    # 猫の 0 頭の日の版は Wayback に無いので、今日の保存ページから譲渡が決まった子の表だけを残して犬と同じ見出し（0件）にして再現する
    for t in soup.select("div#main_body table"):
        if "譲渡が決まりました" not in t.get_text():
            t.decompose()
    for el in soup.find_all(string=lambda s: s and "里親募集中の猫（子猫3頭、成猫2頭）" in s):
        el.replace_with("里親募集中の猫（0件）")
    zero = str(soup)
    assert _zero(_run(MITO_CAT, zero))
    assert not _zero(_run(MITO_CAT, zero.replace("（0件）", "")))


# --- 尼崎市 ---------------------------------------------------------------
AMA = "city_amagasaki-2"


def test_amagasaki_registry():
    s = SOURCES[AMA]
    assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "兵庫県" and s.species == "mixed"
    assert s.phone == "06-6434-2233" and s.address and s.recipe_path.exists()
    assert s.photo == "pending"  # 尼崎市は「コンテンツの使用は事前に問い合わせ」（10/29 の見直し）。新しいページも返事が来るまで pending


def test_amagasaki_today_reads_7_cats_and_the_trial_dog():
    html = _fx("w006_city_amagasaki-2_20261117.html")
    c = _run(AMA, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    names = [a["name"] for a in animals]
    assert names[:7] == ["みど", "モカ", "あずさ", "りつ", "カヌレ", "ダイヤ", "ルル"] and names[7].startswith("レオ")
    assert [a["species"] for a in animals] == ["cat"] * 7 + ["dog"]
    assert animals[0]["sex"] == "メス" and animals[0]["color"] == "白黒" and animals[0]["age"].startswith("7歳齢")
    assert all(a["image_url"] for a in animals) and len({a["id"] for a in animals}) == 8
    assert animals[7]["breed"] == "シーズー" and "トライアル中" in animals[7]["note"]
    assert "とっても甘えん坊" in animals[0]["note"]
    assert _hits(AMA, html) == []


def test_amagasaki_other_days_in_wayback():
    c = _run(AMA, _fx("w006_city_amagasaki-2_child_wb20260920.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 10 and sum(1 for a in c.result.animals if "トライアル中" in (a["note"] or "")) == 1
    c = _run(AMA, _fx("w006_city_amagasaki-2_child_wb20260618.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 10 and sum(1 for a in c.result.animals if "トライアル中" in (a["note"] or "")) == 3


def test_amagasaki_zero_is_only_when_the_frame_is_there_and_no_animal_is():
    # 0 頭の日の版は Wayback に無い（2026-06〜11 の 3 版はいずれも子がいる）。今日の保存ページから動物の表・写真・見出し番号を消して再現する
    soup = BeautifulSoup(_fx("w006_city_amagasaki-2_20261117.html"), "lxml")
    for el in soup.select("article table.w100, article p.imagecenter, article h3"):
        el.decompose()
    zero = str(soup)
    assert _zero(_run(AMA, zero))
    # 表の class が変わった日（見出し・写真は残る）は 0 頭にしない
    broken = _fx("w006_city_amagasaki-2_20261117.html").replace('class="w100"', 'class="w90"')
    assert not _zero(_run(AMA, broken))
    # 見出しの語（枠）が変わった日も 0 頭にしない
    assert not _zero(_run(AMA, zero.replace("新しい飼い主を探している", "")))


# --- 那覇市 ---------------------------------------------------------------
NAHA = "city_naha-1"


def test_naha_registry():
    s = SOURCES[NAHA]
    assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "沖縄県" and s.species == "mixed"
    assert s.phone == "098-951-1530" and "南風原町" in s.address and s.recipe_path.exists()
    assert s.photo == "ok"  # 那覇市の規約は無断転載禁止のみ


def test_naha_today_reads_6_dogs_and_8_cats_from_the_intro_sections_only():
    html = _fx("w006_city_naha-1_20261117.html")
    c = _run(NAHA, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 14 and len({a["id"] for a in animals}) == 14 and all(a["image_url"] for a in animals)
    assert [a["species"] for a in animals] == ["dog"] * 6 + ["cat"] * 8
    names = [a["name"] for a in animals]
    assert names[:6] == ["フーガ", "平次(へいじ)", "ボーノ", "仁(じん)", "リュウ", "ラナ"]  # 全角の括弧はエンジンが半角にそろえる
    assert names[6:9] == ["ちよ", "ビジェ", "チャバ"]
    first = animals[0]
    assert (first["breed"], first["sex"], first["age"], first["size"]) == ("雑種", "オス(去勢済み)", "10歳", "約14kg")
    assert "元気で遊ぶことが大好きです" in first["note"] and "写真撮影日" not in first["note"]
    cats = animals[6:]
    assert cats[0]["breed"] is None and cats[0]["sex"] == "メス(不妊済み)"
    # 「名前：まこ（譲渡交渉中）」は載せて note に出す（トライアル中と同じ扱い）
    mako = [a for a in cats if a["name"].startswith("まこ")][0]
    assert "譲渡交渉中" in mako["note"]
    assert _hits(NAHA, html) == []


def test_naha_other_day_in_wayback_reads_5_dogs_and_6_cats():
    html = _fx("w006_city_naha-1_child_wb20260219.html")
    c = _run(NAHA, html)
    assert c.status == "ok", c.error
    assert [a["name"] for a in c.result.animals if a["species"] == "dog"] == ["ライム", "フーガ", "マルコ", "平次(へいじ)", "くるり"]
    assert len([a for a in c.result.animals if a["species"] == "cat"]) == 6
    assert _hits(NAHA, html) == []


def test_naha_zero_only_when_the_frame_is_there_and_no_animal_is():
    # 0 頭の日の版は Wayback に無い（2026-02 と今日だけ）。今日の保存ページから動物の見出し・写真を消して再現する
    soup = BeautifulSoup(_fx("w006_city_naha-1_20261117.html"), "lxml")
    for el in soup.select("div#voice h3, div#voice p.imagecenter"):
        el.decompose()
    zero = str(soup)
    assert _zero(_run(NAHA, zero))
    # 動物の見出しが h4 に変わった日（写真は残る）は 0 頭にしない
    broken = _fx("w006_city_naha-1_20261117.html").replace("<h3>", "<h4>").replace("</h3>", "</h4>")
    assert not _zero(_run(NAHA, broken))
    # 枠の見出しが変わった日も 0 頭にしない
    assert not _zero(_run(NAHA, zero.replace("譲渡に関すること", "お知らせ")))


# --- 宇都宮市 -------------------------------------------------------------
UTSU = "city_utsunomiya-2"


def test_utsunomiya_registry():
    s = SOURCES[UTSU]
    assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "栃木県" and s.species == "mixed"
    assert s.phone == "028-626-1108" and "竹林町" in s.address and s.recipe_path.exists()
    assert s.photo == "ok"  # 宇都宮市の規約は無断転載禁止のみ


def test_utsunomiya_today_reads_one_cat_and_one_dog():
    html = _fx("w006_city_utsunomiya-2_20261117.html")
    c = _run(UTSU, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["species"], a["name"], a["breed"], a["sex"], a["age"], a["size"]) for a in animals] == [
        ("cat", "のりお", "雑種", "オス", "およそ1~2才", "中"),
        ("dog", "じゃがりこ", "雑種", "オス", "1才弱", "中")]
    assert all(a["image_url"] for a in animals) and animals[0]["image_url"] != animals[1]["image_url"]
    assert "ケンカがめちゃ弱い" in animals[0]["note"] and "無駄吠えせず" in animals[1]["note"]
    assert _hits(UTSU, html) == []


def test_utsunomiya_other_days_in_wayback_with_changing_headings():
    # h3 が「譲渡猫（のりお）」「譲渡犬（愛称　ケンタ）」「譲渡猫14」「譲渡猫19・20」と日によって変わり、名前の書き方も変わる
    c = _run(UTSU, _fx("w006_city_utsunomiya-2_child_wb20260314.html"))
    assert c.status == "ok", c.error
    assert [(a["species"], a["name"]) for a in c.result.animals] == [
        ("cat", "くるん"), ("dog", "ケンタ"), ("dog", "ショウ"), ("dog", "ナトゥ")]
    assert c.result.animals[1]["breed"] == "柴犬" and c.result.animals[2]["size"].startswith("大")
    c = _run(UTSU, _fx("w006_city_utsunomiya-2_child_wb20260712.html"))
    assert c.status == "ok", c.error
    assert [(a["species"], a["name"]) for a in c.result.animals] == [("cat", "のりお"), ("dog", "ポロン")]
    c = _run(UTSU, _fx("w006_city_utsunomiya-2_child_wb20250719.html"))
    assert c.status == "ok", c.error
    assert [a["species"] for a in c.result.animals] == ["cat", "cat", "cat", "dog"]
    assert c.result.animals[2]["name"].startswith("ぷらむ") and c.result.animals[3]["name"].startswith("金太郎")
    c = _run(UTSU, _fx("w006_city_utsunomiya-2_child_wb20250623.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 5 and all(a["species"] == "cat" and a["image_url"] for a in c.result.animals)


def test_utsunomiya_zero_only_when_the_frame_is_there_and_no_animal_is():
    # 0 頭の日の版は Wayback に無い（2025-02〜2026-07 の 6 版はいずれも子がいる）。今日の保存ページから動物の見出し・写真・説明を消して再現する
    soup = BeautifulSoup(_fx("w006_city_utsunomiya-2_20261117.html"), "lxml")
    for h3 in soup.select("h3"):
        if "譲渡猫" in h3.get_text() or "譲渡犬" in h3.get_text():
            for sib in list(h3.find_next_siblings()):
                if sib.name in ("h2", "h3"):
                    break
                sib.decompose()
            h3.decompose()
    zero = str(soup)
    assert "譲渡動物情報" in zero and _zero(_run(UTSU, zero))
    # 動物の見出しが h4 に変わった日（写真は残る）は 0 頭にしない
    broken = _fx("w006_city_utsunomiya-2_20261117.html").replace("<h3>譲渡", "<h4>譲渡")
    assert not _zero(_run(UTSU, broken))
    # 枠の見出しが変わった日も 0 頭にしない
    assert not _zero(_run(UTSU, zero.replace("譲渡動物情報", "お知らせ")))


# --- 東大阪市 -------------------------------------------------------------
HO_DOG, HO_CAT = "city_higashiosaka-2", "city_higashiosaka-3"


def _uncomment_center_blocks(html: str) -> str:
    """今日のページは、センター・ボランティアの節の個体のブロックを HTML コメントの中に残し、「現在…の情報はありません」を出している。
    センターの子がいる日の版（Wayback に見つからない）を、そのコメントを外し 0 頭の文を消して再現する。
    市民間の仲介（出会い広場）のコメント（alt が「ゆずりたい犬」「譲りたい猫」）は外さない。"""
    import re

    def un(m):
        inner = m.group(1)
        return inner if ("譲渡対象犬の画像" in inner or "譲渡対象猫の画像" in inner) else m.group(0)

    out = re.sub(r"<!--(.*?)-->", un, html, flags=re.S)
    for s in ("現在、譲渡対象犬の情報はありません。", "現在、ボランティア犬の情報はありません。", "現在、譲渡対象猫はいません。"):
        out = out.replace(s, "")
    return out


def test_higashiosaka_registry():
    for slug, species in ((HO_DOG, "dog"), (HO_CAT, "cat")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "大阪府", slug
        assert s.species == species and s.phone == "072-963-6211" and s.recipe_path.exists(), slug
        assert s.photo == "ok", slug  # 東大阪市の規約は無断転載禁止のみ


def test_higashiosaka_today_is_zero_and_never_reads_the_matching_board():
    # 今日はセンターの犬も譲渡ボランティアの犬も 0 頭。1 頭載っているのは「犬の出会い広場」（市民間の仲介）で、載せない
    html = _fx("w006_city_higashiosaka-2_20261117.html")
    assert "TD24-1" in html and "現在、譲渡対象犬の情報はありません" in html
    assert _zero(_run(HO_DOG, html))
    html = _fx("w006_city_higashiosaka-3_20261117.html")
    assert "TC230512-1" in html and "現在、譲渡対象猫はいません" in html
    assert _zero(_run(HO_CAT, html))


def test_higashiosaka_zero_days_in_wayback():
    for name in ("w006_city_higashiosaka-2_zero_wb20231002.html", "w006_city_higashiosaka-2_zero_wb20251215.html",
                 "w006_city_higashiosaka-2_zero_wb20260514.html"):
        assert _zero(_run(HO_DOG, _fx(name))), name
    assert _zero(_run(HO_CAT, _fx("w006_city_higashiosaka-3_zero_wb20250324.html")))


def test_higashiosaka_center_and_volunteer_dogs_are_read_when_present():
    html = _uncomment_center_blocks(_fx("w006_city_higashiosaka-2_20261117.html"))
    assert "現在、譲渡対象犬の情報はありません" not in html and "TD24-1" in html
    c = _run(HO_DOG, html)
    assert c.status == "ok", c.error
    nos = [a["management_no"] for a in c.result.animals]
    assert nos == ["D21@@@-2", "D231010-1", "D190530-2"]  # 出会い広場の TD24-1（alt「ゆずりたい犬」）は読まない
    by = {a["management_no"]: a for a in c.result.animals}
    assert by["D231010-1"]["breed"] == "トイ・プードル" and by["D231010-1"]["sex"] == "オス(去勢)" and by["D231010-1"]["color"] == "茶"
    assert by["D190530-2"]["breed"] == "シーズー" and "人懐っこく穏やか" in by["D190530-2"]["note"]
    assert all(a["species"] == "dog" for a in c.result.animals)
    assert by["D231010-1"]["image_url"] and by["D21@@@-2"]["image_url"] is None  # 写真なしの雛形（pic_noimage）は写真にしない


def test_higashiosaka_center_cats_are_read_when_present():
    html = _uncomment_center_blocks(_fx("w006_city_higashiosaka-3_20261117.html"))
    assert "現在、譲渡対象猫はいません" not in html
    c = _run(HO_CAT, html)
    assert c.status == "ok", c.error
    assert c.result.animals and all(a["species"] == "cat" and a["management_no"] for a in c.result.animals)
    assert not any(a["management_no"].startswith("TC") for a in c.result.animals)  # 出会い広場（TC…）は読まない


def test_higashiosaka_zero_sentence_gone_without_animals_is_not_zero():
    html = _fx("w006_city_higashiosaka-2_20261117.html").replace("現在、譲渡対象犬の情報はありません。", "")
    assert not _zero(_run(HO_DOG, html))   # 1 つの節の文だけが消えた（作りが変わった）日は 0 頭にしない
    html = _fx("w006_city_higashiosaka-3_20261117.html").replace("現在、譲渡対象猫はいません。", "")
    assert not _zero(_run(HO_CAT, html))
