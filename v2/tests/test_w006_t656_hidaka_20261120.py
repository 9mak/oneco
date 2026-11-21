"""T656 直し 1 回目・項目 4（2026-11-20・ネットワークなし）: 日高 飼い主募集（hokkaido_hidaka-1）の説明用の画像。

本文は「現在、新しい飼い主を募集している犬が２頭おります。」で、チラシ画像は 2 枚（R8犬6PPB3b・R8犬7P2）。
その後ろに、2 頭のチラシの見方を説明する画像（alt「R8犬6-7説明用」）が並び、3 頭目の犬として載っていた。
"""

from dataclasses import replace
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
LIVE = "w006_hokkaido_hidaka-1_20261120.html"


def _run(mutate=None) -> Collected:
    html = (FIX / LIVE).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    s = replace(SOURCES["hokkaido_hidaka-1"], mode="recipe")  # 台帳は #147 で link_only。レシピは許諾が変わったときのため読み続ける
    return collect_one(s, FakeFetcher({s.url: html}))


def test_explanation_image_is_not_a_dog():
    assert "説明用" in (FIX / LIVE).read_text(encoding="utf-8")
    c = _run()
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 2     # 本文の「犬が２頭」と同じ
    assert all(a["species"] == "dog" and a["location"] == "静内保健所" for a in c.result.animals)
    assert not any("説明用" in (a["image_url"] or "") or "%E8%AA%AC%E6%98%8E%E7%94%A8" in (a["image_url"] or "") for a in c.result.animals)


def test_flyers_still_read_without_the_explanation():
    # 説明用の画像が無い日（11/13 の保存ページ）も 2 頭のまま
    c = _run(lambda h: h)
    older = collect_one(replace(SOURCES["hokkaido_hidaka-1"], mode="recipe"), FakeFetcher({SOURCES["hokkaido_hidaka-1"].url: (FIX / "w006_hokkaido_hidaka-1_20261113.html").read_text(encoding="utf-8")}))
    assert older.status == "ok", older.error
    assert len(older.result.animals) == 2 and len(c.result.animals) == 2
