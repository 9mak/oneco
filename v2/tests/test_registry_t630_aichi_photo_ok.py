"""W006 T630: 愛知県動物愛護センター（わんにゃんナビ）の返事（2026-10-23）。

示した表示方法（写真は保存・加工せず元の画像を参照、出典リンク、電話・所在地は掲載元の記載のみ）で可。
条件は「譲渡済みで掲載をやめた犬猫の写真は速やかに外す」こと。毎日の収集で掲載元に無い子は翌日の公開から消え、
読めない日も前日分を保持しない（OPERATIONS.md）ので、写真を表示に戻す。
"""

from pathlib import Path

from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def test_aichi_wannyan_navi_photo_ok():
    s = SOURCES["wannyan_navi_aichi"]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "ok")
    assert s.url == "https://wannyan-navi.pref.aichi.jp/?page=list_dc"
