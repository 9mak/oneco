"""T521（2026-10-05）越谷市 保護犬・保護猫のテスト（ネットワークなし）。

表の見出し行の書き方が日によって違う（2023: tbody の td、2024: thead の th と tbody の td、2026: thead に見出しと値の 2 行）。
label で読むと 2023 は隣の見出し「収容期限」を値に取り、2024 は値が取れなかった。0 頭の日に残る番号「000」の空の雛形は
中身の無い 1 頭として載っていた。Wayback の保存 3 版を fixture にして固定する。
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run(slug: str, fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / src.recipe), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fields(a: dict) -> tuple:
    return tuple(a.get(k) for k in ("management_no", "shelter_date", "location", "breed", "sex", "age", "color", "size", "note"))


def test_koshigaya_header_row_written_with_td_cells():
    res = _run("city_koshigaya-1", "t521_koshigaya-1_wb20230925.html")
    assert [_fields(a) for a in res.animals] == [
        ("011", "令和5年9月15日", "越谷市大字南荻島地内", "ミニチュア・ダックスフンド", "めす", "高齢", "茶", "小型", "首輪なし")]
    assert res.animals[0]["image_url"].endswith("/dog-011small.jpg")   # 写真が表の後ろにある作り


def test_koshigaya_header_in_thead_and_values_in_tbody():
    res = _run("city_koshigaya-1", "t521_koshigaya-1_wb20240920.html")
    assert [_fields(a) for a in res.animals] == [
        ("001", "令和6年9月2日", "越谷市野島地内", "トイ・プードル", "メス", "中齢", "茶", "中型", "首輪なし マイクロチップなし")]
    assert res.animals[0]["image_url"].endswith("/0902inudog01.jpg")


def test_koshigaya_zero_day_with_leftover_template_000_is_empty():
    res = _run("city_koshigaya-1", "t521_koshigaya-1_wb20250327.html")
    assert res.animals == [] and res.empty_confirmed


def test_koshigaya_cat_page_uses_the_same_reading():
    # 保護猫（-2）は同じテンプレート。同じ fixture を猫の台帳で読んでも、項目が同じに取れる（種別は台帳の固定値）
    res = _run("city_koshigaya-2", "t521_koshigaya-1_wb20240920.html")
    assert [_fields(a) for a in res.animals] == [
        ("001", "令和6年9月2日", "越谷市野島地内", "トイ・プードル", "メス", "中齢", "茶", "中型", "首輪なし マイクロチップなし")]
