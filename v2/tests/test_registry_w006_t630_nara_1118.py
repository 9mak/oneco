"""W006 T630（写真表示のお伺いへの返事 2026-11-17）。

奈良市保健所 保健衛生課（11/17 17:30）: 11/12 にお伺いした「飼い主さん募集中！犬・猫の譲渡」（soshiki/97/10799.html）は「1. 表示してよい」。
条件は付いていない。この掲載元（city_nara-2）は写真だけの一覧なので、写真を出す（photo を既定の ok に戻す）。
"""

from pathlib import Path

import yaml
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
NOTES = {
    d["slug"]: d.get("note") or ""
    for d in yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
}


def test_nara_adoption_page_shows_photos_after_the_city_said_yes():
    s = SOURCES["city_nara-2"]
    assert s.url == "https://www.city.nara.lg.jp/soshiki/97/10799.html" and s.kind == "adoption"
    assert s.photo == "ok"
    assert "2026-11-17" in NOTES["city_nara-2"] and "表示してよい" in NOTES["city_nara-2"]


def test_nara_stray_page_is_unchanged():
    # 迷子の記事（city_nara）は依頼に入れていない。link_only のまま
    assert SOURCES["city_nara"].mode == "link_only"
