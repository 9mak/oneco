"""公開中のサイトの表示と日本語の総点検（2026-11-13 夜。Codex と agy に本番の生成物を読ませた指摘を、本番で裏取りして直す。ネットワークなし）。

おまえさん「ところどころ表示とか日本語とかがおかしいから徹底調査して」「全部治そうぜ」。
- 名前の欄に元ページの見出しや番号が入った子（「犬 探しています(フルサワ)」「譲渡猫R7ねー35」「べティちゃん ※現在…」）は、それを名前として出さない
- 種別も品種も毛色も無い子（奈良市・呉市）の見出しは、バッジと重なる「里親募集の子」ではなく「種類の記載なし」
- 品種や毛色の欄に性別・年齢の語が入った子（「雌（オス）」「避妊雌の猫」「子猫の猫」）は、それを見出しに使わない
- 下の行に年齢の「不明」や単位の無い数字を出さない。見出しに性別を出しても手術の注記は残す。何も無ければ管理番号で見分けられるようにする
- 表記: 性別のかっこ書き・日付・年齢・大きさを、意味が変わらない範囲でそろえる（data.json の値は掲載元のまま）
- 区分に合わない注意書き（探してますの子に「譲渡・返還されている場合」）、内部の言葉（「取れている情報」・サイト内 ID）を直す
- 絞り込みで犬猫以外の子を選べるようにし、写真の alt がカードの文字と重ならないようにする
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_review_1113", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
SAGA = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = SAGA["animals"][0]       # 佐賀県・保護中の犬・雑種・オス・推定約5歳・黒茶(長毛)・写真あり


def _a(**kw: Any) -> dict[str, Any]:
    return {**BASE, **kw}


# --- 名前の欄に入った、名前でないもの ------------------------------------------------------------------------------------
@pytest.mark.parametrize("kw,want", [
    # 旭川市あにまある: 告知の見出しが名前の欄に入る。本当の名前は備考の「名前:あの」
    ({"name": "犬 探しています(フルサワ)", "note": "・名前:あの ・首輪なし", "breed": "チワワ", "sex": "オス"}, "あの"),
    ({"name": "猫 探しています。(カネマキ)", "note": "首輪なし 臆病な性格 名前:まめ", "breed": None, "species": "cat"}, "まめ"),
    ({"name": "猫 保護しています(コダマ)", "note": None, "breed": None, "color": "黒", "species": "cat", "sex": "不明"}, "黒の猫"),
    # 福島市: 名前の欄が「譲渡猫」＋管理番号
    ({"name": "譲渡猫R7ねー35", "management_no": "R7ねー35", "breed": "雑種", "sex": "おす"}, "雑種（オス）"),
    # 高知県・和歌山市: 名前の後ろの「※」の注記
    ({"name": "べティちゃん ※現在アシストファーム南国店にいます"}, "べティちゃん"),
    ({"name": "コロ※"}, "コロ"),
    ({"name": "モモ1", "management_no": "1"}, "モモ1"),                 # 短い番号が名前に含まれるだけでは捨てない（#124 reviewer F-09）
])
def test_things_that_are_not_names_are_not_used_as_the_name(kw, want):
    assert B.headline(_a(**kw)) == want


def test_detail_table_shows_the_cleaned_name(tmp_path: Path):
    out = _build(tmp_path, [_a(id="furusawa0001", name="犬 探しています(フルサワ)", note="・名前:あの ・首輪なし", kind="lost"),
                            _a(id="fukushima001", name="譲渡猫R7ねー35", management_no="R7ねー35")])
    assert "<dt>名前</dt><dd>あの</dd>" in _page(out, "furusawa0001")
    assert "探しています" not in _page(out, "furusawa0001").split("<dt>名前</dt>")[1][:40]
    assert "<dt>名前</dt>" not in _page(out, "fukushima001")
    assert "<dt>管理番号</dt><dd>R7ねー35</dd>" in _page(out, "fukushima001")


# --- 見出し: 何も分からない子・欄の取り違え ------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["adoption", "sheltered", "stray", "lost"])
def test_animal_with_nothing_known_is_not_called_by_its_kind(kind):
    a = _a(kind=kind, name=None, species=None, breed=None, color=None, sex=None)
    assert B.headline(a) == "種類の記載なし"
    assert B.headline({**a, "sex": "オス"}) == "種類の記載なし（オス）"


@pytest.mark.parametrize("kw,want", [
    ({"breed": "雌", "sex": "雄", "species": "dog", "color": None}, "犬（オス）"),       # 佐賀: 品種の欄に「雌」
    ({"breed": None, "color": "避妊雌", "species": "cat", "sex": "メス"}, "猫（メス）"),   # 千葉市: 毛色の欄に「避妊雌」
    ({"breed": None, "color": "子猫", "species": "cat", "sex": "メス"}, "猫（メス）"),     # 船橋市: 毛色の欄に「子猫」
    ({"breed": None, "color": "茶色、縞模様あり", "species": "cat", "sex": "オス"}, "猫（オス）"),   # 特徴の文
    ({"breed": None, "color": "黒、白", "species": "cat", "sex": "メス"}, "黒、白の猫（メス）"),  # 読点だけの多色は毛色（#124 reviewer F-03）
    ({"breed": "MIX(品種不明)", "sex": "オス"}, "雑種（オス）"),                          # 横須賀市
    ({"breed": "ミックス（不明）", "sex": "メス"}, "雑種（メス）"),
])
def test_headline_ignores_sex_and_age_words_in_breed_and_color(kw, want):
    assert B.headline(_a(name=None, **kw)) == want


# --- 下の行 --------------------------------------------------------------------------------------------------------------
def test_subline_does_not_show_unknown_age_or_bare_numbers():
    assert B.subline(_a(breed="雑種", sex="オス", color="黒", age="不明")) == "黒"
    assert B.subline(_a(breed="雑種", sex="オス", color="黒", age="10")) == "黒"            # 沖縄: 単位の無い「推定年齢 10」
    assert "不明" not in B.subline(_a(name="こお", breed="雑種", sex="不明", age="不明"))


def test_subline_keeps_the_surgery_note_when_the_sex_is_in_the_headline():
    a = _a(breed="雑種", sex="オス(去勢手術済)", color=None, age="3歳")
    assert B.headline(a) == "雑種（オス）"
    assert B.subline(a) == "去勢手術済 / 3歳"


def test_named_animal_subline_writes_sex_with_full_width_parentheses():
    a = _a(name="小鉄", breed=None, sex="オス(去勢手術済)", age="2026年6月6日")
    assert B.subline(a) == "オス（去勢手術済） / 2026年6月6日生まれ"


def test_subline_falls_back_to_the_management_number():
    # 熊本県動愛: 写真を止めていて名前も無い子が同じ見た目で並ぶ（agy「クローンカード」）
    a = _a(breed="雑種", sex="オス", color=None, age=None, management_no="MN00361")
    assert B.subline(a) == "管理番号 MN00361"


# --- 表記 ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,want", [
    ("雄(去勢済み)", "オス（去勢済み）"),
    ("オス(去勢手術済)", "オス（去勢手術済）"),
    ("♀", "メス"),
    ("めす（不妊手術済み）", "メス（不妊手術済み）"),
    ("去勢雄", "去勢オス"),
    ("オス (去勢済)", "オス（去勢済）"),
    ("避妊雌", "避妊メス"),
    ("雌雄不明", "雌雄不明"),
    ("メス:4匹 オス:2匹", "メス:4匹 オス:2匹"),
])
def test_sex_is_written_the_same_way(raw, want):
    assert B.disp_sex(raw) == want


@pytest.mark.parametrize("raw,want", [
    ("2026/7/23", "2026年7月23日"),
    ("2026/05/19", "2026年5月19日"),
    ("2026-11-12", "2026年11月12日"),
    ("2026.11.10", "2026年11月10日"),
    ("令和7年10月23日", "2025年10月23日"),
    ("R8.11.12", "2026年11月12日"),
    ("R3.11/16", "2021年11月16日"),
    ("2026年11月10日", "2026年11月10日"),
    ("R8.7/17 午後4時頃", "R8.7/17 午後4時頃"),          # 時刻や注記の付いた値は元のまま
    ("8月17日", "8月17日"),                              # 年の無い日付は年を補わない
    ("令和8年(2026年)11月11日", "令和8年(2026年)11月11日"),
])
def test_plain_dates_are_written_the_same_way(raw, want):
    assert B.disp_value("shelter_date", raw) == want


@pytest.mark.parametrize("raw,want", [
    ("R8.8.15", "2026年8月15日生まれ"),
    ("2026年5月15日", "2026年5月15日生まれ"),
    ("12才", "12歳"),
    ("5~6才", "5〜6歳"),
    ("1才~3才", "1歳〜3歳"),
    ("5歳5ヵ月", "5歳5か月"),
    ("約3ヶ月", "約3か月"),
    ("3カ月齢", "3か月齢"),
    ("推定3歳", "推定3歳"),
    ("2025年6月頃生まれ(推定)", "2025年6月頃生まれ(推定)"),
    ("10", "10（単位の記載なし）"),
    ("推定 2026年6月6日", "2026年6月6日生まれ（推定）"),        # 徳島「推定生年月日」（レシピの prefix。#124 reviewer F-01）
    ("推定 令和8年6月1日", "2026年6月1日生まれ（推定）"),
    ("2099年11月22日", "2099年11月22日"),                    # 今日より後の日付は「生まれ」と言わない（掲載元の誤記）
    ("推定 2099年11月22日", "推定 2099年11月22日"),
])
def test_ages_are_written_the_same_way(raw, want):
    assert B.disp_age(_a(age=raw)) == want


@pytest.mark.parametrize("slug", ["douai_tokushima-2", "douai_tokushima-3", "city_takasaki-8"])
def test_recipes_with_an_estimated_birth_date_mark_it(slug):
    # 掲載元の項目名が「推定生年月日」「推定誕生月」の欄は、値の頭に「推定 」を付けて build に伝える（#124 reviewer F-01）
    lines = (ROOT / "recipes" / f"{slug}.yaml").read_text(encoding="utf-8").splitlines()
    assert 'prefix: "推定 "' in next(line for line in lines if line.strip().startswith("age:"))


@pytest.mark.parametrize("raw,want", [("中", "中型"), ("小", "小型"), ("大", "大型"), ("3~4kg", "3〜4kg"), ("中型", "中型")])
def test_sizes_are_written_the_same_way(raw, want):
    assert B.disp_value("size", raw) == want


def test_age_words_in_the_size_field_move_to_the_age():
    a = _a(age=None, size="生後1か月前後", species="cat")      # 千葉市
    assert B.disp_age(a) == "生後1か月前後" and B.disp_field(a, "size") == ""
    b = _a(age=None, size="仔", species="cat")
    assert B.disp_age(b) == "子猫" and B.disp_field(b, "size") == ""
    c = _a(age="2歳", size="成猫", species="cat")                # 年齢があれば両方そのまま（大きさの欄の語を捨てない。#124 reviewer F-04）
    assert B.disp_age(c) == "2歳" and B.disp_field(c, "size") == "成猫"
    d = _a(age="不明", size="成猫", species="cat")               # 年齢が「不明」なら大きさの欄の語を年齢に
    assert B.disp_age(d) == "成猫" and B.disp_field(d, "size") == ""


# --- 個体ページ ----------------------------------------------------------------------------------------------------------
def _build(tmp_path: Path, extra: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None) -> Path:
    data = {"date": "2026-11-13", "animals": SAGA["animals"] + extra, "sources": sources or SAGA["sources"]}
    p = tmp_path / "latest.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    B.build(p, out, CONFIG)
    return out


def _page(out: Path, id_: str) -> str:
    return (out / "animals" / id_ / "index.html").read_text(encoding="utf-8")


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def _desc(html: str) -> str:
    return BeautifulSoup(html, "lxml").find("meta", attrs={"name": "description"})["content"]


def test_fine_print_matches_the_kind(tmp_path: Path):
    out = _build(tmp_path, [_a(id="lost00000001", kind="lost"), _a(id="adopt0000001", kind="adoption"),
                            _a(id="stray0000001", kind="stray")])
    lost, adopt, stray = (_text(_page(out, i)) for i in ("lost00000001", "adopt0000001", "stray0000001"))
    assert "譲渡" not in lost and "すでに見つかっている場合があります" in lost
    assert "すでに譲渡先が決まっている場合があります" in adopt
    assert "すでに飼い主さんの元に戻ったり、譲渡されたりしている場合があります" in stray


def test_detail_does_not_talk_about_internal_things(tmp_path: Path):
    out = _build(tmp_path, [_a(id="mgmt00000001", management_no="26-0470"), _a(id="nomgmt000001", management_no=None)])
    h = _page(out, "mgmt00000001")
    assert "取れている情報" not in h and "<h2>基本情報</h2>" in h
    assert "<code>" not in h and "このサイトの中だけの番号" not in h
    assert "管理番号「26-0470」をお伝えください" in _text(h)
    assert "管理番号「" not in _text(_page(out, "nomgmt000001"))


def test_animal_with_no_fields_points_to_the_source_page(tmp_path: Path):
    nara = _a(id="nara00000001", name=None, species=None, breed=None, color=None, sex=None, age=None, size=None,
              management_no=None, shelter_date=None, location=None, note=None, kind="adoption")
    t = _text(_page(_build(tmp_path, [nara]), "nara00000001"))
    assert "写真以外の項目は取れていません" not in t
    assert "詳しい情報は自治体のページでご確認ください" in t
    assert "里親募集の子" not in t


def test_meaningless_notes_stay_out_of_the_description_too(tmp_path: Path):
    out = _build(tmp_path, [_a(id="notemu000001", note="無"), _a(id="noteyu000001", note="有"),
                            _a(id="notedot00001", age="高齢と思われます。", note="温厚な性格です。")])
    assert not _desc(_page(out, "notemu000001")).endswith("無")
    assert "<dt>備考</dt>" not in _page(out, "noteyu000001")
    assert "。。" not in _desc(_page(out, "notedot00001"))


def test_photo_alt_on_cards_is_empty_and_detail_alt_reads_naturally(tmp_path: Path):
    out = _build(tmp_path, [_a(id="altdog000001", municipality="町田市", prefecture="東京都"),
                            _a(id="altname00001", name="ポチ", municipality="町田市", prefecture="東京都")])
    pref = (out / "pref" / "東京都" / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'<img src="[^"]+" alt="([^"]*)"', pref) == ["", ""]     # カードはリンクの文字で読めるので写真は飾り
    assert 'alt="雑種の犬（オス）"' in _page(out, "altdog000001")
    assert 'alt="ポチ（犬）"' in _page(out, "altname00001")


def test_no_photo_message_does_not_claim_there_is_no_photo(tmp_path: Path):
    h = _page(_build(tmp_path, [_a(id="nophoto00001", image_url=None)]), "nophoto00001")
    assert "写真はありません" not in h and "写真は自治体のページでご確認ください" in h


# --- 一覧・トップ・情報源・404 ------------------------------------------------------------------------------------------
def test_pref_page_names_the_other_animals_and_offers_a_filter_for_them(tmp_path: Path):
    out = _build(tmp_path, [_a(id="bird00000001", species="other", breed="セキセイインコ"),
                            _a(id="none00000001", species=None, breed=None, color=None)])
    h = (out / "pref" / "佐賀県" / "index.html").read_text(encoding="utf-8")
    assert "ほか" not in _desc(h)
    assert "その他の動物 1 頭" in _desc(h) and "種類の記載なし 1 頭" in _desc(h)
    assert "犬猫の区別なし" not in h
    assert 'data-value="other"' in h
    assert '<div class="chips" role="group" aria-label="動物の種類">' in h
    assert '<div class="chips" role="group" aria-label="掲載の区分">' in h
    assert 'aria-live="polite"' in h
    assert "この条件に当てはまる掲載はありません。" in h and "当てはまる子はいません" not in h


def test_index_wording(tmp_path: Path):
    out = _build(tmp_path, [_a(id="none00000002", species=None, breed=None, color=None)])
    t = _text((out / "index.html").read_text(encoding="utf-8"))
    assert "区分の意味：" in t and "区分の意味:" not in t
    assert "飼い主が分からない" not in t and "飼い主さんが分からないまま保護されている子" in t
    assert "犬猫の区別なし" not in t and "種類の記載なし" in t


def test_index_lists_prefectures_with_nothing_today(tmp_path: Path):
    t = _text((_build(tmp_path, []) / "index.html").read_text(encoding="utf-8"))
    assert "本日の掲載が無い都道府県：" in t and "島根県" in t and "佐賀県、" not in t.split("本日の掲載が無い都道府県：")[1][:200]


def test_sources_page_does_not_call_other_animal_pages_dogs_and_cats(tmp_path: Path):
    src = {**SAGA["sources"][0], "slug": "asahikawa-other", "name": "旭川市あにまある（飼い主が探している その他の動物）",
           "municipality": "旭川市あにまある", "species": "mixed", "kind": "lost", "status": "empty"}   # 台帳の種別は mixed
    out = _build(tmp_path, [], SAGA["sources"] + [src])
    h = (out / "sources" / "index.html").read_text(encoding="utf-8")
    li = next(x for x in BeautifulSoup(h, "lxml").select("li.src") if "その他の動物" in x.get_text())
    meta = li.select_one(".src-meta").get_text(" ", strip=True)
    assert "犬・猫" not in meta and "その他の動物" in meta
    assert "旭川市あにまある" not in meta                    # 名前に自治体名があれば下の行で重ねない
    t = _text(h)
    assert "自治体側の更新やページ構造の変化で" not in t and "接続できなかったり" in t
    assert "確認済み" not in t.split("情報源（自治体ページ）の一覧")[1][:200]


def test_404_does_not_guess_why_the_page_is_gone(tmp_path: Path):
    t = _text((_build(tmp_path, []) / "404.html").read_text(encoding="utf-8"))
    assert "譲渡・返還された子のページは翌日には無くなります" not in t
    assert "自治体のページから掲載が無くなった子のページは、翌日の更新で消えます" in t


def test_css_stacks_facts_on_narrow_screens_and_keeps_small_text_readable():
    css = B.CSS
    assert "max(11px" not in css and ".ph span{font-size:max(13px" in css
    assert re.search(r"@media \(max-width:\d+px\)\{\.facts>div\{grid-template-columns:1fr", css)
    assert "-webkit-line-clamp:2" in css


def test_title_of_an_animal_with_nothing_known_says_what_it_is(tmp_path: Path):
    # 見出しは「種類の記載なし」のまま、タイトルには区分を足して何のページか分かるようにする（#124 reviewer F-06）
    nara = _a(id="nara00000002", name=None, species=None, breed=None, color=None, sex=None, kind="adoption", municipality="奈良市", prefecture="奈良県")
    h = _page(_build(tmp_path, [nara]), "nara00000002")
    assert "<title>里親募集の動物・種類の記載なし｜奈良市｜oneco</title>" in h
    assert "<h1>種類の記載なし</h1>" in h


def test_unknown_filter_in_the_url_falls_back_to_all():
    # 「その他」のボタンが無い県に ?species=other で来たら「すべて」に戻す（#124 reviewer F-10）
    assert "data-value=\"'+state.species+'\"" in B.PREF_JS or "state.species='all'" in B.PREF_JS


def test_url_filter_values_are_not_put_into_a_selector():
    # ?species=a"b のような値でセレクタが壊れてスクリプトが止まらないように、ボタンの値と比べる（#124 reviewer G-01）
    assert "[data-value=\"'+state" not in B.PREF_JS and "dataset.value===state[k]" in B.PREF_JS


def test_lost_animal_with_nothing_known_has_a_natural_title(tmp_path: Path):
    a = _a(id="lostnone0001", name=None, species=None, breed=None, color=None, sex=None, kind="lost", municipality="町田市", prefecture="東京都")
    assert "<title>飼い主さんが探している動物・種類の記載なし｜町田市｜oneco</title>" in _page(_build(tmp_path, [a]), "lostnone0001")


def test_estimated_unknown_age_is_just_unknown():
    assert B.disp_age(_a(age="推定 不明")) == "不明" and B.card_age(_a(age="推定 不明")) == ""


def test_takasaki_estimated_birth_month_has_no_day():
    import yaml
    spec = yaml.safe_load((ROOT / "recipes" / "city_takasaki-8.yaml").read_text(encoding="utf-8"))["fields"]["age"]
    m = re.search(spec["regex"], "令和8年6月1日")
    assert m and m.group(1) == "令和8年6月" and spec["prefix"] == "推定 "
