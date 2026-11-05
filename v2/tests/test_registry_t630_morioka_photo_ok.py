"""W006 T630: 盛岡市保健所（返事 2026-11-05）。保護動物・迷子動物の情報は写真を含め表示してよい、示した表示方法も問題ない。"""

from pathlib import Path

import pytest
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


@pytest.mark.parametrize("slug", ["city_morioka-1", "city_morioka-2"])
def test_photo_ok(slug):
    assert SOURCES[slug].photo == "ok"
    assert SOURCES[slug].mode == "recipe"


def test_iwate_prefecture_page_is_untouched():
    # URL に /morioka/ を含むが県央保健所のページで、盛岡市の返事の対象ではない
    assert SOURCES["pref_iwate_kennan"].photo == "ok"
    assert SOURCES["pref_iwate_kennan"].municipality != "盛岡市保健所"
