"""品種のかっこ書きを見出しから外す（2026-11-14 agy ③。ネットワークなし）。

「雑種(キジ白)・オス」「雑種(柴風)・メス」のように、品種のかっこ書きのせいで性別を「・」でつなぐ見出しが 26 件あった。
見出しは品種の本体と性別（「雑種（オス）」）、かっこの中は下の行に回す。本体が「不明」なら、かっこの中を品種として使う
（「不明(フレンチブルドッグ風)」→「フレンチブルドッグ風（オス）」）。詳細の表の「種類」は掲載元のまま。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_paren_1114", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
BASE: dict[str, Any] = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))["animals"][0]


def _a(**kw: Any) -> dict[str, Any]:
    return {**BASE, "name": None, "color": None, "age": None, "management_no": None, **kw}


@pytest.mark.parametrize("breed,sex,head,sub", [
    ("雑種(キジ白)", "オス", "雑種（オス）", "キジ白"),
    ("雑種(柴風)", "メス", "雑種（メス）", "柴風"),
    ("雑種(生後3か月未満)", "メス", "雑種（メス）", "生後3か月未満"),
    ("チワワ（ロングコート）", "オス", "チワワ（オス）", "ロングコート"),
    ("不明(フレンチブルドッグ風)", "オス", "フレンチブルドッグ風（オス）", ""),
    ("MIX(品種不明)", "オス", "雑種（オス）", ""),
    ("柴犬", "メス", "柴犬（メス）", ""),
    ("ミックス(キジ白)", "オス", "雑種（オス）", "キジ白"),             # 本体にも雑種の言い換え
    ("雑(メインクーン風)", None, "雑種", "メインクーン風"),
])
def test_breed_parenthesis_goes_to_the_subline(breed, sex, head, sub):
    a = _a(breed=breed, sex=sex)
    assert B.headline(a) == head
    assert B.subline(a) == sub


def test_detail_table_keeps_the_breed_as_written():
    assert B.disp_field(_a(breed="雑種(キジ白)"), "breed") == "雑種(キジ白)"


def test_parenthesis_that_repeats_the_color_or_the_sex_is_not_repeated():
    # 「雑種(茶)」＋毛色「茶」で「茶 / 茶」、「柴犬(オス)」で見出しと同じ「オス」を下の行に出さない（#125 reviewer H-02）
    assert B.subline(_a(breed="雑種(茶)", sex="オス", color="茶")) == "茶"
    assert B.subline(_a(breed="柴犬(オス)", sex="オス")) == ""
