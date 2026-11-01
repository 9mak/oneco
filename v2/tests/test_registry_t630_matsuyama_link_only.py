"""W006 T630: 松山市 はぴまるの丘の返事（2026-10-22。収容動物は頻繁に更新されるので、リンクのみの掲載にしてほしい）。

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


def test_matsuyama_is_link_only_without_photo():
    s = SOURCES["city_matsuyama"]
    assert (s.mode, s.enabled, s.photo) == ("link_only", True, "no")
    assert s.url == "https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html"
    assert s.recipe == "recipes/city_matsuyama.yaml" and s.recipe_path.exists()


def test_matsuyama_collect_does_not_fetch():
    assert collect_one(SOURCES["city_matsuyama"], _NoFetch()).status == "link_only"
