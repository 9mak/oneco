"""W006 T624（見守り運転 2026-10-30 の確認）: 奈良市の収容動物の記事（soshiki/97/222574.html）が 10/16 から 404。

入口の「ペットの飼養・届出」一覧（/life/4/34/134/）からは記事へのリンク文字が消え、
市の案内ページ「ペットが迷子になったときは」（soshiki/97/8478.html）と環境省のリンク集は 222574 を指したまま。
読む先が無いので、記事が戻るまでは案内ページへのリンクだけを載せる（毎晩 failed にしない）。
レシピは案内ページから「迷子犬・迷子猫をお探しの方へ」を辿る形で残し、記事が戻ったら mode を recipe に戻す。
"""

from pathlib import Path

from collector.recipe import Recipe
from collector.registry import load_sources
from collector.run import collect_one

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


class _NoFetch:
    def get(self, *a, **k):   # 読みに行ったら失敗にする
        raise AssertionError("link_only のページを取得しようとした")


def test_nara_points_to_the_guidance_page_as_link_only():
    s = SOURCES["city_nara"]
    assert (s.mode, s.enabled, s.kind) == ("link_only", True, "sheltered")
    assert s.url == "https://www.city.nara.lg.jp/soshiki/97/8478.html"
    assert s.recipe == "recipes/city_nara.yaml" and s.recipe_path.exists()


def test_nara_collect_does_not_fetch():
    assert collect_one(SOURCES["city_nara"], _NoFetch()).status == "link_only"


def test_nara_recipe_still_follows_the_article_link_from_the_guidance_page():
    r = Recipe.load(SOURCES["city_nara"].recipe_path)
    assert r.steps and r.steps[0] == {"follow_text": "迷子犬・迷子猫をお探しの方へ"}
