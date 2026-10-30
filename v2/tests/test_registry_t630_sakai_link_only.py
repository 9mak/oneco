"""W006 T630: 堺市動物指導センターの返事（2026-10-29「貴ページではリンクの掲載のみでお願いいたします」）。

一覧を読まず（写真も文字も転記しない）、情報源の一覧に自治体ページへのリンクだけを載せる。
レシピは残す（許諾が変わったときに mode を戻せば読める）。誤って recipe に戻すと意向に反するので固定する。
"""

from pathlib import Path

from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


def test_sakai_is_link_only_without_photo():
    s = SOURCES["eonet_sakai-1"]
    assert (s.mode, s.enabled, s.photo) == ("link_only", True, "no")
    assert s.url == "https://www.eonet.ne.jp/~sakai-doshi/"
    assert s.recipe == "recipes/eonet_sakai-1.yaml" and s.recipe_path.exists()


def test_sakai_collect_does_not_fetch():
    assert collect_one(SOURCES["eonet_sakai-1"], _NoFetch()).status == "link_only"
