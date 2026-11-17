"""W006 T640 掲載漏れ 2 回目 B: 市民の掲示板のうち迷子（2026-11-17・ネットワークなし）。

おまえさん決定: 飼い主が探している迷子（lost）と、市民が保護している迷子（sheltered）は載せる。飼えなくなった飼い主からの譲渡（新しい飼い主さがし・出会い広場など）は載せない。
- 写真: lost は飼い主が届けた写真なので photo: no（町田の前例）。sheltered は千葉市・旭川の前例どおりホストの規約で決める（無断転載禁止だけなら ok・事前相談が要るホストは pending）。
- 前橋市（行方不明一覧 lost・市民保護一覧 sheltered）・鳥取県（捜しています lost・保護しています sheltered）・船橋市（個人等で保護している動物 sheltered と、同じページの迷子動物 lost）・
  宮崎市（迷子の猫・犬を探しています lost・迷子の猫・犬を保護しています sheltered）。
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


def _by_species(c: Collected) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in c.result.animals:
        out[a["species"]] = out.get(a["species"], 0) + 1
    return out


# --- 前橋市 ---------------------------------------------------------------
MB_LOST, MB_SHELTERED = "city_maebashi-2", "city_maebashi-3"


def test_maebashi_registry():
    s = SOURCES[MB_LOST]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, "lost", "mixed", "群馬県")
    assert s.photo == "no" and s.phone == "027-220-5777" and s.recipe_path.exists()  # 飼い主が届けた写真は出さない
    s = SOURCES[MB_SHELTERED]
    assert (s.mode, s.enabled, s.kind, s.species, s.prefecture) == ("recipe", True, "sheltered", "mixed", "群馬県")
    assert s.photo == "pending" and s.phone == "027-220-5777" and s.recipe_path.exists()  # 前橋市の規約は転載要申請（事前相談の要るホスト）


def test_maebashi_lost_today_reads_6_dogs_27_cats_and_3_birds():
    html = _fx("w006_city_maebashi-2_20261117.html")
    c = _run(MB_LOST, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 36 and _by_species(c) == {"dog": 6, "cat": 27, "other": 3}
    assert len({a["id"] for a in animals}) == 36
    first = animals[0]
    assert (first["management_no"], first["shelter_date"], first["location"], first["breed"], first["sex"], first["age"], first["color"]) == (
        "YD2026-10-01", "2026年9月26日", "小坂子町", "雑種(柴犬系)", "オス", "10歳", "茶")
    assert "尻尾の毛がない" in first["note"] and "革製青色" in first["note"]
    by = {a["management_no"]: a for a in animals}
    # 行方不明の日時に時刻・午前午後・朝などが付いても、場所だけを取る
    assert by["YD2026-09-04"]["location"] == "吉岡町漆原" and by["YD2026-09-02"]["location"] == "伊勢崎市下植木町"
    assert by["Y2026-11-07"]["location"] == "青柳町" and by["Y2026-10-13"]["location"] == "柏倉町"
    assert by["Y2026-11-09"]["species"] == "other" and by["Y2026-11-10"]["species"] == "cat"


def test_maebashi_lost_other_day_in_wayback():
    c = _run(MB_LOST, _fx("w006_city_maebashi-2_child_wb20260616.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 13 and _by_species(c) == {"dog": 4, "cat": 9}


def test_maebashi_sheltered_today_reads_8_cats_1_dog_and_1_lizard():
    html = _fx("w006_city_maebashi-3_20261117.html")
    c = _run(MB_SHELTERED, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 10 and _by_species(c) == {"cat": 8, "dog": 1, "other": 1}
    first = animals[0]
    assert (first["management_no"], first["shelter_date"], first["location"], first["breed"], first["sex"], first["age"]) == (
        "A2026-11-02", "2026年10月中旬", "天川原町2丁目", "雑種(シャム系)", "オス", "成猫")
    lizard = next(a for a in animals if a["species"] == "other")
    assert lizard["management_no"] == "A2026-08-02" and "保護はしていない" in lizard["note"]
    assert sum(1 for a in animals if a["image_url"]) == 2  # 写真があるのは 2 件


def test_maebashi_sheltered_other_day_in_wayback():
    c = _run(MB_SHELTERED, _fx("w006_city_maebashi-3_child_wb20250206.html"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 5 and _by_species(c) == {"cat": 4, "dog": 1}


def test_maebashi_zero_only_when_the_frame_is_there_and_no_row_is():
    # 0 頭の日の版は Wayback に見つからない。今日の保存ページから動物の行・写真を消して再現する
    for slug, name in ((MB_LOST, "w006_city_maebashi-2_20261117.html"), (MB_SHELTERED, "w006_city_maebashi-3_20261117.html")):
        soup = BeautifulSoup(_fx(name), "lxml")
        for tr in soup.select("table tbody tr"):
            if tr.select("td"):
                tr.decompose()
        zero = str(soup)
        assert _zero(_run(slug, zero)), slug
        # 受付番号の書き方が変わった日（行は読める）は 0 頭にしない
        assert not _zero(_run(slug, _fx(name).replace("(Y", "（Y").replace("(A", "（A"))), slug
        # 枠の見出しが変わった日も 0 頭にしない
        assert not _zero(_run(slug, zero.replace("一覧】", "】")))
