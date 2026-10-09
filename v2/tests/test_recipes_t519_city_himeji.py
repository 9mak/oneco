"""T519: 姫路市 迷子のペット情報掲示板（city_himeji-1）のレシピ（ネットワークなし）。

t519_city_himeji-1.html は 2026-10-05 のページから本文（h2「現在掲載中のペット」を含む div）だけを抜いたもの（犬 1 件 + 見本の猫）。
複数件が並ぶ日は実物が無いので、同じ作りの猫 1 件を足した合成で確かめる（合成と分かるようテスト内で作る）。
"""

import json
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
BASE = "https://www.city.himeji.lg.jp/kurashi/cmsfiles/contents/0000031/31472/"


def _source(slug: str) -> Source:
    return next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)


def _run(html: str):
    src = _source("city_himeji-1")
    recipe = Recipe.load(ROOT / "recipes" / "city_himeji-1.yaml")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _fixture() -> str:
    return (FIX / "t519_city_himeji-1.html").read_text(encoding="utf-8")


def test_himeji_takes_the_posted_dog_and_skips_the_sample_cat():
    res = _run(_fixture())
    assert len(res.animals) == 1
    a = res.animals[0]
    assert a["species"] == "dog"
    assert a["image_url"] == BASE + "20260326inu1.jpg"
    assert (a["breed"], a["sex"], a["age"], a["color"], a["size"]) == ("雑種", "メス", "9歳8ヶ月", "全身茶色で腹・尻尾の先・足先が白", "中")
    assert a["shelter_date"] == "令和8年3月29日 午後8時"
    assert a["note"] == "令和8年3月20日姫路市玉手3丁目付近で犬が逃げたので探しています。"
    assert "neko.jpg" not in json.dumps(res.animals, ensure_ascii=False)


def test_himeji_never_carries_the_posters_email_address():
    res = _run(_fixture())
    assert "takuma" not in json.dumps(res.animals, ensure_ascii=False)
    assert "gmail" not in json.dumps(res.animals, ensure_ascii=False)


def test_himeji_second_posting_gets_its_own_photo_and_species():
    cat = (
        '<div class="mol_textblock"><p><em>猫を探しています。</em></p></div>'
        '<div class="mol_imageblock"><div><img alt="探している猫" src="./cmsfiles/contents/0000031/31472/cat1.jpg"></div></div>'
        '<div class="mol_tableblock"><table><caption>令和8年9月1日姫路駅付近</caption><tbody>'
        '<tr><th scope="row">逸走日時</th><td>令和8年9月1日</td></tr>'
        '<tr><th scope="row">ペットの種別</th><td>猫</td></tr>'
        '<tr><th scope="row">種類</th><td>三毛</td></tr>'
        '<tr><th scope="row">性別</th><td>メス</td></tr>'
        '<tr><th scope="row">連絡先</th><td>nyan(a)example.jp</td></tr></tbody></table></div>'
    )
    marker = '<a class="anchor" id="index-2-33"'
    html = _fixture().replace(marker, cat + marker, 1)
    assert cat in html
    res = _run(html)
    assert [a["species"] for a in res.animals] == ["dog", "cat"]
    assert res.animals[0]["image_url"] == BASE + "20260326inu1.jpg"
    assert res.animals[1]["image_url"] == BASE + "cat1.jpg"
    assert (res.animals[1]["breed"], res.animals[1]["sex"]) == ("三毛", "メス")
