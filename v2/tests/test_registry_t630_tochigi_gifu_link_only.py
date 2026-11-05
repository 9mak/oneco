"""W006 T630: 栃木県動物愛護指導センター（返事 2026-11-04）と岐阜市（返事 2026-11-02）をリンクのみにする。

栃木: 収容・譲渡動物の画像やスクリーンショットの転載は遠慮してほしい（返還・譲渡済みの子をすみやかに取り下げる必要がある）。
掲載するなら当該ページへのリンクのみ。
岐阜: 今後は市のホームページの該当箇所へリンクする形で。写真だけの話とも読めるが、堺・松山と同じく安全側で文字も外す。
レシピは残す（許諾が変わったときに mode を戻せば読める）。
"""

from pathlib import Path

import pytest
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

SLUGS = [
    "douai_pref_tochigi_puppy-1",
    "douai_pref_tochigi_puppy-2",
    "spec_douai_pref_tochigi",
    "spec_douai_pref_tochigi_stray-1",
    "spec_douai_pref_tochigi_stray-2",
    "city_gifu-1",
    "city_gifu-2",
    "city_gifu-3",
]


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


@pytest.mark.parametrize("slug", SLUGS)
def test_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.enabled, s.photo) == ("link_only", True, "no")
    assert s.recipe_path.exists()


@pytest.mark.parametrize("slug", SLUGS)
def test_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"
