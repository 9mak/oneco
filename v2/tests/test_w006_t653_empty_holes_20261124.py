"""W006 T653（方針 52）: 誤って 0 頭と出す穴 2 つ（2026-11-24）。

- 岡山市 city_okayama: 入口に「保護犬情報一覧」の記事があり他に記事が無いと 0 頭と確定していた。一覧の表（0000016464）に期限が
  先の行がある（保護中の子がいる）のに個別記事がまだ無い日も 0 頭になる。一覧の表も辿り、期限が今日以降（読めない行も）の行があれば 0 頭と確定しない。
- さいたま市 city_saitama-1・-2: 枠の h2 があり「管理番号 …-数字」「収容日：令和」が無いだけで 0 頭と確定していた。0 頭の日の書き方
  （全項目が空の雛形）を正の根拠にし、写真・数字の入った項目など作りの根拠が 1 つでもあれば確定しない。
"""

from datetime import date
from pathlib import Path

import pytest
from collector import extract
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _swap(html: str, old: str, new: str) -> str:
    assert old in html, old
    return html.replace(old, new)


def _collect(slug: str, pages: dict[str, str | bytes]) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher(pages))


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract, "_today", lambda: date(2026, 11, 24))


# --- 岡山市 -------------------------------------------------------------------------------------------------------
OKA = "city_okayama"
BASE = "https://www.city.okayama.jp/kurashi/"
OKA_INDEX = "w006_t653_city_okayama_index_20261124.html"        # 個別 2 本（1D2026080・1D2026079）＋猫一覧・訓練・犬一覧
OKA_ZERO_INDEX = "w006_city_okayama_index_zero_20261119.html"   # 個別記事が無く 3 本だけ
OKA_LIST = "w006_t653_city_okayama_list_20261124.html"          # 保護犬情報一覧の表: 2 行・期限 令和8年11月27日
OKA_DOGS = {BASE + "0000060648.html": "w006_t653_city_okayama_dog_1D2026080_20261124.html",
            BASE + "0000086918.html": "w006_t653_city_okayama_dog_1D2026079_20261124.html"}
OKA_LIST_URL = BASE + "0000016464.html"
DEADLINE = "令和8年11月27日"


def _oka(index: str, list_html: str | None, dogs: bool) -> Collected:
    pages: dict[str, str | bytes] = {SOURCES[OKA].url: _fx(index)}
    if list_html is not None:
        pages[OKA_LIST_URL] = list_html
    if dogs:
        pages.update({u: _fx(f) for u, f in OKA_DOGS.items()})
    return _collect(OKA, pages)


def test_okayama_today_reads_2_dogs_and_the_list_table_is_not_an_animal():
    c = _oka(OKA_INDEX, _fx(OKA_LIST), dogs=True)
    assert c.status == "ok", c.error
    assert c.result is not None
    assert sorted(a["management_no"] for a in c.result.animals) == ["1D2026079", "1D2026080"]


def test_okayama_list_row_with_a_future_deadline_and_no_article_is_not_a_zero():
    # 穴の型の日: 一覧の表に期限が先の行（保護中）があるのに個別記事がまだ無い
    c = _oka(OKA_ZERO_INDEX, _fx(OKA_LIST), dogs=False)
    assert c.status not in ("ok", "empty"), (c.status, c.error)
    assert c.result is not None and c.result.animals == []


def test_okayama_list_row_with_a_deadline_today_is_not_a_zero():
    c = _oka(OKA_ZERO_INDEX, _swap(_fx(OKA_LIST), DEADLINE, "令和8年11月24日"), dogs=False)
    assert c.status not in ("ok", "empty"), (c.status, c.error)


def test_okayama_list_with_only_expired_rows_is_a_confirmed_zero():
    c = _oka(OKA_ZERO_INDEX, _swap(_fx(OKA_LIST), DEADLINE, "令和8年11月23日"), dogs=False)
    assert c.status == "empty", (c.status, c.error)
    assert c.result is not None and c.result.animals == []


def test_okayama_list_with_no_rows_is_a_confirmed_zero():
    html = _fx(OKA_LIST)
    start = html.index("<tbody>") + len("<tbody>")
    header_end = html.index("</tr>", start) + len("</tr>")
    end = html.index("</tbody>")
    c = _oka(OKA_ZERO_INDEX, html[:header_end] + html[end:], dogs=False)
    assert c.status == "empty", (c.status, c.error)


def test_okayama_list_row_with_an_unreadable_deadline_is_not_a_zero():
    c = _oka(OKA_ZERO_INDEX, _swap(_fx(OKA_LIST), DEADLINE, "掲載期限なし"), dogs=False)
    assert c.status not in ("ok", "empty"), (c.status, c.error)


def test_okayama_list_page_gone_is_not_a_zero():
    # 一覧の表を読めない日は、辿れなかったので 0 頭にしない
    c = _oka(OKA_ZERO_INDEX, None, dogs=False)
    assert c.status == "failed", (c.status, c.error)


# --- さいたま市 -----------------------------------------------------------------------------------------------------
SAI1, SAI2 = "city_saitama-1", "city_saitama-2"
SAI1_ZERO = "w006_t653_city_saitama-1_zero_20261124.html"       # 今日: 雛形の「管理番号 R08-」「収容日：」だけ
SAI1_CHILD = "w006_city_saitama-1_child_20261119.html"          # R08-17 のいる日
SAI1_ZEROS = [SAI1_ZERO, "w006_city_saitama-1_zero_wb20260210.html", "w006_city_saitama-1_zero_wb20250715.html"]
SAI2_CHILD = "w006_t653_city_saitama-2_children_20261124.html"  # 今日: 猫 2 頭ほか
SAI2_ZEROS = ["t521_saitama-2_wb20250209.html"]
SAI2_OLD_CHILD = "w006_city_saitama-2_20261107.html"


def _one(slug: str, html: str) -> Collected:
    return _collect(slug, {SOURCES[slug].url: html})


@pytest.mark.parametrize("name", SAI1_ZEROS)
def test_saitama_1_template_only_day_is_a_confirmed_zero(name: str):
    c = _one(SAI1, _fx(name))
    assert c.status == "empty", (c.status, c.error)


@pytest.mark.parametrize("name", SAI2_ZEROS)
def test_saitama_2_template_only_day_is_a_confirmed_zero(name: str):
    c = _one(SAI2, _fx(name))
    assert c.status == "empty", (c.status, c.error)


def test_saitama_1_day_with_a_dog_is_read_and_not_a_zero():
    c = _one(SAI1, _fx(SAI1_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and [a["management_no"] for a in c.result.animals] == ["R8-17"]


def test_saitama_2_today_reads_its_cats():
    c = _one(SAI2, _fx(SAI2_CHILD))
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 5


def _reworded_child(html: str) -> str:
    """穴の型: 子の側だけ「管理番号」「収容日：令和」の書き方が変わった（雛形はそのまま）。"""
    out = html
    for old, new in (("管理番号 R08-17", "整理番号 R08-17"), ("収容日：令和", "保護日：令和"), ("公示（掲載）期限：令和", "掲載期限：令和")):
        out = _swap(out, old, new)
    return out


def test_saitama_1_reworded_child_is_not_a_zero():
    c = _one(SAI1, _reworded_child(_fx(SAI1_CHILD)))
    assert c.status != "empty", (c.status, c.error)


def test_saitama_1_reworded_child_without_a_photo_is_not_a_zero():
    # 写真の無い子でも、数字の入った項目（日付など）が 1 つでもあれば確定しない
    html = _reworded_child(_fx(SAI1_CHILD))
    html = html.replace("<img", "<span").replace('alt="R8-17"', "")
    assert _one(SAI1, html).status != "empty"


def test_saitama_1_unlabelled_photo_alone_is_not_a_zero():
    # 雛形に子の写真だけが足された日（項目の中身は空のまま）
    html = _swap(_fx(SAI1_ZERO), "<h2>返還申請について</h2>", '<img src="./p003138_d/img/290_s.jpg" alt="R8-18"><h2>返還申請について</h2>')
    assert _one(SAI1, html).status != "empty"


def test_saitama_1_template_gone_is_not_a_zero():
    # 雛形の書き方が変わった（0 頭の日の正の根拠が無い）日は 0 頭と言わない
    html = _swap(_fx(SAI1_ZERO), "収容日：", "保護日：")
    assert _one(SAI1, html).status != "empty"


def test_saitama_1_without_the_heading_is_not_a_zero():
    html = _swap(_fx(SAI1_ZERO), "迷子の犬を保護しています", "お知らせ")
    assert _one(SAI1, html).status != "empty"


def test_saitama_2_reworded_child_is_not_a_zero():
    html = _fx(SAI2_OLD_CHILD)
    for old, new in (("管理番号 R08-58", "整理番号 R08-58"), ("管理番号 R08-60", "整理番号 R08-60"), ("収容日：令和", "保護日：令和")):
        html = _swap(html, old, new)
    c = _one(SAI2, html)
    assert c.status != "empty", (c.status, c.error)


def test_saitama_2_template_with_a_photo_is_not_a_zero():
    html = _fx(SAI2_ZEROS[0]).replace("</body>", "")
    html = _swap(html, "管理番号 R06-</p>", "管理番号 R06-</p><p><img src=\"./p019971_d/img/150_s.jpg\" alt=\"R8-70\"></p>")
    assert _one(SAI2, html).status != "empty"
