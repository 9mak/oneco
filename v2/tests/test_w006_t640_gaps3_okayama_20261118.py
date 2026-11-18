"""W006 T640 掲載漏れ 3 回目 A: 岡山市の譲渡犬・譲渡猫の一覧（2026-11-18・ネットワークなし）。

- 譲渡犬情報一覧（0000016441）と譲渡猫情報一覧（0000016404）。台帳の city_okayama は保護動物（迷子）の個別記事を読むので別のページ。
  仕様の親ページ（0000016464）は「保護犬情報一覧」（譲渡犬の情報ではありません）なので足さない。
- h3「1D2026067(ちゃこ君)」→ 名前(仮)・種類・性別・月齢の欄 → 写真のブロックが 1 頭分。「譲渡が決まりました」の子は見出しだけで中身が無い。「お声かかり中」は載せて note に出す。
- Wayback の版: 犬 2023-02・2024-08・2025-12、猫 2023-03・2024-02・2025-04・2025-08（猫の 0 頭の文は 2024-02・2025-04・2025-08 に出る）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

DOG, CAT = "city_okayama-2", "city_okayama-3"
DOG_URL = "https://www.city.okayama.jp/kurashi/0000016441.html"
CAT_URL = "https://www.city.okayama.jp/kurashi/0000016404.html"
CAT_ZERO_SENTENCES = ["現在、譲渡対象の猫はいません", "現在、譲渡対象猫はいません", "現在譲渡者募集中の猫はいません"]


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry():
    for slug, url, species in ((DOG, DOG_URL, "dog"), (CAT, CAT_URL, "cat")):
        s = SOURCES[slug]
        assert (s.url, s.kind, s.species, s.mode, s.enabled) == (url, "adoption", species, "recipe", True)
        assert (s.municipality, s.prefecture) == ("岡山市", "岡山県")
        assert s.photo == "ok"   # 11/02〜05 に岡山市から写真の表示は可の返事（既存の city_okayama と同じ）
        assert s.recipe_path.exists()


def test_dog_today_reads_30_dogs_and_skips_the_two_already_decided():
    html = _fx("w006_city_okayama-2_20261118.html")
    assert "譲渡が決まりました" in html   # 1D2026059 ポテト君・1D2025169 福ちゃん
    c = _run(DOG, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 30 and len({a["id"] for a in animals}) == 30
    assert all(a["species"] == "dog" for a in animals)
    assert not any(a["management_no"] in ("1D2026059", "1D2025169") for a in animals)
    first = animals[0]
    assert (first["management_no"], first["name"], first["breed"], first["sex"]) == ("1D2026067", "ちゃこ君", "雑種", "オス")
    assert first["age"] == "生後1ヶ月半ほど(令和8年11月中旬、現在)"
    assert first["image_url"] == "https://www.city.okayama.jp/kurashi/cmsfiles/contents/0000016/16441/112.jpg"
    by = {a["management_no"]: a for a in animals}
    # 括弧は半角にそろえる（エンジンの正規化）。2 つ目の節（譲渡に条件がある犬達・ZOOねるパークの犬たち・他の施設で訓練中）の子も読む。年齢・フィラリア・体重の書き方が違っても名前と性別は同じに取れる
    assert (by["1D2024171"]["name"], by["1D2024171"]["sex"], by["1D2024171"]["age"]) == ("サンドくん", "オス", "推定4才(令和8年現在)")
    assert by["1D2025072"]["name"] == "エムちゃん" and "陽性" in by["1D2025072"]["note"]
    assert by["1D2024209"]["name"] == "乙(オト)くん" and by["R04030"]["name"] == "茶太くん"
    # 名前の欄が写真のブロックの中にあっても（お声かかり中の子）読み、お声かかり中は note に出す（トライアル中と同じ。載せて状況を出す）
    called = [a["management_no"] for a in animals if "お声かかり中" in (a.get("note") or "")]
    assert called == ["1D2026073", "1D2026061", "1D2025160", "1D2024231"]
    assert by["1D2026073"]["name"] == "ゆきみちゃん" and by["1D2026073"]["image_url"].endswith("/16441/71.jpg")
    # 写真は 1 頭目の 1 枚目（複数枚ある子は先頭）
    assert by["1D2026055"]["image_url"].endswith("/16441/587.jpg")


def test_cat_today_reads_3_cats_and_no_zero_sentence_is_on_the_page():
    html = _fx("w006_city_okayama-3_20261118.html")
    assert not any(s in html for s in CAT_ZERO_SENTENCES)
    c = _run(CAT, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["management_no"], a["name"], a["sex"]) for a in animals] == [
        ("1N2026036", "うーちゃん", "メス"), ("1N2026047", "イチ君", "オス"), ("1N2026040", "ティラ君", "オス")]
    assert all(a["species"] == "cat" for a in animals)
    assert animals[0]["image_url"].endswith("/16404/image199.jpeg")
    assert "お声かかり中" in animals[2]["note"] and animals[2]["image_url"].endswith("/16404/image13.jpeg")
    assert not any("お声かかり中" in (a.get("note") or "") for a in animals[:2])


def test_dog_other_days_in_wayback():
    for name, n, called in (
        ("w006_city_okayama-2_wb20230203.html", 17, 3),
        ("w006_city_okayama-2_wb20240802.html", 17, 2),
        ("w006_city_okayama-2_wb20251204.html", 29, 4),
    ):
        c = _run(DOG, _fx(name))
        assert c.status == "ok", (name, c.error)
        assert len(c.result.animals) == n, name
        assert sum("お声かかり中" in (a.get("note") or "") for a in c.result.animals) == called, name
        assert all(a["management_no"] and a["name"] for a in c.result.animals), name


def test_cat_zero_days_in_wayback_are_zero_and_never_on_a_day_with_cats():
    for name in ("w006_city_okayama-3_wb20240203.html", "w006_city_okayama-3_wb20250421.html", "w006_city_okayama-3_wb20250815.html"):
        html = _fx(name)
        assert any(s in html for s in CAT_ZERO_SENTENCES), name
        assert _zero(_run(CAT, html)), name


def test_cat_old_layout_with_animal_headings_as_h2_is_not_zero():
    # 2023-03 は子（ジジちゃん・お声かかり中）が h2 の見出しと写真だけで載る別の作り。1 頭も読めないが 0 頭とは言わない（failed で通知）
    c = _run(CAT, _fx("w006_city_okayama-3_wb20230327.html"))
    assert c.status == "failed", c.status


def test_dog_zero_only_when_the_frame_is_there_and_no_dog_is():
    # 犬の 0 頭の日の版は Wayback に見つからない。今日の保存ページから犬の見出し・欄・写真を消して再現する
    soup = BeautifulSoup(_fx("w006_city_okayama-2_20261118.html"), "lxml")
    for el in soup.select("#mol_contents h3, #mol_contents div.mol_imageblock"):
        el.decompose()
    for div in soup.select("#mol_contents div.mol_textblock"):
        if "名前(仮)" in div.get_text():
            div.decompose()
    assert _zero(_run(DOG, str(soup)))
    # 枠の見出し（h1）が変わった日は 0 頭にしない
    assert not _zero(_run(DOG, str(soup).replace("譲渡犬情報一覧", "犬の情報")))


def test_dog_that_cannot_be_read_is_not_zero():
    html = _fx("w006_city_okayama-2_20261118.html")
    # 欄の名前が変わった日（見出し・写真は残る）
    assert not _zero(_run(DOG, html.replace("名前(仮)", "愛称")))
    # 動物の見出しの書き方が変わった日（写真は残る）
    soup = BeautifulSoup(html, "lxml")
    for h in soup.select("#mol_contents h3"):
        h.name = "h4"
    assert not _zero(_run(DOG, str(soup)))
