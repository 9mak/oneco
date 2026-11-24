"""一覧の並びを新しい順に（POLICY.md 方針 40。2026-11-24 おまえさん決定。ネットワークなし）。

- 区分の順（里親募集 → 保護中 → 迷子 → 探してます）は今のまま
- 各区分の中は、日付のある子を新しい順 → 日付の無い子（掲載元の順）。写真の有無では並べない
- 同じ日付の子は掲載元の順を保つ。読めない値・日付として成り立たない値は「日付の無い子」
- 年の無い日付は、データの日付より後の月日なら前の年、そうでなければ同じ年
"""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_sort_1124", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
SAGA = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = SAGA["animals"][0]
REF = date(2026, 11, 24)


@pytest.mark.parametrize("raw,want", [
    ("2026/11/02", date(2026, 11, 2)),
    ("2026-11-02", date(2026, 11, 2)),
    ("2026.11.2", date(2026, 11, 2)),
    ("2026年11月2日", date(2026, 11, 2)),
    ("令和8年11月2日", date(2026, 11, 2)),
    ("R8.11.2", date(2026, 11, 2)),
    ("令和元年5月1日", date(2019, 5, 1)),
    ("令和8(2026)年 11月11日", date(2026, 11, 11)),         # 西暦の併記（本番データにある書き方）
    ("R7 8/27 午前10時頃", date(2025, 8, 27)),              # 年と月日の区切りが空白
    ("2026年11月2日午後3時頃", date(2026, 11, 2)),        # 時刻・時間帯の注記は捨てる
    ("令和8年11月2日午前9時30分頃", date(2026, 11, 2)),
    ("2026年11月2日9時~11時半", date(2026, 11, 2)),
    ("2026年11月2日(日曜日)", date(2026, 11, 2)),
    ("R8.11/2 午後2時頃", date(2026, 11, 2)),
    ("R8.11.2 09:30", date(2026, 11, 2)),
    ("  2026/11/02  ", date(2026, 11, 2)),
    ("11月2日", date(2026, 11, 2)),                         # 年の無い日付: データの日付以前なら同じ年
    ("11月24日", date(2026, 11, 24)),
    ("11月2日(水)", date(2026, 11, 2)),
    ("11/2", date(2026, 11, 2)),
    ("11月25日", date(2025, 11, 25)),                       # データの日付より後の月日なら前の年
    ("12月3日", date(2025, 12, 3)),
    ("1月5日", date(2026, 1, 5)),
])
def test_shelter_date_readable_forms(raw: str, want: date):
    assert B.parse_shelter_date(raw, REF) == want


@pytest.mark.parametrize("raw", [None, "", "  ", "不明", "令和8年", "令和9年11", "2026年13月2日", "2月30日", "11月", "先月", "2026",
                                 "2020年12月初旬", "令和8年3月中旬", "R5年11月下旬", "2014年3月",   # 日が無い書き方は推測しない
                                 "R83/19", "20267/3"])                                           # 年と月日の境が決められない書き方
def test_shelter_date_unreadable_is_none(raw: Any):
    assert B.parse_shelter_date(raw, REF) is None


def test_yearless_feb_29_in_non_leap_year_is_none():
    assert B.parse_shelter_date("2月29日", date(2026, 11, 24)) is None   # 2026 年に 2/29 は無い（推測しない）


def _a(id_: str, **kw: Any) -> dict[str, Any]:
    return {**BASE, "id": id_, **kw}


def _order(tmp_path: Path, animals: list[dict[str, Any]]) -> list[str]:
    data = {"date": "2026-11-24", "animals": animals, "sources": SAGA["sources"]}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    B.build(p, out, CONFIG)
    h = (out / "pref" / "佐賀県" / "index.html").read_text(encoding="utf-8")
    return re.findall(r'<a class="card" href="/animals/([^/]+)/"', h)


def test_newest_first_then_undated_in_source_order_within_each_kind(tmp_path: Path):
    animals = [
        _a("adop_nodate01", kind="adoption", shelter_date=None),
        _a("adop_old00001", kind="adoption", shelter_date="2026/10/01"),
        _a("adop_nophoto1", kind="adoption", shelter_date=None, image_url=None),
        _a("adop_new00001", kind="adoption", shelter_date="令和8年11月20日"),
        _a("shel_old00001", kind="sheltered", shelter_date="2026年11月1日"),
        _a("shel_nodate01", kind="sheltered", shelter_date="不明"),
        _a("shel_new00001", kind="sheltered", shelter_date="11月23日"),
        _a("lost_new00001", kind="lost", shelter_date="2026-11-22"),
        _a("lost_old00001", kind="lost", shelter_date="2026-11-01"),
    ]
    assert _order(tmp_path, animals) == [
        "adop_new00001", "adop_old00001", "adop_nodate01", "adop_nophoto1",   # 日付あり（新しい順）→ 日付なし（掲載元の順。写真の有無は見ない）
        "shel_new00001", "shel_old00001", "shel_nodate01",
        "lost_new00001", "lost_old00001",
    ]


def test_same_date_keeps_source_order(tmp_path: Path):
    animals = [_a(f"same_{i:07d}", kind="sheltered", shelter_date=f"2026/11/0{1 + i % 2}") for i in range(6)]
    assert _order(tmp_path, animals) == [
        "same_0000001", "same_0000003", "same_0000005", "same_0000000", "same_0000002", "same_0000004"]


def test_yearless_dates_use_data_date_to_pick_the_year(tmp_path: Path):
    animals = [_a("y_dec00000001", shelter_date="12月3日"),     # 2025-12-03
               _a("y_nov00000001", shelter_date="11月2日"),     # 2026-11-02
               _a("y_jan00000001", shelter_date="1月5日")]      # 2026-01-05
    assert _order(tmp_path, animals) == ["y_nov00000001", "y_jan00000001", "y_dec00000001"]


def test_photo_no_longer_decides_order(tmp_path: Path):
    animals = [_a("nophoto00001", kind="adoption", image_url=None), _a("photo0000001", kind="adoption")]
    assert _order(tmp_path, animals) == ["nophoto00001", "photo0000001"]
