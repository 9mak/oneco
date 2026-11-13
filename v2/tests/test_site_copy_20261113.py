"""サイトの文言と表示の違和感を直す（2026-11-13 おまえさん「全体的に違和感がある文字列とか表示」。ネットワークなし）。

- 名前の無い子の見出し: バッジに「犬」「里親募集」があるのに見出しも「里親募集の犬」だった → 品種と性別（「ミニチュア・シュナウザー（オス）」）。
  品種が分からなければ毛色と種別（「茶白の猫（メス）」）、それも無ければ種別（「犬（オス）」）。下の行は見出しと重ねない
- 許諾待ち・不可で写真を止めている子は「写真はありません」ではなく「写真は自治体のページで見られます」
- 表記ゆれ: 性別の 雄・雌・おす・めす → オス・メス、品種の 雑・MIX・ミックス(雑種) 等 → 雑種
- 自治体名に県名が入っているときは後ろに（県名）を重ねない（「愛知県動物愛護センター（わんにゃんナビ）（愛知県）」）
- 備考が「無」「募集中」だけの子は備考を出さない
- 半角のコロン（「時点:」「掲載元:」「データ確認日:」）を全角に、「この情報は 2026年11月13日 に」の空白を詰める
- 熊本県動愛の各子の電話番号（収容先の保健所ごと）は備考ではなく電話に出す（レシピの phone 項目を子の電話にする）
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_copy_1113", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
SAGA = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = SAGA["animals"][0]       # 佐賀県・保護中の犬・雑種・オス・推定約5歳・黒茶(長毛)・写真あり


def _a(**kw: Any) -> dict[str, Any]:
    return {**BASE, **kw}


# --- 見出し ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kw,want", [
    ({"name": "ポチ"}, "ポチ"),
    ({"breed": "ミニチュア・シュナウザー", "sex": "オス"}, "ミニチュア・シュナウザー（オス）"),
    ({"breed": "雑種(ミックス)", "sex": "メス"}, "雑種（メス）"),
    ({"breed": "MIX", "sex": "雄"}, "雑種（オス）"),
    ({"breed": "雑", "sex": "めす"}, "雑種（メス）"),
    ({"breed": None, "color": "茶白", "species": "cat", "sex": "メス"}, "茶白の猫（メス）"),
    ({"breed": "その他", "color": None, "species": "dog", "sex": "オス"}, "犬（オス）"),
    ({"breed": "猫", "color": "白", "species": "cat", "sex": "オス"}, "白の猫（オス）"),     # 品種の欄に種別しか無い子
    ({"breed": None, "color": None, "species": "dog", "sex": None}, "犬"),
    ({"breed": "柴犬", "sex": "不明"}, "柴犬"),                                              # 性別が不明なら付けない
    ({"breed": "雑種", "sex": "オス(去勢済)"}, "雑種（オス）"),                               # かっこを重ねない
    ({"breed": "雑種", "sex": "メス（不妊手術済み）"}, "雑種（メス）"),
    ({"breed": "雑種", "sex": "去勢オス"}, "雑種（去勢オス）"),
    ({"breed": "雑種(柴風)", "sex": "メス"}, "雑種(柴風)・メス"),
    ({"breed": "雑種", "sex": "メス:4匹1235 オス:2匹46 不明:2匹78"}, "雑種"),               # 複数頭をまとめた欄は見出しに出さない（#123 F-02）
    ({"breed": "雑種", "sex": "オス1匹 2匹目は不明、確認できていない"}, "雑種"),
    ({"breed": None, "color": "不明", "species": "cat", "sex": "オス"}, "猫（オス）"),        # 毛色が「不明」なら「不明の猫」としない
    ({"breed": None, "color": "黒白(おひげ模様)", "species": "cat", "sex": "メス"}, "黒白(おひげ模様)の猫・メス"),
    ({"breed": None, "color": None, "species": "other", "sex": None}, "動物"),
    ({"breed": None, "color": None, "species": None, "sex": None}, "種類の記載なし"),          # 種別も何も無い子（区分で呼ぶとバッジと重なる。test_site_review_20261113.py）
])
def test_headline_uses_breed_and_sex_not_the_kind(kw, want):
    assert B.headline(_a(**kw)) == want


@pytest.mark.parametrize("kind", ["adoption", "sheltered", "stray", "lost"])
def test_headline_does_not_repeat_the_kind_badge(kind):
    h = B.headline(_a(kind=kind, name=None))
    assert not any(w in h for w in ("里親募集", "保護中", "迷子", "探して"))


def test_subline_does_not_repeat_what_the_headline_says():
    a = _a(breed="雑種", sex="オス", age="推定約5歳", color="黒茶(長毛)")
    assert B.subline(a) == "黒茶(長毛) / 推定約5歳"
    named = _a(name="ポチ", breed="柴犬", sex="雄", age="3歳")
    assert B.subline(named) == "柴犬 / オス / 3歳"
    by_color = _a(breed=None, color="茶白", species="cat", sex="メス", age="子猫")
    assert B.subline(by_color) == "子猫"
    many = _a(breed="雑種", color=None, sex="メス:4匹 オス:2匹", age=None)    # 見出しに出さなかった性別の欄は下の行に出す
    assert B.headline(many) == "雑種" and B.subline(many) == "メス:4匹 オス:2匹"
    unknown = _a(breed=None, color="不明", species="cat", sex="メス", age=None)  # 下の行に「不明」だけを出さない（#123 F-06）
    assert B.headline(unknown) == "猫（メス）" and B.subline(unknown) == ""


# --- サイト全体を組む ----------------------------------------------------------------------------------------------
def _build(tmp_path: Path) -> Path:
    extra = [
        _a(id="withheld0001", source="pref_saga-pending"),                       # 写真を止めている掲載元（許諾待ち）の、写真のある子
        _a(id="nophoto00001", image_url=None),                                   # 掲載元にも写真が無い子
        _a(id="aichi0000001", municipality="愛知県動物愛護センター（わんにゃんナビ）", prefecture="愛知県", kind="adoption"),
        _a(id="machida00001", municipality="町田市", prefecture="東京都"),
        _a(id="notenone0001", note="無"),
        _a(id="notewant0001", note="募集中"),
        _a(id="notereal0001", note="首輪（赤）"),
        _a(id="sexkanji0001", sex="雌", breed="MIX"),
    ]
    sources = SAGA["sources"] + [{**SAGA["sources"][0], "slug": "pref_saga-pending", "photo": "pending"}]
    data = {"date": "2026-11-13", "animals": SAGA["animals"] + extra, "sources": sources}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    B.build(p, out, CONFIG)
    return out


def _page(out: Path, id_: str) -> str:
    return (out / "animals" / id_ / "index.html").read_text(encoding="utf-8")


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def test_withheld_photo_says_the_photo_is_on_the_source_page(tmp_path: Path):
    out = _build(tmp_path)
    w = _page(out, "withheld0001")
    assert "写真は自治体のページで見られます" in w and "写真はありません" not in w
    n = _page(out, "nophoto00001")
    assert "写真は自治体のページでご確認ください" in n and "写真は自治体のページで見られます" not in n   # 無いとは言い切らない（test_site_review_20261113.py）
    # 一覧のカードも同じ
    pref = (out / "pref" / "佐賀県" / "index.html").read_text(encoding="utf-8")
    assert "写真は自治体のページで見られます" in pref
    # data.json には内部の印を出さず、写真の URL も出さない
    data = json.loads((out / "data.json").read_text(encoding="utf-8"))
    w_row = next(a for a in data["animals"] if a["id"] == "withheld0001")
    assert w_row["image_url"] is None and not any(k.startswith("_") for k in w_row)


def test_municipality_with_the_prefecture_in_its_name_does_not_repeat_it(tmp_path: Path):
    out = _build(tmp_path)
    assert "愛知県動物愛護センター（わんにゃんナビ）（愛知県）" not in _page(out, "aichi0000001")
    assert '<p class="muni">愛知県動物愛護センター（わんにゃんナビ）</p>' in _page(out, "aichi0000001")
    assert '<p class="muni">町田市（東京都）</p>' in _page(out, "machida00001")


def test_meaningless_notes_are_not_shown(tmp_path: Path):
    out = _build(tmp_path)
    assert "<dt>備考</dt>" not in _page(out, "notenone0001")
    assert "<dt>備考</dt>" not in _page(out, "notewant0001")
    assert "<dt>備考</dt><dd>首輪（赤）</dd>" in _page(out, "notereal0001")


def test_sex_and_breed_are_written_the_same_way(tmp_path: Path):
    h = _page(_build(tmp_path), "sexkanji0001")
    assert "<dt>性別</dt><dd>メス</dd>" in h and "<dt>種類</dt><dd>雑種</dd>" in h


def test_titles_and_alts_do_not_nest_parentheses(tmp_path: Path):
    h = _page(_build(tmp_path), "machida00001")
    title = re.search(r"<title>([^<]+)</title>", h).group(1)
    assert title == "雑種（オス）｜町田市｜oneco"
    assert "）（" not in h
    assert 'alt="雑種の犬（オス）"' in h        # 写真の alt には種別を足す（読み上げで犬か猫か分かる。#123 F-03）。自治体名は本文にあるので重ねない


def test_only_kumamoto_recipes_read_a_phone_per_animal():
    # 子ごとの電話を読むのは熊本県動物愛護センターだけ。三重（mie_dakc）は運営元の電話・所在地の組なので読まない（#123 F-01）
    have = sorted(p.stem for p in (ROOT / "recipes").glob("*.yaml") if re.search(r"(?m)^  phone:", p.read_text(encoding="utf-8")))
    assert have == ["kumamoto_doubutuaigo-1", "kumamoto_doubutuaigo-2", "kumamoto_doubutuaigo-7", "kumamoto_doubutuaigo-8"]


def test_colons_are_full_width_and_dates_are_not_spaced(tmp_path: Path):
    out = _build(tmp_path)
    index = (out / "index.html").read_text(encoding="utf-8")
    pref = (out / "pref" / "佐賀県" / "index.html").read_text(encoding="utf-8")
    page = _page(out, "machida00001")
    assert "時点：" in _text(index) and "時点:" not in _text(index)
    assert "掲載元：" in _text(pref) and "掲載元:" not in _text(pref)
    assert "データ確認日：" in _text(page) and "データ確認日:" not in _text(page)
    assert "この情報は2026年11月13日に自治体のページから取得" in _text(page)
    srcs = (out / "sources" / "index.html").read_text(encoding="utf-8")
    assert "2026年11月13日に確認した" in _text(srcs)


# --- 熊本県動愛: 子ごとの電話番号 ------------------------------------------------------------------------------------------
KUMA_LIST = """<ul class="list-4col"><li><a href="/animals/detail/1"><img src="/img/1.jpg"></a><dl>
<dt>収容日</dt><dd>2026年11月1日</dd><dt>種類</dt><dd>雑種(ミックス)</dd><dt>性別</dt><dd>オス</dd>
<dt>個体管理ナンバー</dt><dd>DC00240</dd><dt>保健所</dt><dd>水俣保健所</dd><dt>電話番号</dt><dd>0966-63-4104</dd></dl></li></ul>"""


@pytest.mark.parametrize("slug", ["kumamoto_doubutuaigo-1", "kumamoto_doubutuaigo-2", "kumamoto_doubutuaigo-7", "kumamoto_doubutuaigo-8"])
def test_kumamoto_phone_goes_to_the_contact_not_the_note(slug):
    from collector.registry import load_sources
    src = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}[slug]
    recipe = Recipe.load(ROOT / src.recipe)
    assert "phone" in recipe.fields and "電話番号" not in str(recipe.fields.get("note") or "")


def test_recipe_phone_field_overrides_the_ledger_phone_only_when_read():
    src = Source(slug="t", name="t", municipality="熊本県動物愛護センター", prefecture="熊本県", url="https://x.jp/a/",
                 kind="adoption", species="cat", phone=None)
    recipe = Recipe.from_dict({"rows": "ul.list-4col li", "image": "img@src",
                               "fields": {"management_no": {"label": "個体管理ナンバー"},
                                          "phone": {"label": "電話番号", "regex": r"(0\d{1,4}-\d{1,4}-\d{3,4})"}}})
    doc = Doc(url=src.url, html=KUMA_LIST, soup=BeautifulSoup(KUMA_LIST, "lxml"))
    (a,) = build(src, recipe, [doc]).animals
    assert a["phone"] == "0966-63-4104"
    blank = KUMA_LIST.replace("0966-63-4104", "")
    (b,) = build(src, recipe, [Doc(url=src.url, html=blank, soup=BeautifulSoup(blank, "lxml"))]).animals
    assert b["phone"] is None                       # 読めなければ台帳の値（ここでは無し）のまま
    src2 = Source(**{**src.__dict__, "phone": "096-380-3153"})
    (c,) = build(src2, recipe, [Doc(url=src.url, html=blank, soup=BeautifulSoup(blank, "lxml"))]).animals
    assert c["phone"] == "096-380-3153"


def test_kumamoto_municipality_is_not_an_abbreviation():
    from collector.registry import load_sources
    for s in load_sources(ROOT / "registry" / "sources.yaml"):
        if s.slug.startswith("kumamoto_doubutuaigo-"):
            assert s.municipality == "熊本県動物愛護センター", s.slug
