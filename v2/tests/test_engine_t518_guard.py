"""T518 再レビュー（2026-10-05 20:27）F-09・F-10 のテスト（ネットワークなし）。

1. 山形県: データ行を th のセルで書いた版（庄内 2023-02-06）でも子を取りこぼさない
2. 種別なしの行の守り: 種別が決まらない行は、これまで「犬か猫か分からない」で偶然捨てられていた。種別なしで載せるようにした
   ので、掲載が終わった行（「飼い主さんが見つかり、返還することができました」）と、写真が無く項目もほぼ無い行
   （0 頭の雛形に番号だけ残ったもの。佐賀 2025-12-05）は捨てる。種別が決まる行・allow_other の行には効かせない
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def _run_slug(slug: str, fixture: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, Recipe.load(ROOT / "recipes" / f"{slug}.yaml"), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def _src(species: str = "mixed") -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="山形県", url="https://x.jp/a/", kind="sheltered", species=species)


def _run(html: str, reg_species: str = "mixed", **recipe):
    r = Recipe.from_dict({"rows": "div.row", "image": "img@src",
                          "fields": {"shelter_date": {"regex": r"(\d+月\d+日)"}, "location": {"regex": r"場所[:：]\s*(\S+)"},
                                     "breed": {"regex": r"種類[:：]\s*(\S+)"}, "sex": {"regex": r"性別[:：]\s*(\S+)"}},
                          **recipe})
    return build(_src(reg_species), r, [Doc(url="https://x.jp/a/", html=html, soup=BeautifulSoup(html, "lxml"))])


# --- Wayback の別の作りの日 -----------------------------------------------------------------
def test_yamagata_rows_written_with_th_cells_are_read():
    res = _run_slug("pref_yamagata", "t518_yamagata_shonai_wb20230206.html")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert "shiba1" in (a["image_url"] or "") and "酒田" in (a["location"] or "")


def test_yamagata_returned_row_is_not_published():
    res = _run_slug("pref_yamagata", "t518_yamagata_mogami_wb20251111.html")
    assert all("返還" not in (a.get("location") or "") for a in res.animals)
    assert res.animals == []


def test_saga_template_with_leftover_number_is_not_an_animal():
    res = _run_slug("pref_saga-1", "t518_saga-1_wb20251205.html")
    assert res.animals == []
    assert res.empty_confirmed is True


# --- 種別なしの行の守り（エンジン） --------------------------------------------------------------
def test_species_none_row_with_closed_listing_phrase_is_dropped():
    html = "<div class='row'><img src='/p1.jpg'><p>10月6日 場所：新庄市 飼い主さんが見つかり、返還することができました。</p></div>"
    assert _run(html).animals == []


def test_species_none_row_without_photo_and_with_few_fields_is_dropped():
    html = "<div class='row'><p>保護動物（251118-1） 10月6日</p></div>"
    assert _run(html).animals == []


def test_species_none_row_with_photo_is_kept_even_with_few_fields():
    html = "<div class='row'><img src='/p2.jpg'><p>10月1日 保護</p></div>"
    res = _run(html)
    assert len(res.animals) == 1 and res.animals[0]["species"] is None


def test_species_none_row_without_photo_but_with_fields_is_kept():
    html = "<div class='row'><p>10月1日 場所：下松市 種類：雑種 性別：オス</p></div>"
    assert len(_run(html).animals) == 1


def test_stray_wording_like_deadline_or_found_place_is_not_treated_as_closed():
    html = ("<div class='row'><img src='/p3.jpg'><p>10月2日 場所：周南市 返還期限：10月9日 公園で見つかりました</p></div>")
    assert len(_run(html).animals) == 1


def test_guard_does_not_touch_rows_whose_species_is_known():
    html = "<div class='row'><p>犬 10月6日 飼い主さんが見つかり、返還することができました。</p></div>"
    assert len(_run(html, reg_species="dog").animals) == 1      # 種別が決まる行は従来どおり（終わった掲載はレシピで落とす）


def test_guard_does_not_touch_allow_other_rows():
    html = "<div class='row'><p>インコ 10月6日</p></div>"
    res = _run(html, species={"allow_other": True})
    assert [a["species"] for a in res.animals] == ["other"]


# --- 3 回目のゲート G-01・G-02（2026-10-05 23:10） ---------------------------------------------
def test_ninohe_adopted_dog_under_closed_heading_is_not_published():
    # 見出し「譲渡先が決まりました。」の下の譲渡済みの犬 R7-121-1 は載せない。募集中の 2 頭（見出し「【譲渡】里親さんを募集しています。」）は種別なしで載る
    res = _run_slug("pref_iwate_ninohe", "t518_ninohe_wb20260213.html")
    assert sorted(a["management_no"] for a in res.animals) == ["R6-10-4", "R6-10-5"]
    assert all(a["species"] is None for a in res.animals)


def test_species_none_row_under_closed_heading_is_dropped_but_open_heading_is_kept():
    html = ("<h2>里親さんを募集しています</h2><div class='row'><p>10月1日 場所：二戸市 種類：雑種 性別：オス</p></div>"
            "<h2>新しい家族が決まりました！</h2><div class='row'><p>9月1日 場所：二戸市 種類：雑種 性別：メス</p></div>")
    res = _run(html)
    assert [a["sex"] for a in res.animals] == ["オス"]


def test_closed_phrases_cover_common_wordings():
    from collector.extract import _CLOSED_LISTING

    for t in ("返還いたしました", "返還となりました", "譲渡先が決まりました", "里親さんが決まりました", "新しい家族が決まりました",
              "譲渡決定", "譲渡されました", "飼主が見つかりました", "飼い主様が見つかりました", "飼い主の元へ戻りました"):
        assert _CLOSED_LISTING.search(t), t


def test_closed_phrases_do_not_hit_wishes_or_conditions():
    from collector.extract import _CLOSED_LISTING

    for t in ("優しい飼い主さんが見つかりますように", "公示期間内に飼い主が見つかりませんでした", "飼い主が見つかり次第掲載を終了します",
              "飼い主の元に戻りたい", "掲載中でも、譲渡済みの場合があります", "里親さんが決まり次第お知らせします"):
        assert not _CLOSED_LISTING.search(t), t


def test_mito_empty_kind_cell_does_not_take_the_next_heading_as_breed():
    # 種別なしで載るようになった鳥の行（Wayback 2025-06 の 保護275）。種類の欄が空のとき、次の見出し「体格」を品種にしない
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == "city_mito-1")
    html = ("<div id='main_body'><table><tr><th>管理番号</th><td>保護275</td></tr><tr><td><img src='/p/275.jpg'></td></tr>"
            "<tr><th>動物</th><td>セキセイインコ</td></tr>"
            "<tr><th>種類</th><td></td><th>体格</th><td></td></tr><tr><th>年齢</th><td></td><th>毛色</th><td>頭が黄 胴が緑</td></tr>"
            "<tr><th>保護日</th><td>令和7年5月20日</td></tr></table>"
            "<table><tr><th>管理番号</th><td>保護276</td></tr><tr><th>犬種</th><td>雑種</td><th>体格</th><td>中</td></tr>"
            "<tr><th>保護日</th><td>令和7年5月21日</td></tr></table></div>")
    res = build(src, Recipe.load(ROOT / "recipes" / "city_mito-1.yaml"), [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])
    got = {a["management_no"]: (a["species"], a["breed"]) for a in res.animals}
    assert got == {"保護275": (None, None), "保護276": ("dog", "雑種")}
