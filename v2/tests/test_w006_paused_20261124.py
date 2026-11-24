"""W006 方針 22 の当てはめ（2026-11-24・ネットワークなし）: 募集を一時止めていると書かれた子は載せない（掲載元が再開したら戻る）。

奥州「（受付一時停止）」・埼玉県 南支所「（募集停止中です）」・鳥取市「【治療のため募集一時停止】」・
埼玉県の犬と本所の猫「（現在募集を停止しています）」・福岡県動愛センターの状態「募集一時停止」。
トライアル中・お見合い中・譲渡調整中だけ・お声がかかりました、だけの子は方針で決まっていないので今までどおり載せる。
fixture は 2026-11-24 の保存ページ（奥州・南支所の猫・福岡県動愛 団体猫）と既存の保存ページ。
"""

import re
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _nos(c: Collected) -> list[str]:
    return [(a["management_no"] or "").split("(")[0].strip() for a in c.result.animals]


OSHU = "w006_pref_iwate_oshu_20261124.html"
MINAMI = "w006_pref_saitama_joto_neko_minami_20261124.html"
DOUAI8 = "w006_zaidan_fukuoka_douai-8_20261124.html"


# --- 岩手県 奥州 ---------------------------------------------------------------------------------
def test_oshu_paused_cats_are_not_listed_but_the_rest_are() -> None:
    h = _fx(OSHU)
    assert h.count("（受付一時停止）") == 2
    c = _run("pref_iwate_oshu", h)
    assert c.status == "ok", c.error
    nos = _nos(c)
    assert "R8-9-2" not in nos and "R8-9-3" not in nos
    assert len(nos) == 4   # 募集中の 4 頭だけ（受付一時停止の 2 頭と、決まった子の見出しの下の 2 頭が外れる）


def test_oshu_adjusting_without_the_pause_mark_is_still_listed() -> None:
    h = _fx(OSHU).replace("（受付一時停止）", "")
    c = _run("pref_iwate_oshu", h)
    assert c.status == "ok", c.error
    assert {"R8-9-2", "R8-9-3"} <= set(_nos(c)) and len(c.result.animals) == 6


def test_oshu_page_where_every_cat_is_paused_or_decided_is_zero_not_failed() -> None:
    h = _fx(OSHU).replace("【譲渡】新しい飼い主さんを募集しています", "【譲渡調整中】新しい飼い主さんを募集しています（受付一時停止）")
    c = _run("pref_iwate_oshu", h)
    assert c.result.animals == []
    assert c.status == "empty", (c.status, c.error)


# --- 埼玉県 -------------------------------------------------------------------------------------
def test_saitama_minami_cat_with_stop_mark_is_not_listed_and_the_day_is_zero_not_failed() -> None:
    # 2026-11-24: C76 が「お声がかかりました！（募集停止中です）」、C77・C78 は「譲渡されました！」= 載せる子がいない日
    h = _fx(MINAMI)
    assert h.count("募集停止中です") == 1
    c = _run("pref_saitama_joto_neko_minami", h)
    assert c.result.animals == []
    assert c.status == "empty", (c.status, c.error)


def test_saitama_minami_cat_called_for_without_the_stop_mark_is_still_listed() -> None:
    h = _fx(MINAMI).replace("<br />\n\t\t\t（募集停止中です）", "")
    assert "募集停止" not in h
    c = _run("pref_saitama_joto_neko_minami", h)
    assert c.status == "ok", c.error
    assert _nos(c) == ["南2026-C76"]


def test_saitama_honsho_cat_with_stop_mark_is_not_listed() -> None:
    h = _fx("t519_saitama_joto_neko_honsho.html")
    base = _run("pref_saitama_joto_neko_honsho", h)
    assert len(base.result.animals) == 2
    h2 = h.replace("<strong>募集中です</strong>", "<strong>お声がかかりました！（現在募集を停止しています）</strong>", 1)
    c = _run("pref_saitama_joto_neko_honsho", h2)
    assert _nos(base)[0] not in _nos(c) and len(c.result.animals) == 1


def test_saitama_dog_with_stop_mark_is_not_listed() -> None:
    h = _fx("t519_saitama_joto_inu.html")
    base = _run("pref_saitama_joto_inu", h)
    h2 = h.replace("ロッキー\xa0<font color=\"#c51f1f\">飼い主さん募集中です！", "ロッキー\xa0<font color=\"#c51f1f\">お声がかかりました！（現在募集を停止しています）", 1)
    c = _run("pref_saitama_joto_inu", h2)
    assert len(c.result.animals) == len(base.result.animals) - 1


def test_saitama_dog_called_for_without_the_stop_mark_is_still_listed() -> None:
    h = _fx("t519_saitama_joto_inu.html")
    base = _run("pref_saitama_joto_inu", h)
    c = _run("pref_saitama_joto_inu", h.replace("ロッキー\xa0<font color=\"#c51f1f\">飼い主さん募集中です！", "ロッキー\xa0<font color=\"#c51f1f\">お声がかかりました！", 1))
    assert len(c.result.animals) == len(base.result.animals)


# --- 鳥取市 -2 ----------------------------------------------------------------------------------
def test_tottori_paused_for_treatment_are_not_listed() -> None:
    h = _fx("t519v_g7_tottori-2_20261007.html")
    assert h.count("治療のため募集一時停止") == 2
    c = _run("city_tottori-2", h)
    assert c.status == "ok", c.error
    names = {a["name"] for a in c.result.animals}
    assert not ({"ねね", "べんけい"} & names)
    assert len(c.result.animals) == 16
    assert {"アル", "らん", "ひばり"} <= names   # トライアル中は今までどおり載せる


def test_tottori_paused_mark_after_another_mark_is_not_listed() -> None:
    h = _fx("t519v_g7_tottori-2_20261007.html")
    pat = re.compile("【治療のため募集一時停止\u200b?】")   # 実ページには 1 つ零幅空白が混ざる
    c0 = _run("city_tottori-2", pat.sub("【里親募集中】", h))
    assert len(c0.result.animals) == 18
    c = _run("city_tottori-2", pat.sub("【NEW!】【治療のため募集一時停止】", h))
    assert len(c.result.animals) == 16


# --- 福岡県動愛センター -------------------------------------------------------------------------
def test_fukuoka_douai_paused_animal_is_not_listed() -> None:
    h = _fx(DOUAI8)
    base = _run("zaidan_fukuoka_douai-8", h)
    assert base.status == "ok" and len(base.result.animals) == 3   # 募集中 2・トライアル中 1（トライアル中は今までどおり載せる）
    c = _run("zaidan_fukuoka_douai-8", h.replace('status05">トライアル中<', 'status05">募集一時停止<'))
    assert len(c.result.animals) == 2


def test_fukuoka_douai_every_animal_paused_is_zero_not_failed() -> None:
    h = re.sub(r'(ico-animal status\d+">)[^<]+<', r"\1募集一時停止<", _fx(DOUAI8))
    c = _run("zaidan_fukuoka_douai-8", h)
    assert c.result.animals == []
    assert c.status == "empty", (c.status, c.error)
