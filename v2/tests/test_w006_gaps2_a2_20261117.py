"""W006 T640 掲載漏れ 2 回目 A-2: 高知県の迷子情報・北海道（胆振・北見）・栃木県・新潟県（2026-11-17・ネットワークなし）。

- 高知県 中央・中村小動物管理センターの「迷子情報」（kochi_apc-2）: 台帳には譲渡（kochi_apc）しか無かった。一覧の「詳細はこちら」を個体ページ方式で辿る。
- 北海道 胆振の「飼い主募集中の犬・猫」（kainushibosyu.html）: 室蘭保健所の猫 2 頭は既存の hokkaido_iburi-1（室蘭保健所のページ）と同じ子なので足さない。
- 北海道 北見の飼い主募集中（hokkaido_okhotsk-6）・栃木県の飼い主募集中の犬たち（リンクのみ）・新潟県の猫の募集（リンクのみ）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 高知県 迷子情報 -------------------------------------------------------
KOCHI = "kochi_apc-2"


def _kochi_pages(keep: int = 4) -> tuple[dict[str, str], list[str]]:
    """一覧（今日 9 件）から先頭 keep 件だけを残した一覧と、その個体ページ（保存したのは先頭 4 件）の辞書。"""
    soup = BeautifulSoup(_fx("w006_kochi_apc-2_list_20261117.html"), "lxml")
    cards = soup.select("div.tab-animal-card")
    assert len(cards) == 9
    for c in cards[keep:]:
        c.decompose()
    links = [a["href"] for a in soup.select("a.animal-more")]
    pages = {SOURCES[KOCHI].url: str(soup)}
    for i, u in enumerate(links, 1):
        pages[u] = _fx(f"w006_kochi_apc-2_detail{i}_20261117.html")
    return pages, links


def test_kochi_registry():
    s = SOURCES[KOCHI]
    assert s.mode == "recipe" and s.enabled and s.kind == "stray" and s.prefecture == "高知県" and s.species == "mixed"
    assert s.phone == "088-831-7939" and s.address and s.contact_scope == "operator" and s.recipe_path.exists()
    assert s.photo == "pending"  # 返事待ち（kochi-apc.com）
    assert s.url == "https://kochi-apc.com/maigo/"


def test_kochi_reads_the_lost_animals_through_the_detail_pages():
    pages, links = _kochi_pages(4)
    c = collect_one(SOURCES[KOCHI], FakeFetcher(pages))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"] for a in animals] == ["20ADF261002", "31WCU260924", "CD26-021", "22ECU260908"]
    assert [a["species"] for a in animals] == ["dog", "cat", "dog", "cat"]  # 個体ページの「迷子の犬/猫」の区分リンク（center_maigo_inu / _neko）で決める
    assert [a["name"] for a in animals] == ["とうこちゃん", "ゆうすけ", "じゅん", "みか"]
    assert animals[0]["sex"] == "メス" and animals[0]["breed"] == "雑種" and animals[0]["location"] == "東洋町河内"
    assert all(a["image_url"] for a in animals)
    assert animals[0]["source_url"] == links[0]


def test_kochi_zero_only_when_the_frame_is_there_and_no_card_is():
    # 0 頭の日の版は Wayback に無い（2025-07〜2026-05 の 5 版はいずれも 20 件前後が載る）。今日の保存ページからカードを消して再現する
    soup = BeautifulSoup(_fx("w006_kochi_apc-2_list_20261117.html"), "lxml")
    for c in soup.select("div.tab-animal-card"):
        c.decompose()
    zero = str(soup)
    assert "迷子情報" in zero and _zero(_run(KOCHI, zero))
    # カードの class が変わった日（詳細へのリンクは残る）は 0 頭にしない
    broken = _fx("w006_kochi_apc-2_list_20261117.html").replace("tab-animal-card", "animal-card")
    pages = {SOURCES[KOCHI].url: broken}
    c = collect_one(SOURCES[KOCHI], FakeFetcher(pages))
    assert not _zero(c)
    # 枠の見出しが変わった日も 0 頭にしない
    assert not _zero(_run(KOCHI, zero.replace("迷子情報", "お知らせ")))



# --- 北海道 オホーツク（北見）飼い主募集中 -----------------------------------
OKH = "hokkaido_okhotsk-6"


def test_okhotsk_registry():
    s = SOURCES[OKH]
    assert s.mode == "recipe" and s.enabled and s.kind == "adoption" and s.prefecture == "北海道" and s.species == "mixed"
    assert s.phone == "0157-24-4171" and "北見市青葉町" in s.address and s.recipe_path.exists()
    assert s.photo == "pending"  # 北海道は返事待ち・未依頼


def test_okhotsk_today_reads_the_one_dog():
    c = _run(OKH, _fx("w006_hokkaido_okhotsk-6_20261117.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["species"], a["management_no"], a["sex"], a["age"], a["breed"]) == ("dog", "8-10-1", "メス", "5", "雑種")
    assert "元野犬なので" in a["note"] and "募集期限" in a["note"] and a["image_url"]


def test_okhotsk_other_days_in_wayback():
    c = _run(OKH, _fx("w006_hokkaido_okhotsk-6_child_wb20241210.html"))
    assert c.status == "ok" and [(a["species"], a["sex"]) for a in c.result.animals] == [("cat", "オス")], c.error
    c = _run(OKH, _fx("w006_hokkaido_okhotsk-6_child_wb20260125.html"))
    assert c.status == "ok" and [(a["species"], a["sex"], a["age"]) for a in c.result.animals] == [("cat", "メス", "10歳")], c.error
    assert c.result.animals[0]["management_no"] == "R7-1-い"
    # 4 行のうち、新しい飼い主さんが決まった 3 頭（R8-5-2・4・5）は載せず、募集中の R8-5-3 だけ読む
    c = _run(OKH, _fx("w006_hokkaido_okhotsk-6_child_wb20260722.html"))
    assert c.status == "ok", c.error
    assert [(a["species"], a["management_no"], a["sex"], a["age"]) for a in c.result.animals] == [("dog", "R8-5-3", "オス", "二か月")]


def test_okhotsk_zero_days_in_wayback_with_different_sentences():
    # 0 頭の日の文は「現在、新しい飼い主さんを探している犬はいません」「…募集している猫はいません」「現在、飼い主を募集している猫はいません」と変わる。
    # 犬の表が「新しい飼い主さんが見つかりました！」の行だけの日（2024-08）もある。文言でなく、募集中の行が 1 つも無いことで 0 頭を決める
    for name in ("w006_hokkaido_okhotsk-6_zero_wb20250804.html", "w006_hokkaido_okhotsk-6_zero_wb20240815.html"):
        assert _zero(_run(OKH, _fx(name))), name


def test_okhotsk_structure_change_is_not_zero():
    # 子のいる日に表の見出しの語が変わった（行が読めなくなった）日を 0 頭にしない
    html = _fx("w006_hokkaido_okhotsk-6_child_wb20260125.html").replace("特徴など", "備考")
    assert not _zero(_run(OKH, html))
    html = _fx("w006_hokkaido_okhotsk-6_zero_wb20250804.html").replace("飼い主募集中の犬", "譲渡の犬")
    assert not _zero(_run(OKH, html))


# --- 栃木県・新潟県（リンクのみ）---------------------------------------------
TOCHIGI, NIIGATA_ADULT, NIIGATA_KITTEN = "douai_pref_tochigi_adult-1", "pref_niigata-2", "pref_niigata-3"


def _note(slug: str) -> str:
    import yaml

    data = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))
    return next((d.get("note") or "") for d in data["sources"] if d["slug"] == slug)


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


def _as_recipe(slug: str, html: str) -> Collected:
    """link_only のレシピは「許諾が変わったときのために残す」もの。読み方が壊れていないことを、mode を recipe にして確かめる。"""
    import dataclasses

    src = dataclasses.replace(SOURCES[slug], mode="recipe")
    return collect_one(src, FakeFetcher({src.url: html}))


def test_tochigi_adult_dogs_are_link_only_without_photo():
    s = SOURCES[TOCHIGI]
    assert (s.mode, s.photo, s.enabled, s.kind, s.species) == ("link_only", "no", True, "adoption", "dog")
    assert s.url == "https://www.douai.pref.tochigi.lg.jp/work/dog/" and s.phone is None and s.address is None
    assert s.recipe_path.exists()   # 許諾が変わったときのために残す
    assert "2026-11-04" in _note(TOCHIGI)  # 栃木県の返事（リンクのみ）が理由
    assert collect_one(s, _NoFetch()).status == "link_only"


def test_tochigi_recipe_still_reads_the_dog_table_when_permission_changes():
    c = _as_recipe(TOCHIGI, _fx("w006_douai_pref_tochigi_adult-1_20261117.html"))
    assert c.status == "ok", c.error
    assert [(a["management_no"], a["sex"], a["age"], a["species"]) for a in c.result.animals] == [("R8-0002", "メス", "5~7歳", "dog")]
    assert c.result.animals[0]["image_url"] and "しっぽ" in c.result.animals[0]["note"]
    c = _as_recipe(TOCHIGI, _fx("w006_douai_pref_tochigi_adult-1_child_wb20250908.html"))
    assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == ["R7-0005", "R7-0006"], c.error
    c = _as_recipe(TOCHIGI, _fx("w006_douai_pref_tochigi_adult-1_child_wb20260116.html"))
    assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == ["R7-0009"], c.error


def test_tochigi_zero_day_is_zero_by_its_sentence_that_child_days_never_show():
    html = _fx("w006_douai_pref_tochigi_adult-1_zero_wb20250518.html")
    assert "飼い主さん募集中の犬はいません" in html
    assert _zero(_as_recipe(TOCHIGI, html))
    for name in ("w006_douai_pref_tochigi_adult-1_20261117.html", "w006_douai_pref_tochigi_adult-1_child_wb20250908.html",
                 "w006_douai_pref_tochigi_adult-1_child_wb20260116.html"):
        assert "募集中の犬はいません" not in _fx(name), name


def test_niigata_cat_pages_are_link_only_because_the_information_is_in_the_photos():
    for slug, url in ((NIIGATA_ADULT, "https://www.pref.niigata.lg.jp/sec/seikatueisei/1334350843426.html"),
                      (NIIGATA_KITTEN, "https://www.pref.niigata.lg.jp/sec/seikatueisei/1344055708060.html")):
        s = SOURCES[slug]
        assert (s.mode, s.enabled, s.kind, s.species, s.url) == ("link_only", True, "adoption", "cat", url), slug
        assert s.phone == "0258-21-5501" and s.address and s.recipe_path.exists(), slug
        assert collect_one(s, _NoFetch()).status == "link_only", slug


def test_niigata_adult_page_has_only_cage_numbers_as_text():
    html = _fx("w006_pref_niigata-2_20261117.html")
    soup = BeautifulSoup(html, "lxml")
    body = soup.select_one("#main_body")
    heads = [h.get_text(strip=True).strip("\u200b") for h in body.select("h3")]
    assert "15a-16a" in heads and "3段ケージ" in heads and len(body.select("img")) >= 40
    # 説明文は無く、動物の情報（種類・性別・年齢）は写真の中にしかない
    assert not any(w in body.get_text() for w in ("性別", "オス", "メス", "年齢", "種類"))
    c = _as_recipe(NIIGATA_ADULT, html)
    assert c.status == "ok" and len(c.result.animals) == 16 and all(a["species"] == "cat" and a["image_url"] for a in c.result.animals)


def test_niigata_kitten_page_shows_no_kitten():
    html = _fx("w006_pref_niigata-3_20261117.html")
    assert 'alt="子猫はいません"' in html
