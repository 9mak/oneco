"""W006 T640 掲載漏れ 3 回目 B: 高知県中央・中村小動物管理センター アニマルステーション（市民の掲示板）のうち迷子の 4 区分（2026-11-18・ネットワークなし）。

おまえさん決定: 飼い主が探している迷子（lost）と市民が保護している迷子（sheltered）は載せる。飼えなくなった飼い主からの譲渡（「猫を譲りたい人」）は載せない。
- 区分ごとの一覧: category/maigo-sagasu-neko（猫を探している）・maigo-sagasu-inu（犬を探している）・maigo-hogo-neko（猫を保護している）・maigo-hogo-inu（犬を保護している）。
- 一覧のカード（li.unit）に管理番号・仮名・種類・性別と区分のリンクが出る。個体ページには「提供者住所」（市民の住所）が出るので辿らない。
- 「迷子の猫を保護している」の今日の 1 件（08J05）は「猫を譲りたい人」の区分も付いた譲渡の投稿なので載せない。
- 犬の 2 区分は今日 0 頭（カードの無い一覧）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

SAGASU_NEKO, SAGASU_INU, HOGO_NEKO, HOGO_INU = "kochi_apc-3", "kochi_apc-4", "kochi_apc-5", "kochi_apc-6"
URL = {
    SAGASU_NEKO: "https://kochi-apc.com/category/maigo-sagasu-neko/",
    SAGASU_INU: "https://kochi-apc.com/category/maigo-sagasu-inu/",
    HOGO_NEKO: "https://kochi-apc.com/category/maigo-hogo-neko/",
    HOGO_INU: "https://kochi-apc.com/category/maigo-hogo-inu/",
}
FXN = {
    SAGASU_NEKO: "w006_kochi_apc-3_20261118.html",
    SAGASU_INU: "w006_kochi_apc-4_20261118.html",
    HOGO_NEKO: "w006_kochi_apc-5_20261118.html",
    HOGO_INU: "w006_kochi_apc-6_20261118.html",
}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str, extra: dict[str, str] | None = None) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html, **(extra or {})}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry():
    expect = {
        SAGASU_NEKO: ("lost", "cat", "no"),
        SAGASU_INU: ("lost", "dog", "no"),     # 飼い主が届けた迷子の写真は出さない（町田・前橋・宮崎の前例）
        HOGO_NEKO: ("sheltered", "cat", "pending"),   # kochi_apc（譲渡）と同じ。返事が来るまで写真を出さない
        HOGO_INU: ("sheltered", "dog", "pending"),
    }
    for slug, (kind, species, photo) in expect.items():
        s = SOURCES[slug]
        assert (s.url, s.kind, s.species, s.photo, s.mode, s.enabled) == (URL[slug], kind, species, photo, "recipe", True), slug
        assert (s.prefecture, s.phone, s.contact_scope) == ("高知県", "088-831-7939", "operator"), slug
        assert s.recipe_path.exists(), slug


def test_fixtures_hold_no_private_address_of_the_citizens():
    # 個体ページには「提供者住所」（投稿した市民の住所）が出る。一覧だけを読み、個体ページは辿らない・fixture にも入れない
    for name in FXN.values():
        assert "提供者住所" not in _fx(name), name


def test_lost_cats_today_reads_3_cards_and_the_photo_only_where_there_is_one():
    c = _run(SAGASU_NEKO, _fx(FXN[SAGASU_NEKO]))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["management_no"], a["name"], a["breed"], a["sex"]) for a in animals] == [
        ("08M04", "ララ", "雑種", "オス・去勢済み"),
        ("08M03", "るい", "雑種", "メス・不妊済み"),
        ("08M02", "らん", "雑種", "メス・不妊済み"),
    ]
    assert all(a["species"] == "cat" for a in animals) and len({a["id"] for a in animals}) == 3
    assert animals[0]["image_url"] == "https://kochi-apc.com/wp-content/uploads/2026/10/IMG_3804.jpeg"
    assert not animals[1]["image_url"] and not animals[2]["image_url"]   # 「写真がありません」の仮画像（no-image.png）は写真にしない
    # 個体ページ（行方不明の場所などが載る）へのリンクを元ページのリンクにする
    assert [a["source_url"] for a in animals] == ["https://kochi-apc.com/28487/", "https://kochi-apc.com/5640/", "https://kochi-apc.com/5638/"]


def test_shelter_cat_that_is_also_tagged_as_a_give_away_post_is_not_listed_and_the_day_is_zero():
    html = _fx(FXN[HOGO_NEKO])
    assert "08J05" in html and "猫を譲りたい人" in html   # 区分が「猫を譲りたい人」と「迷子の猫を保護している」の両方
    c = _run(HOGO_NEKO, html)
    assert _zero(c), (c.status, c.error)
    assert c.result.empty_evidence == "empty_absent"


def test_shelter_cat_tagged_only_as_found_is_listed():
    # 譲渡の区分が付かない投稿（市民が保護している迷子だけ）は載せる。今日の 08J05 から譲渡の区分を外して再現する
    html = _fx(FXN[HOGO_NEKO])
    assert html.count("猫を譲りたい人") >= 1
    soup = BeautifulSoup(html, "lxml")
    for a in soup.select("li.unit a.yuzuru-neko"):
        a.decompose()
    c = _run(HOGO_NEKO, str(soup).replace("猫を譲りたい人", ""))
    assert c.status == "ok", c.error
    assert [(a["management_no"], a["name"], a["sex"], a["species"]) for a in c.result.animals] == [("08J05", "るか", "オス", "cat")]


def test_dogs_today_are_zero_because_the_list_is_empty():
    for slug in (SAGASU_INU, HOGO_INU):
        html = _fx(FXN[slug])
        assert "li class=\"unit\"" not in html
        c = _run(slug, html)
        assert _zero(c), (slug, c.status, c.error)


def test_zero_is_never_claimed_when_a_card_cannot_be_read_or_the_frame_is_gone():
    html = _fx(FXN[SAGASU_NEKO])
    # カードの作りが変わった日（表が無い）は読めないので 0 頭にしない
    soup = BeautifulSoup(html, "lxml")
    for t in soup.select("li.unit div.animal-table"):
        t.decompose()
    for a in soup.select("li.unit a.animal-more"):
        a.decompose()
    assert not _zero(_run(SAGASU_NEKO, str(soup)))
    # 一覧の枠そのものが無い日（作り替え・ブロック画面）は 0 頭にしない
    gone = _fx(FXN[SAGASU_INU]).replace("animal-card", "animal-list")
    assert not _zero(_run(SAGASU_INU, gone))
    # 犬の一覧にカードが 1 枚載った日（今日の猫のカードを入れる）は 0 頭でなく読む
    card = BeautifulSoup(html, "lxml").select_one("li.unit")
    dog = BeautifulSoup(_fx(FXN[SAGASU_INU]), "lxml")
    dog.select_one("ul.animal-card-item").append(card)
    c = _run(SAGASU_INU, str(dog))
    assert c.status == "ok" and [a["species"] for a in c.result.animals] == ["dog"]


def test_next_page_of_the_list_is_followed():
    # 一覧が複数ページに分かれた日（WP-PageNavi の「次へ」）も読む。今日は 1 ページだけなので、2 ページ目を作って確かめる（実物は未観測）
    html = _fx(FXN[SAGASU_NEKO])
    soup = BeautifulSoup(html, "lxml")
    nav = BeautifulSoup("<div class='wp-pagenavi'><span class='current'>1</span><a class='nextpostslink' rel='next' href='https://kochi-apc.com/category/maigo-sagasu-neko/page/2/'>»</a></div>", "lxml").div
    soup.select_one("div.animal-card").insert_after(nav)
    p1 = str(soup)
    assert "nextpostslink" in p1
    p2 = html.replace("08M04", "08M09").replace("08M03", "08M08").replace("08M02", "08M07").replace("IMG_3804", "IMG_9999")
    c = _run(SAGASU_NEKO, p1, {"https://kochi-apc.com/category/maigo-sagasu-neko/page/2/": p2})
    assert c.status == "ok", c.error
    assert sorted(a["management_no"] for a in c.result.animals) == ["08M02", "08M03", "08M04", "08M07", "08M08", "08M09"]
