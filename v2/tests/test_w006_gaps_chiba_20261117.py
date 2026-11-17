"""W006 T640 掲載漏れ 1 回目: 千葉県動物愛護センターの飼い主募集 4 ページ・千葉市の譲渡 2 ページの追加（2026-11-17・ネットワークなし）。

台帳には収容（pref_chiba-1〜5）・迷子と市民保護（city_chiba-1〜6）しか無く、里親募集のページが抜けていた。
- pref_chiba-6〜9: 本所の成猫・成犬その他、東葛飾支所の成猫その他・成犬。1 頭 = div.col2/col3 の列 1 つ（写真・【番号】名前・年齢・性別）。
  「譲渡になりました」の子は載せない、「予約あり」「トライアル中です」の子は載せて note に出す。
  0 頭は文言でなく「動物情報の PDF リンクも col の中の写真も無い」ことで決める（0 頭の文言は Wayback の版によって違う）。
- city_chiba-7・8: 千葉市の譲渡犬・譲渡猫。h4「26101501（クール）」→ p 写真 → p 種類・毛色・性別・年齢・コメント。
  「お見合いが決まりました！」の子は載せて note に出す（トライアル中と同じ扱い）。
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

CHIBA_PREF = ("pref_chiba-6", "pref_chiba-7", "pref_chiba-8", "pref_chiba-9")
CHIBA_CITY = ("city_chiba-7", "city_chiba-8")
TODAY = "20261117"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _today(slug: str) -> str:
    return _fx(f"w006_{slug}_{TODAY}.html")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def _by_no(c: Collected) -> dict[str, dict]:
    assert c.result is not None
    return {a["management_no"]: a for a in c.result.animals}


def test_registry_entries():
    expect = {
        "pref_chiba-6": ("cat", "0476-93-5711"), "pref_chiba-7": ("mixed", "0476-93-5711"),
        "pref_chiba-8": ("mixed", "04-7191-0050"), "pref_chiba-9": ("dog", "04-7191-0050"),
        "city_chiba-7": ("dog", "043-258-7817"), "city_chiba-8": ("cat", "043-258-7817"),
    }
    for slug, (species, phone) in expect.items():
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "千葉県", slug
        assert s.species == species and s.phone == phone, slug
        assert s.photo == "ok", slug  # 既存の同じホスト（pref.chiba.lg.jp・city.chiba.jp）の掲載元と同じ（規約は無断転載禁止のみ）
        assert s.contact_scope == "facility", slug
        assert s.recipe_path.exists(), slug


def test_honsyo_cat_today_reads_13_and_notes_reserved():
    c = _run("pref_chiba-6", _today("pref_chiba-6"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 13
    assert all(a["species"] == "cat" and a["image_url"] for a in c.result.animals)
    by = _by_no(c)
    assert by["c26042"]["name"] == "カン" and by["c26042"]["sex"] == "オス" and by["c26042"]["age"] == "推定4歳"
    assert by["c26017"]["sex"] == "メス"
    # 「予約あり」の 2 頭（チャチャ・ポム）は載せて note に出す。同じ番号 c26002 が 2 頭（パンチ・パンダ）に付く誤記があるので ID は写真から作る
    assert [a["name"] for a in c.result.animals if a.get("note") == "予約あり"] == ["チャチャ", "ポム"]
    assert len({a["id"] for a in c.result.animals}) == 13
    assert _hits("pref_chiba-6", _today("pref_chiba-6")) == []


def test_honsyo_dog_today_is_one_pigeon_not_zero_and_species_other():
    c = _run("pref_chiba-7", _today("pref_chiba-7"))
    assert c.status == "ok", c.error
    assert [(a["management_no"], a["name"], a["species"]) for a in c.result.animals] == [("z26801", "カワラバト", "other")]
    assert _hits("pref_chiba-7", _today("pref_chiba-7")) == []


def test_honsyo_dog_zero_days_are_empty_and_child_days_are_never_zero():
    for name in ("w006_pref_chiba-7_zero_wb20260717.html", "w006_pref_chiba-7_zero_wb20250519.html"):
        assert _zero(_run("pref_chiba-7", _fx(name))), name
    # 子のいる日: 「募集中の犬は0頭です」「現在、譲渡対象の動物はいません」は出ない。2026-03 は col の囲みが無い作りで行は読めないが、0 頭にもしない
    for name in ("w006_pref_chiba-7_child_wb20250922.html", "w006_pref_chiba-7_child_wb20260308.html"):
        html = _fx(name)
        assert "募集中の犬は0頭" not in html and "譲渡対象の動物はいません" not in html, name
        assert not _zero(_run("pref_chiba-7", html)), name
        assert _hits("pref_chiba-7", html) == [], name
    c = _run("pref_chiba-7", _fx("w006_pref_chiba-7_child_wb20250922.html"))
    assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == ["d23063", "d25043"], c.error
    assert all(a["species"] == "dog" for a in c.result.animals)


def test_shisyo_cat_reads_19_and_skips_decided():
    c = _run("pref_chiba-8", _today("pref_chiba-8"))
    assert c.status == "ok", c.error
    by = _by_no(c)
    assert len(c.result.animals) == 19  # h3「11月13日時点で19匹募集しています」。表は 20 件で、c260520-1-2（にん）は「譲渡になりました」
    assert "c260520-1-2" not in by
    assert all(a["species"] == "cat" for a in c.result.animals)
    assert {a["name"] for a in c.result.animals if a.get("note") == "トライアル中です"} == {"いち", "しい", "ごろう"}
    assert _hits("pref_chiba-8", _today("pref_chiba-8")) == []


def test_shisyo_dog_reads_two():
    c = _run("pref_chiba-9", _today("pref_chiba-9"))
    assert c.status == "ok", c.error
    by = _by_no(c)
    assert sorted(by) == ["d260817-2-1", "d260930-1-1"]
    assert by["d260930-1-1"]["name"] == "てんしん" and by["d260930-1-1"]["age"] == "14歳程度" and by["d260930-1-1"]["sex"] == "オス"
    assert all(a["species"] == "dog" for a in c.result.animals)
    assert _hits("pref_chiba-9", _today("pref_chiba-9")) == []


def test_city_dog_reads_six_and_keeps_omiai():
    c = _run("city_chiba-7", _today("city_chiba-7"))
    assert c.status == "ok", c.error
    by = _by_no(c)
    assert sorted(by) == ["26050706", "26080302", "26090202", "26090901", "26093001", "26101501"]
    cool = by["26101501"]
    assert cool["name"] == "クール" and cool["breed"] == "雑種" and cool["color"] == "茶黒" and cool["sex"] == "オス"
    assert cool["age"] == "1~3歳(推定)" and "元気いっぱい" in cool["note"]
    assert by["26093001"]["note"].startswith("お見合いが決まりました")
    assert all(a["species"] == "dog" and a["image_url"] for a in c.result.animals)
    assert _hits("city_chiba-7", _today("city_chiba-7")) == []


def test_city_cat_reads_twelve_in_two_sections():
    c = _run("city_chiba-8", _today("city_chiba-8"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 12  # 子猫 4 頭（ナラ・シンバ・ムー・テト）+ 成猫 8 頭
    by = _by_no(c)
    assert by["26082501"]["name"] == "ナラ" and by["26082501"]["sex"] == "メス"
    assert "圧迫排尿" in by["26090201"]["note"] and "センターには春から" not in by["26090201"]["note"]
    assert all(a["species"] == "cat" for a in c.result.animals)
    assert _hits("city_chiba-8", _today("city_chiba-8")) == []


def test_city_cat_child_days_in_wayback_read_and_never_zero():
    # 千葉市の譲渡猫: 2024-10（11 頭）・2026-04（10 頭）の版も同じレシピで読める（h4 の数と合う）
    for name, n in (("w006_city_chiba-8_child_wb20241010.html", 11), ("w006_city_chiba-8_child_wb20260421.html", 10)):
        html = _fx(name)
        c = _run("city_chiba-8", html)
        assert c.status == "ok", (name, c.error)
        assert len(c.result.animals) == n, name
        assert _hits("city_chiba-8", html) == [], name


def _strip_animals(html: str, slug: str) -> str:
    """子のいない日の作りを今日の保存ページから作る（動物の見出し・列だけ消し、枠・案内文・PDF リンクの無い作りにする）。"""
    soup = BeautifulSoup(html, "lxml")
    if slug.startswith("city_chiba"):
        for h4 in soup.select("div#contents_editable > h4"):
            if "（" in h4.get_text():
                sib = h4.find_next_sibling()
                while sib is not None and sib.name not in ("h2", "h3", "h4"):
                    nxt = sib.find_next_sibling()
                    sib.decompose()
                    sib = nxt
                h4.decompose()
    else:
        for col in soup.select("#tmp_contents div[class^='col']"):
            col.decompose()
    return str(soup)


def test_zero_day_without_any_animal_is_empty():
    # 実際の 0 頭の版が Wayback に無いページ（猫・東葛飾・千葉市）は、今日の保存ページから動物だけを消して 0 頭の作りを再現する
    for slug in ("pref_chiba-6", "pref_chiba-8", "pref_chiba-9", "city_chiba-7", "city_chiba-8"):
        assert _zero(_run(slug, _strip_animals(_today(slug), slug))), slug


def test_structure_change_with_children_is_not_zero():
    # 行の読み方が崩れた（番号の括弧・見出しの語が変わった）子のいる日は、0 頭にしない
    for slug in ("pref_chiba-6", "pref_chiba-8", "pref_chiba-9"):
        html = _today(slug).replace("【", "〔").replace("】", "〕")
        assert not _zero(_run(slug, html)), slug
    for slug in ("city_chiba-7", "city_chiba-8"):
        html = _today(slug).replace("種類：", "区分：")
        assert not _zero(_run(slug, html)), slug
