"""W006 T640 掲載漏れ 2 回目 A-3: 要確認の 5 件のうち、台帳に無い子の一覧だった分（2026-11-17・ネットワークなし）。

確かめた結果:
- 香川県 西讃・中讃の「迷い犬・迷い猫の情報」（HTML）: PDF の読み落としではない。西讃の PDF のページは「公開期間は収容日の翌日から 7 日間」の最新の収容動物（今日は 2640152〜2640165）で、
  HTML は公開期間を過ぎても保護が続いている子（2640145・2640144 は 11/5・11/4 収容で、7 日たって PDF から外れた子）。別の一覧なので足す（pref_kagawa_html-2・3）。
- 町田市「収容動物のお知らせ」: hogo.html（city_machida-1）とは別の子（収容動物のお知らせは今日の猫 1 頭。保護情報の猫 2 頭とは保護日・場所が違う）。足す（city_machida-5）。
- 山梨県「飼い主募集中」（be_a_foster.html）: 台帳の 6 ページの入口ではなく譲渡の条件のページ。動物の一覧は別ページ（譲渡対象の犬 /doubutsu/dog/・猫 /doubutsu/cats/）で、
  台帳の 6 ページ（保護・迷子）には無い。山梨県は 11/11 に文字も載せないでほしいと返事 → 同じくリンクのみで足す（pref_yamanashi-7・8）。
- 鳥取県「犬・猫の譲渡情報」（220718.htm）: 動物の一覧が無い案内のハブ（写真 5 枚はロゴ・アイコン）なので足さない。
"""

import dataclasses
from pathlib import Path

import yaml
from bs4 import BeautifulSoup
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str, **kw) -> Collected:
    src = dataclasses.replace(SOURCES[slug], **kw) if kw else SOURCES[slug]
    return collect_one(src, FakeFetcher({src.url: html}))


def _hits(slug: str, html: str):
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return empty_hits(recipe, [Doc(url=SOURCES[slug].url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 香川県 迷い犬・迷い猫の情報（HTML）------------------------------------------
KG_CHU, KG_SEI = "pref_kagawa_html-2", "pref_kagawa_html-3"


def test_kagawa_registry():
    for slug, phone, name in ((KG_CHU, "0877-24-9964", "中讃"), (KG_SEI, "0875-25-4383", "西讃")):
        s = SOURCES[slug]
        assert s.mode == "recipe" and s.enabled and s.kind == "stray" and s.prefecture == "香川県" and s.species == "mixed", slug
        assert s.phone == phone and name in s.municipality and s.recipe_path.exists(), slug
        assert s.url.endswith("/maigo_info.html"), slug
        assert s.photo == "pending", slug  # 香川県の規約は無断転載禁止のみ（2026-11-22 方針 1・2: 可の返事も規約の可も無いので、確認が取れるまで出さない）


def test_kagawa_seisan_html_has_the_animals_the_pdf_no_longer_shows():
    html = _fx("w006_pref_kagawa_html-3_20261117.html")
    c = _run(KG_SEI, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"] for a in animals] == ["2640145", "2640144", "2640141", "2640122", "2640112"]
    assert [a["species"] for a in animals] == ["cat", "dog", "dog", "dog", "dog"]
    first = animals[0]
    assert (first["shelter_date"], first["location"], first["breed"], first["color"], first["sex"], first["size"], first["age"]) == (
        "令和8年11月5日", "三豊市詫間町大浜", "雑種", "白キジ", "オス", "中", "1歳前後")
    assert "カギ尻尾" in first["note"] and all(a["image_url"] for a in animals)
    # 西讃の PDF のページ（pref_kagawa_pdf-3）は「公開期間は収容日の翌日から 7 日間」の最新の収容動物だけ。11/5・11/4 収容の 2640145・2640144 は 11/17 には
    # 公開期間（11/6〜11/12・11/5〜11/11）を過ぎて PDF から外れているが、保健所はまだ保護している（HTML の一覧に残る）。実際に 11/17 の PDF を読むと 2640152〜2640165 の 12 頭
    pdf_page = _fx("w006_pref_kagawa_pdf-3_page_20261117.html")
    assert "公開期間は収容日の翌日から" in pdf_page and "7日間" in pdf_page.replace("\n", "").replace(" ", "")
    assert _hits(KG_SEI, html) == []


def test_kagawa_chusan_html_skips_the_returned_animal():
    html = _fx("w006_pref_kagawa_html-2_20261117.html")
    assert "2630327" in html and "飼い主さんに返還されました" in html
    c = _run(KG_CHU, html)
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [a["management_no"] for a in animals] == ["2630306", "2630301"]
    assert all(a["species"] == "dog" and a["image_url"] for a in animals)
    assert (animals[0]["breed"], animals[0]["color"], animals[0]["sex"], animals[0]["age"]) == ("雑種", "黒白", "オス", "5~10歳")
    assert animals[0]["shelter_date"].startswith("令和8年10月27日") and "有岡集会場" in animals[0]["location"]
    assert "リードは保健所のもの" in animals[1]["note"]


def test_kagawa_other_days_in_wayback():
    c = _run(KG_SEI, _fx("w006_pref_kagawa_html-3_child_wb20250423.html"))
    assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == ["2540011"], c.error
    c = _run(KG_CHU, _fx("w006_pref_kagawa_html-2_child_wb20250327.html"))
    assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == ["2430497", "2430445"], c.error
    c = _run(KG_CHU, _fx("w006_pref_kagawa_html-2_child_wb20250907.html"))   # 「飼い主さんに返還しました」の 1 頭は載せない
    assert c.status == "ok" and len(c.result.animals) == 2, c.error
    assert "飼い主さんに返還しました" in _fx("w006_pref_kagawa_html-2_child_wb20250907.html")
    c = _run(KG_CHU, _fx("w006_pref_kagawa_html-2_child_wb20260314.html"))
    assert c.status == "ok" and [a["management_no"] for a in c.result.animals] == ["2530650", "2530645"], c.error


def test_kagawa_zero_days_in_wayback_do_not_depend_on_the_sentence():
    # 0 頭の日（西讃 2025-09・2026-03）は「現在、掲載情報はありません」が出るが、この文は子のいる日（西讃 2025-04・中讃 2025-03）にも別の欄に出るので根拠にしない
    for name in ("w006_pref_kagawa_html-3_zero_wb20250912.html", "w006_pref_kagawa_html-3_zero_wb20260306.html"):
        html = _fx(name)
        assert "現在、掲載情報はありません" in html
        assert _zero(_run(KG_SEI, html)), name
    assert "現在、掲載情報はありません" in _fx("w006_pref_kagawa_html-3_child_wb20250423.html")
    assert not _zero(_run(KG_SEI, _fx("w006_pref_kagawa_html-3_child_wb20250423.html")))


def test_kagawa_structure_change_is_not_zero():
    html = _fx("w006_pref_kagawa_html-3_20261117.html").replace("個体管理番号", "管理番号")
    assert not _zero(_run(KG_SEI, html))
    html = _fx("w006_pref_kagawa_html-2_20261117.html").replace("個体管理番号", "管理番号")
    assert not _zero(_run(KG_CHU, html))


# --- 町田市 収容動物のお知らせ -----------------------------------------------------
MCH = "city_machida-5"


def test_machida_registry():
    s = SOURCES[MCH]
    # 2026-11-18 朝に syuyou.html が HTTP 404（市のナビからもリンクが消えた）。初日から毎晩 failed にしないため、戻るまで止める（#130 reviewer F-01）
    assert s.mode == "recipe" and not s.enabled and s.kind == "sheltered" and s.prefecture == "東京都" and s.species == "mixed"
    registry = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))
    entry = next(e for e in registry["sources"] if e["slug"] == MCH)
    assert "404" in entry["note"]
    assert s.phone == "042-722-6727" and s.recipe_path.exists()
    assert s.url.endswith("/mayoi/syuyou.html")


def test_machida_syuyou_today_is_a_different_cat_from_the_hogo_page():
    c = _run(MCH, _fx("w006_city_machida-5_20261117.html"), enabled=True)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1
    a = c.result.animals[0]
    assert (a["species"], a["sex"], a["breed"], a["size"], a["color"]) == ("cat", "おす", "雑種", "中", "茶トラ")
    assert a["shelter_date"] == "2026年11月11日" and a["location"] == "町田市能ヶ谷4丁目" and "負傷猫" in a["note"]
    # 保護情報（city_machida-1。hogo.html）の猫は保護日・場所が違う別の子
    hogo = _run("city_machida-1", _fx("w006_city_machida-1_hogo_20261117.html"))
    assert hogo.status == "ok", hogo.error
    assert all("能ヶ谷" not in (h["location"] or "") and h["shelter_date"] != a["shelter_date"] for h in hogo.result.animals)


def test_machida_syuyou_other_days_in_wayback():
    c = _run(MCH, _fx("w006_city_machida-5_child_wb20221227.html"), enabled=True)
    assert c.status == "ok", c.error
    assert [(x["species"], x["breed"]) for x in c.result.animals] == [("dog", "柴犬"), ("dog", "トイプードル")] and all(x["image_url"] for x in c.result.animals)
    c = _run(MCH, _fx("w006_city_machida-5_child_wb20230322.html"), enabled=True)
    assert c.status == "ok", c.error
    assert [(x["species"], x["breed"]) for x in c.result.animals] == [("cat", "アビシニアン")] and "移送されました" in c.result.animals[0]["note"]


def test_machida_syuyou_zero_day_is_zero_by_its_sentence():
    html = _fx("w006_city_machida-5_zero_wb20220829.html")
    assert "移送された動物の情報はありません" in html
    assert _zero(_run(MCH, html, enabled=True))
    for name in ("w006_city_machida-5_20261117.html", "w006_city_machida-5_child_wb20221227.html", "w006_city_machida-5_child_wb20230322.html"):
        assert "移送された動物の情報はありません" not in _fx(name), name   # 子のいる日には出ない
    assert _hits(MCH, _fx("w006_city_machida-5_zero_wb20220829.html")) != []


def test_machida_syuyou_structure_change_is_not_zero():
    html = _fx("w006_city_machida-5_20261117.html").replace("性別：", "性：").replace("種類：", "種：")
    c = _run(MCH, html, enabled=True)
    assert not _zero(c)


# --- 山梨県 譲渡対象の犬・猫（リンクのみ）------------------------------------------
YMN_DOG, YMN_CAT = "pref_yamanashi-7", "pref_yamanashi-8"


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


def test_yamanashi_adoption_pages_are_link_only_like_the_other_six():
    for slug, url, species in ((YMN_DOG, "https://www.pref.yamanashi.jp/doubutsu/dog/index.html", "dog"),
                               (YMN_CAT, "https://www.pref.yamanashi.jp/doubutsu/cats/index.html", "cat")):
        s = SOURCES[slug]
        assert (s.mode, s.photo, s.enabled, s.kind, s.species, s.url) == ("link_only", "no", True, "adoption", species, url), slug
        assert s.phone == "055-273-5034" and s.address and s.recipe_path.exists(), slug
        assert collect_one(s, _NoFetch()).status == "link_only", slug
    # 既存の 6 ページ（保護・迷子）の URL とは重ならない
    old = {SOURCES[f"pref_yamanashi-{i}"].url for i in range(1, 7)}
    assert SOURCES[YMN_DOG].url not in old and SOURCES[YMN_CAT].url not in old


def test_yamanashi_recipes_still_read_when_permission_changes():
    c = _run(YMN_DOG, _fx("w006_pref_yamanashi-7_20261117.html"), mode="recipe")
    assert c.status == "ok", c.error
    assert [(a["name"], a["management_no"], a["species"]) for a in c.result.animals] == [("ムラサメ", "dog8-9-3", "dog")]
    c = _run(YMN_CAT, _fx("w006_pref_yamanashi-8_20261117.html"), mode="recipe")
    assert c.status == "ok", c.error
    assert [(a["name"], a["management_no"]) for a in c.result.animals] == [("プリエ", "cat8-10-6"), ("しゃちお", "cat8-10-5"), ("ゲンキ", "cat8-11-7")]
