"""公開中のサイトの総点検（2026-11-13 夜）のうち、収集で崩れていた値を直す（ネットワークなし）。

- PDF の表のセル内の改行: 和文どうしの間は詰める（香川 さぬき動物愛護センター「スクスク成 長しています」55 件）
- 丸数字（①②③）を NFKC で数字に潰さない（福井「メス:4匹①②③⑤」が「メス:4匹1235」になっていた）
- 高崎市の「毛色・首輪」の列: 毛色は最後の「・」より前、首輪は備考に「首輪：…」（「茶・無」57 件）。項目の頭に足す文字（prefix）をレシピで書けるようにする
- 函館どうなん動物愛護センター（nyantomo）: 名前の頭の施設名（「函館 かぐら」「道南愛護センター みゆき」）を外す
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe, _norm_text, _pdf_cell
from collector.recipe_schema import validate_recipe_dict
from collector.registry import Source

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("raw,want", [
    ("・スタッフに美味しいご飯をもらってスクスク成\n長しています\n・明るく元気", "・スタッフに美味しいご飯をもらってスクスク成長しています ・明るく元気"),
    ("人懐っこい性格の子で\nす♪", "人懐っこい性格の子です♪"),
    ("8中-\nD0155", "8中- D0155"),            # 和文どうしでなければ今までどおり空白
    ("元気です。\n人が好き", "元気です。 人が好き"),
    (None, ""),
])
def test_pdf_cell_joins_japanese_line_breaks_when_the_recipe_asks(raw, want):
    assert _pdf_cell(raw, join_ja=True) == want


def test_pdf_cell_keeps_line_breaks_as_spaces_by_default():
    # 神奈川県（pref_kanagawa-5）の PDF はセル内の改行で句を区切る（「他は白\n未去勢」）。既定では詰めない
    assert _pdf_cell("ハチワレ、他は白\n未去勢、耳カットなし") == "ハチワレ、他は白 未去勢、耳カットなし"


def test_only_sanuki_joins_japanese_line_breaks():
    have = sorted(p.stem for p in (ROOT / "recipes").glob("*.yaml") if "join_ja_lines: true" in p.read_text(encoding="utf-8"))
    assert have == ["sanuki_kagawa"]


@pytest.mark.parametrize("raw,want", [
    ("メス:4匹①②③⑤ オス:2匹④⑥", "メス:4匹①②③⑤ オス:2匹④⑥"),
    ("成猫①~⑤1才~3才", "成猫①~⑤1才~3才"),
    ("ＡＢＣ　１２３", "ABC 123"),           # 全角英数・全角空白は今までどおり半角に
    ("  ", None),
])
def test_text_normalization_keeps_circled_numbers(raw, want):
    assert _norm_text(raw) == want


TAKASAKI = """<table>
<tr><th>受付日時</th><th>管理番号</th></tr>
<tr><th>令和8年8月19日</th><td>2026-11</td><td>令和8年8月15日 十文字町</td><td>雑種</td><td>メス・小型・高齢</td><td>茶・無</td><td>・歯が三分の一ほど抜けている</td></tr>
<tr><th>令和8年9月24日</th><td>2026-12</td><td>令和8年9月21日 中里町</td><td>雑種</td><td>オス・中型・10才</td><td>白が多い・革製青色</td><td></td></tr>
<tr><th>令和8年9月25日</th><td>2026-13</td><td>令和8年9月22日 箕郷町</td><td>雑種</td><td>オス・中型・3才</td><td>黒</td><td>人懐こい</td></tr>
<tr><th>令和8年9月26日</th><td>2026-14</td><td>令和8年9月23日 箕郷町</td><td>雑種</td><td>オス・中型・3才</td><td>首輪無</td><td>おとなしい</td></tr>
</table>"""


@pytest.mark.parametrize("slug", ["city_takasaki-3", "city_takasaki-4", "city_takasaki-5", "city_takasaki-6"])
def test_takasaki_color_and_collar_are_split(slug):
    path = ROOT / "recipes" / f"{slug}.yaml"
    assert validate_recipe_dict(yaml.safe_load(path.read_text(encoding="utf-8")), "https://www.city.takasaki.gunma.jp/") == []
    recipe = Recipe.load(path)
    fields = {k: recipe.fields[k] for k in ("color", "note")}
    r = Recipe.from_dict({"rows": "table tr:has(td)", "fields": {"management_no": {"selector": "td:nth-of-type(1)"}, **fields}})
    src = Source(slug="t", name="t", municipality="高崎市", prefecture="群馬県", url="https://x.jp/a/", kind="sheltered", species="dog")
    got = [(a["color"], a["note"]) for a in build(src, r, [Doc(url=src.url, html=TAKASAKI, soup=BeautifulSoup(TAKASAKI, "lxml"))]).animals]
    assert got == [("茶", "・歯が三分の一ほど抜けている 首輪：無"), ("白が多い", "首輪：革製青色"),
                   ("黒", "人懐こい"), (None, "おとなしい 首輪：無")]


def test_prefix_is_a_valid_field_key_and_only_applies_to_a_value():
    r = Recipe.from_dict({"rows": "li", "fields": {"note": {"selector": "span", "prefix": "首輪："}}})
    src = Source(slug="t", name="t", municipality="m", prefecture="群馬県", url="https://x.jp/a/", kind="sheltered", species="dog")
    html = "<ul><li><span>赤</span><img src='/a.jpg'></li><li><span></span><img src='/b.jpg'></li></ul>"
    got = [a["note"] for a in build(src, r, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))]).animals]
    assert got == ["首輪：赤", None]
    ok = {"rows": "li", "fields": {"note": {"selector": "span", "prefix": "首輪："}}}
    assert validate_recipe_dict(ok, "https://x.jp/a/") == []
    bad = {"rows": "li", "fields": {"note": {"selector": "span", "prefix": 3}}}
    assert validate_recipe_dict(bad, "https://x.jp/a/") != []


NYANTOMO = """<div>{}</div>"""
CARD = ('<div class="jet-listing-grid__item"><img src="/{i}.jpg"><div class="elementor-element-64868d36">'
        '<div class="jet-listing-dynamic-field__content">{name}</div></div><p>函館市愛護センター</p></div>')


def test_nyantomo_name_drops_the_facility_prefix():
    src = Source(slug="nyantomo", name="函館どうなん動物愛護センター（里親募集）", municipality="函館どうなん動物愛護センター",
                 prefecture="北海道", url="https://nyantomo.jp/donanhakodate/", kind="adoption", species="cat")
    recipe = Recipe.load(ROOT / "recipes" / "nyantomo.yaml")
    names = ["函館 かぐら", "道南 しじみ", "道南愛護センター みゆき", "ミキ", "函館太郎"]
    html = NYANTOMO.format("".join(CARD.format(i=i, name=n) for i, n in enumerate(names)))
    got = [a["name"] for a in build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))]).animals]
    assert got == ["かぐら", "しじみ", "みゆき", "ミキ", "函館太郎"]
