"""W006 T630（写真表示のお伺いへの回答 2026-11-10・11）: 山梨県と新潟市動物愛護センターはリンクのみにする。

山梨県動物愛護指導センターは写真だけでなく文字の内容も載せないでほしい、
新潟市動物愛護センターは表示しないでほしい（センターのページへのリンクは載せてほしい）との返事。
どちらも一覧は読まず（写真も文字も転記しない）、情報源一覧のリンクだけを残す。
レシピは許諾が変わったときのために残す。
"""

from pathlib import Path

import pytest
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}

SLUGS = [f"pref_yamanashi-{i}" for i in range(1, 7)] + [f"city_niigata-{i}" for i in range(1, 5)]


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


@pytest.mark.parametrize("slug", SLUGS)
def test_link_only_without_photo(slug):
    s = SOURCES[slug]
    assert (s.mode, s.photo, s.enabled) == ("link_only", "no", True)
    assert s.recipe_path.exists()        # 許諾が変わったときのために残す


@pytest.mark.parametrize("slug", SLUGS)
def test_collect_does_not_fetch(slug):
    assert collect_one(SOURCES[slug], _NoFetch()).status == "link_only"


# 甲府市（city_kofu-1・-2）は 11/12 にお伺いを送り返事まで pending にしていた。
# 2026-11-16 の返事でリンクのみになったので test_registry_w006_t630_replies_1116.py へ移した。


def test_ikutopia_is_unchanged():
    # 新潟市動物ふれあいセンター（いくとぴあ）は別の窓口で、写真の表示は可の返事（2026-10）
    s = SOURCES["ikutopia-1"]
    assert (s.mode, s.photo) == ("recipe", "ok")
