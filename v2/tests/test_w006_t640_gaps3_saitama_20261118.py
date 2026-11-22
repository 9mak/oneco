"""W006 T640 掲載漏れ 3 回目 A: さいたま市の譲渡猫・譲渡犬の紹介（2026-11-18・ネットワークなし）。

- 譲渡猫の紹介（jyoutonekonosyoukai.html）19 頭と、譲渡犬の紹介（jyoutokensyoukai.html。仕様の親ページ p007933 は手続きの案内で犬の一覧は無い）3 頭。台帳の city_saitama-1・-2（保護犬・保護猫。迷子）とは別のページ。
- 手書きの HTML で作りが日ごとに変わる（Wayback: 猫は 2025 年が表、2026-03 から div の並び。犬は 2024〜2025 年が見出し・写真・名前が 1 つの p、今日は見出し p・写真 p・名前 p が別）。
  今日の作りを読み、別の作りの日は 0 頭と言わず failed で通知する。
- 「譲渡No.7　トライアル中！」は載せて note に出す。「飼い主さんが決まりました」の子は載せない（見出しにだけ書く）。子猫は「掲載していません」の注記があるだけで載っていない。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

CAT, DOG = "city_saitama-3", "city_saitama-4"
CAT_URL = "https://www.city.saitama.lg.jp/008/004/003/005/jyoutonekonosyoukai.html"
DOG_URL = "https://www.city.saitama.lg.jp/008/004/003/005/jyoutokensyoukai.html"
IMG = "https://www.city.saitama.lg.jp/008/004/003/005/"


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_registry():
    for slug, url, species in ((CAT, CAT_URL, "cat"), (DOG, DOG_URL, "dog")):
        s = SOURCES[slug]
        assert (s.url, s.kind, s.species, s.mode, s.enabled) == (url, "adoption", species, "recipe", True)
        assert (s.municipality, s.prefecture, s.phone) == ("さいたま市", "埼玉県", "048-840-4150")
        assert s.photo == "pending"   # 未指定は pending（2026-11-22 方針 1・2: 可の返事も規約の可も無いので、確認が取れるまで出さない）
        assert s.recipe_path.exists()


def test_cat_today_reads_19_cats_with_sex_age_color_and_the_two_on_trial():
    c = _run(CAT, _fx("w006_city_saitama-3_20261118.html"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert len(animals) == 19 and len({a["id"] for a in animals}) == 19
    assert [a["name"] for a in animals] == [
        "やまと", "かえで", "すずしろ", "ネロ", "つゆ", "エポ", "はっち", "おかか", "ミロ", "ひな",
        "はる", "しぐ", "どら", "くまろ", "ちょっちゃん", "きつね", "さくら", "てつ", "ピア"]
    assert all(a["species"] == "cat" for a in animals)
    assert [a["sex"] for a in animals] == [
        "去勢オス", "避妊メス", "去勢オス", "去勢オス", "避妊メス", "オス", "避妊メス", "去勢オス", "去勢オス", "メス",
        "避妊メス", "去勢オス", "オス", "去勢オス", "去勢オス", "去勢オス", "メス", "オス", "避妊メス"]
    assert [a["age"] for a in animals] == [
        "6歳", "2歳", "7歳", "6歳", "2歳", "1歳", "10歳", "3歳", "5歳", "3歳", "6歳", "3歳", "15歳", "3歳", "3歳", "3歳", "3歳", "10歳", "6歳"]
    by = {a["name"]: a for a in animals}
    # 全角の空白・括弧は半角にそろえる（エンジンの正規化）
    assert by["やまと"]["color"] == "白、一部薄茶 大きめ" and by["おかか"]["color"] == "灰白(黒白、サバ白にも見える)"
    assert "ブルーアイ" in by["やまと"]["note"] and "骨盤を骨折" in by["ネロ"]["note"]
    # 1 つの div に性別と年齢（毛色と特徴）が <br> で入る書き方・p に全部入る書き方（さくら・てつ・ピア）も読める
    assert (by["くまろ"]["sex"], by["くまろ"]["age"], by["くまろ"]["color"]) == ("去勢オス", "3歳", "黒、大きめ")
    assert "尖った耳" in by["きつね"]["note"] and by["きつね"]["color"] == "シャム風、小柄"
    assert (by["てつ"]["sex"], by["てつ"]["age"], by["てつ"]["color"]) == ("オス", "10歳", "黒茶、やせ")
    assert (by["ピア"]["sex"], by["ピア"]["color"]) == ("避妊メス", "茶トラ、大きめ") and by["ピア"]["image_url"] == IMG + "jyoutonekonosyoukai_d/img/230_i.jpg"
    # 譲渡No.7・No.12 はトライアル中（載せて note に出す）
    assert [a["name"] for a in animals if "トライアル中" in (a.get("note") or "")] == ["はっち", "しぐ"]
    # 写真は 1 頭の 1 枚目
    assert by["やまと"]["image_url"] == IMG + "jyoutonekonosyoukai_d/img/196_i.jpg"
    assert by["かえで"]["image_url"] == IMG + "jyoutonekonosyoukai_d/img/154_i.jpg"
    assert by["さくら"]["image_url"] == IMG + "jyoutonekonosyoukai_d/img/224_i.jpg"
    # 管理番号は譲渡No（ページの書き方のまま）
    assert by["やまと"]["management_no"] == "譲渡No.1" and by["てつ"]["management_no"] == "譲渡No.18"


def test_cat_whose_photo_sits_outside_the_siblings_is_still_read_without_a_photo():
    # 譲渡No.18（てつ）は写真の div と名前の p の間に div が挟まる作りで、写真が行の兄弟に無い。写真なしで載せる（名前・性別・年齢・毛色・特徴は読める）
    c = _run(CAT, _fx("w006_city_saitama-3_20261118.html"))
    tetsu = next(a for a in c.result.animals if a["name"] == "てつ")
    assert not tetsu["image_url"] and "両目が見えていない" in tetsu["note"]


def test_cat_2026_03_wayback_reads_16_cats_in_the_same_layout():
    c = _run(CAT, _fx("w006_city_saitama-3_wb20260309.html"))
    assert c.status == "ok", c.error
    assert [a["name"] for a in c.result.animals] == [
        "ひだか", "ボス", "やまと", "みこと", "かえで", "ムロ", "しゅうじ", "すみ", "すずしろ", "ネロ", "つゆ", "たけじ", "エポ", "はっち", "とらこ", "くー"]
    assert len({a["id"] for a in c.result.animals}) == 16


def test_cat_table_layout_of_2025_is_not_zero():
    # 2025 年の版は表（名前・写真・「1 性別 2 年齢…」の列）。読めないが猫は載っているので 0 頭とは言わない（failed で通知）
    c = _run(CAT, _fx("w006_city_saitama-3_wb20250219.html"))
    assert c.status == "failed", c.status


def test_cat_zero_only_when_the_frame_is_there_and_no_cat_is():
    # 猫の 0 頭の日の版は Wayback に無い（保存の 4 版はどれも猫がいる日）。今日の保存ページから猫の見出し・欄・写真を消して再現する
    soup = BeautifulSoup(_fx("w006_city_saitama-3_20261118.html"), "lxml")
    area = soup.select_one("div.wysiwyg_area")
    start = area.find("h2")
    end = area.find("h2", string=lambda s: bool(s) and "成猫から飼い始めて" in s)
    node = start.find_next_sibling()
    while node is not None and node is not end:
        nxt = node.find_next_sibling()
        node.decompose()
        node = nxt
    zero = str(soup)
    assert "名前：" not in zero and "譲渡No" not in zero
    assert _zero(_run(CAT, zero))
    # 枠の見出しが変わった日・名前の書き方が変わった日（写真は残る）は 0 頭にしない
    assert not _zero(_run(CAT, zero.replace("新しい飼い主さんを募集しています", "猫の一覧")))
    assert not _zero(_run(CAT, _fx("w006_city_saitama-3_20261118.html").replace("名前：", "愛称：")))


def test_decided_cat_is_not_listed_and_the_planned_trial_is():
    html = _fx("w006_city_saitama-3_20261118.html")
    c = _run(CAT, html.replace("<strong>譲渡No.2</strong>", "<strong>譲渡No.2　飼い主さんが決まりました</strong>", 1).replace("<strong>譲渡No.3</strong>", "<strong>譲渡No.3　トライアル予定あり</strong>", 1))
    names = [a["name"] for a in c.result.animals]
    assert "かえで" not in names and len(names) == 18
    assert "トライアル予定あり" in next(a for a in c.result.animals if a["name"] == "すずしろ")["note"]


def test_dog_today_reads_3_dogs_and_the_one_on_trial():
    c = _run(DOG, _fx("w006_city_saitama-4_20261118.html"))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["name"], a["breed"], a["sex"], a["size"], a["age"]) for a in animals] == [
        ("アル", "ラブラドール・レトリバー", "オス", "大型", "13歳"),
        ("ロン", "雑種", "オス", "中型", "9歳(推定)"),
        ("黒姫", "甲斐犬", "メス", "中型", "3歳"),
    ]
    assert all(a["species"] == "dog" for a in animals) and len({a["id"] for a in animals}) == 3
    assert [a["image_url"] for a in animals] == [IMG + "jyoutokensyoukai_d/img/120_s.jpg", IMG + "jyoutokensyoukai_d/img/131_i.jpg", IMG + "jyoutokensyoukai_d/img/128_s.jpg"]
    assert [a["management_no"] for a in animals] == ["譲渡No.1", "譲渡No.2", "譲渡No.3"]
    assert [a["name"] for a in animals if "トライアル中" in (a.get("note") or "")] == ["黒姫"]
    assert "耳血腫" in animals[0]["note"] and "フィラリア陽性" in animals[1]["note"]


def test_dog_other_days_in_the_same_layout_keep_the_same_id_for_the_same_dog():
    # 2025-08（4 頭。No.1 メルはトライアル予定あり）・2025-12（2 頭）は今日と同じ作り。アルの ID は写真から作るので日が変わっても同じ
    c1 = _run(DOG, _fx("w006_city_saitama-4_wb20250807.html"))
    c2 = _run(DOG, _fx("w006_city_saitama-4_wb20251206.html"))
    c3 = _run(DOG, _fx("w006_city_saitama-4_20261118.html"))
    assert c1.status == c2.status == c3.status == "ok"
    assert [a["name"] for a in c1.result.animals] == ["メル", "シルク", "ボビン", "アル"]
    assert [a["name"] for a in c2.result.animals] == ["ボビン", "アル"]
    assert "トライアル予定あり" in c1.result.animals[0]["note"] and "トライアル" not in (c1.result.animals[3].get("note") or "")
    aru = [next(a["id"] for a in c.result.animals if a["name"] == "アル") for c in (c1, c2, c3)]
    assert aru[0] == aru[1] == aru[2]


def test_dog_zero_sentence_is_on_the_zero_day_only():
    zero = _fx("w006_city_saitama-4_wb20240425.html")
    assert "現在、掲載可能な譲渡対象犬はいません" in zero
    assert _zero(_run(DOG, zero))
    # 犬のいる日（今日・2024-11・2025-03）には出ない
    for name in ("w006_city_saitama-4_20261118.html", "w006_city_saitama-4_wb20241102.html", "w006_city_saitama-4_wb20250325.html"):
        assert "現在、掲載可能な譲渡対象犬はいません" not in _fx(name), name


def test_dog_layout_of_2024_and_2025_is_not_zero():
    # 見出し・写真・名前が 1 つの p に入る作り（2024-11・2025-03）は今のレシピでは読めない。犬は載っているので 0 頭とは言わない（failed で通知）
    assert _run(DOG, _fx("w006_city_saitama-4_wb20241102.html")).status == "failed"
    # 2025-03 は 1 頭（ニナ・譲渡No.7）だけ今の作り（見出しの p・写真の p・名前の p が別）で、あとの 6 頭は古い作り。作りが混ざる日は今の作りの頭だけ読む
    # （古い作りの p は前の頭の見出しの印を取り違えるので、行にしない）
    c = _run(DOG, _fx("w006_city_saitama-4_wb20250325.html"))
    assert c.status == "ok" and [a["name"] for a in c.result.animals] == ["ニナ"]
    assert c.result.animals[0]["image_url"] == IMG + "jyoutokensyoukai_d/img/111_s.jpg"


def test_decided_dog_is_not_listed_and_dog_that_cannot_be_read_is_not_zero():
    html = _fx("w006_city_saitama-4_20261118.html")
    c = _run(DOG, html.replace("譲渡No.2<br />", "譲渡No.2　<strong>飼い主さんが決まりました</strong><br />", 1))
    assert [a["name"] for a in c.result.animals] == ["アル", "黒姫"]
    assert not _zero(_run(DOG, html.replace("名前：", "愛称：")))
    gone = BeautifulSoup(html, "lxml")
    for p in gone.select("div.wysiwyg_area p"):
        if "名前：" in p.get_text():
            p.decompose()
    assert not _zero(_run(DOG, str(gone)))   # 写真の p が残る（動物の痕跡）
