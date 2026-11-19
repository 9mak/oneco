"""W006 T630（写真表示のお伺いへの返事 2026-11-17〜18 と、飼い主が探している迷子のページの扱い）。

越谷市（11/17 動物管理センター）: 「保護・収容した動物（犬・猫）の情報」は写真等を掲載して問題ない。
  譲渡のページを広告つきで載せることも問題ない（譲渡の 2 ページは別の PR で足す）。
久留米市（11/18 動物愛護センター）: 写真等の転載はしないでほしい。所在地と電話番号の記載、市のホームページへのリンクの設置は問題ない。
  栃木・岐阜・甲府と同じく安全側で、一覧は読まず（写真も文字も転記しない）リンクだけを載せる。所在地と電話は可と明記されたので残す。
旭川市あにまある「飼い主が探している」3 ページ: 飼い主の方が届け出た迷子の告知なので、返事にかかわらず写真は出さない
  （町田市 -2〜-4・鳥取県 -2・前橋市 -2 と同じ扱い。11/20 の追伸でそう伝える）。
"""

from pathlib import Path

import pytest
import yaml
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
RAW = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
NOTES = {d["slug"]: d.get("note") or "" for d in RAW}

KOSHIGAYA = ["city_koshigaya-1", "city_koshigaya-2"]
KURUME = ["city_kurume-1", "city_kurume-2"]
ASAHIKAWA_LOST = ["spec_douaicenter-9", "spec_douaicenter-10", "spec_douaicenter-11"]


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


@pytest.mark.parametrize("slug", KOSHIGAYA)
def test_koshigaya_sheltered_pages_show_photos(slug):
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.kind, s.photo) == ("recipe", True, "sheltered", "ok")
    assert "2026-11-17" in NOTES[slug] and "T630" in NOTES[slug]
    assert "確認中" not in NOTES[slug]          # 11/16 の「確認中」の記録を残さない


def test_koshigaya_kojin_stays_link_only():
    # 個人保護のページは 11/16 の返事のまま（11/17 の返事はリンクを外すかに触れていない）
    s = SOURCES["city_koshigaya_kojin"]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)


@pytest.mark.parametrize("slug", KURUME)
def test_kurume_is_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)
    assert s.recipe_path.exists()               # 許諾が変わったときのために残す
    assert "2026-11-18" in NOTES[slug] and "T630" in NOTES[slug]
    # 所在地と電話番号の記載は問題ないと返事にある
    assert s.phone == "0942-30-1500" and s.address == "福岡県久留米市百年公園1番2号"


@pytest.mark.parametrize("slug", KURUME)
def test_kurume_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


@pytest.mark.parametrize("slug", ASAHIKAWA_LOST)
def test_asahikawa_lost_pages_never_show_photos(slug):
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.kind, s.photo) == ("recipe", True, "lost", "no")
    assert "2026-11-19" in NOTES[slug] and "T630" in NOTES[slug]


def test_asahikawa_other_pages_are_untouched():
    # 迷子以外のページ（返事待ち）は pending のまま
    others = [s for s in SOURCES.values() if s.slug.startswith("spec_douaicenter-") and s.slug not in ASAHIKAWA_LOST]
    assert others and all(s.photo == "pending" for s in others), [(s.slug, s.photo) for s in others]
