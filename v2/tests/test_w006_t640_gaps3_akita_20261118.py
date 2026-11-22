"""W006 T640 掲載漏れ 3 回目 A: 秋田市の「犬・猫の譲渡制度」に登録されている動物（2026-11-18・ネットワークなし）。

- 新しい飼い主を募集している犬（今日 0）と猫（5）。h2 の管理番号（F027）→ 写真 → ul の項目。台帳の city_akita-1〜3（公示・迷子・市民保護）と別のページ。
  「犬・ねこの飼い主紹介制度」（1012580。飼い主からの譲渡）は載せない。
- Wayback: 2026-03 は犬猫とも「…はいません」の 0 頭の日。2021-04・2023-03・2025-11 は別の作り（h3 の見出し・ラベルの無い欄）で今のレシピでは読めず、failed で通知される。
"""


from pathlib import Path

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


# --- 秋田市 ---------------------------------------------------------------
AKITA = "city_akita-4"
AKITA_URL = "https://www.city.akita.lg.jp/kurashi/pet/1005363/1012582.html"
AKITA_FX = "w006_city_akita-4_20261118.html"
AKITA_DOG_ZERO = "現在、秋田市保健所の譲渡制度に登録されている犬はいません"
AKITA_CAT_ZERO = "現在、秋田市保健所の譲渡制度に登録されている猫はいません"


def test_akita_registry():
    s = SOURCES[AKITA]
    assert (s.url, s.kind, s.species, s.mode, s.enabled) == (AKITA_URL, "adoption", "mixed", "recipe", True)
    assert (s.municipality, s.prefecture, s.phone) == ("秋田市保健所", "秋田県", "018-883-1182")
    assert s.photo == "pending" and s.recipe_path.exists()   # 未指定は pending（2026-11-22 方針 1・2: 可の返事も規約の可も無いので、確認が取れるまで出さない）


def test_akita_today_reads_5_cats_and_the_dog_section_is_empty():
    html = _fx(AKITA_FX)
    assert AKITA_DOG_ZERO in html and "登録されている猫は5匹です" in html
    c = _run(AKITA, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"] for a in animals] == ["F027", "F023", "F095", "F094", "F090"]
    assert all(a["species"] == "cat" for a in animals) and len({a["id"] for a in animals}) == 5
    assert [(a["breed"], a["sex"], a["age"]) for a in animals] == [
        ("雑種", "オス", "推定5カ月齢"), ("雑種", "メス", "推定6カ月齢"), ("雑種", "メス", "7カ月齢"),
        ("雑種", "去勢", "7カ月齢"), ("雑種", "メス", "推定3歳")]
    assert animals[0]["image_url"] == "https://www.city.akita.lg.jp/_res/projects/default_project/_page_/001/012/582/r08-f027.jpg"
    assert "体重：2.6kg" in animals[0]["note"] and "所有者不明の仔猫として収容しました。" in animals[0]["note"] and "カギしっぽ" in animals[0]["note"]
    assert "陰性" in animals[0]["note"] and "所有者飼養困難のため収容しました。" in animals[4]["note"]
    # 動画（YouTube）へのリンクの文字は note に入れない
    assert not any("YouTube" in (a.get("note") or "") or "You Tube" in (a.get("note") or "") for a in animals)


def test_akita_zero_needs_both_sections_empty():
    html = _fx(AKITA_FX)
    # 犬も猫も「…はいません」の日だけ 0 頭（犬の文は猫がいる日にも出るので、猫の文が無ければ 0 頭にしない）。猫の節（h2 から問い合わせの枠の手前まで）を 0 頭の文に差し替えて再現する
    start = html.index("<h2>新しい飼い主を募集している猫</h2>")
    end = html.index('<div id="pagequest">')
    both = html[:start] + "<h2>新しい飼い主を募集している猫</h2>\n<p>" + AKITA_CAT_ZERO + "。</p>\n" + html[end:]
    assert AKITA_DOG_ZERO in both and AKITA_CAT_ZERO in both and "F027" not in both
    assert _zero(_run(AKITA, both))
    assert not _zero(_run(AKITA, both.replace(AKITA_CAT_ZERO, "")))
    assert not _zero(_run(AKITA, both.replace(AKITA_DOG_ZERO, "")))
    # 猫のいる日（今日）には猫の 0 頭の文が出ない
    assert AKITA_CAT_ZERO not in html


def test_akita_zero_day_in_wayback_and_other_layouts_are_not_misread():
    # 2026-03 は犬も猫も「現在、…登録されている犬／猫はいません。」の 0 頭の日（実物）
    zero = _fx("w006_city_akita-4_wb20260312.html")
    assert AKITA_DOG_ZERO in zero and AKITA_CAT_ZERO in zero
    assert _zero(_run(AKITA, zero))
    # 猫のいる日（2025-11・2023-03・2021-04）は節の見出しが h3・欄が「雑種、オス、推定2カ月齢」の並びで、今の読み方（h2＋「種類：」）では 1 頭も読めない。
    # 猫が載っているので 0 頭とは言わず failed で通知する（犬の「…はいません」が出ていても）
    for name in ("w006_city_akita-4_wb20251115.html", "w006_city_akita-4_wb20230326.html", "w006_city_akita-4_wb20210413.html"):
        html = _fx(name)
        assert AKITA_CAT_ZERO not in html, name
        assert _run(AKITA, html).status == "failed", name
    # 2020-05 は 0 頭の日だが、書き方が古い（「…犬は0頭です」「…猫は0匹です」）ので 0 頭とは言い切らない（failed で通知）。今の書き方に変わってからの 0 頭は上のとおり
    old = _fx("w006_city_akita-4_wb20200511.html")
    assert "犬は0頭です" in old and _run(AKITA, old).status == "failed"
