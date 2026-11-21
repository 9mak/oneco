"""T656 直し 2 回目（2026-11-21・ネットワークなし）。agy の全項目の監査の高・中の指摘のうち、実ページで裏取りして本当に誤りだったもの。

fixture は 2026-11-21 に取った実ページ（script・style を落とした）。
"""

from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _animals(c: Collected) -> list[dict]:
    assert c.status == "ok", c.error
    assert c.result is not None
    return c.result.animals


# --- 1. 船橋市 -3・-4: 表に「動物種」列が増えた（列ずれ） ------------------------------------------------------------
FN_FX = "w006_city_funabashi-3_20261121.html"


def test_funabashi_3_reads_columns_by_header_after_the_species_column_was_added():
    animals = _animals(_run("city_funabashi-3", _fx(FN_FX)))
    assert [(a["species"], a.get("breed"), a["color"], a["sex"], a["size"], a["shelter_date"], a["location"]) for a in animals] == [
        ("cat", None, "茶トラ", "オス", "小", "令和8年9月25日", "前貝塚町"),
        ("cat", None, "茶白", "オス", "中", "令和8年9月21日", "東船橋"),
        ("cat", None, "キジ", "メス", "小", "令和8年10月23日", "習志野台")]
    assert animals[1]["note"] == "推定8歳程度去勢済 届出日：令和8年10月19日"
    assert animals[0]["note"] == "届出日：令和8年10月19日"


def test_funabashi_4_reads_columns_by_header_after_the_species_column_was_added():
    animals = _animals(_run("city_funabashi-4", _fx(FN_FX)))
    assert [(a["species"], a.get("breed"), a["color"], a["sex"], a["size"]) for a in animals] == [
        ("cat", None, "白", "メス", "小"),
        ("cat", "ロシアンブルー", "グレー", "メス", "小"),
        ("cat", None, "黒", "メス", "小"),
        ("cat", "ベンガル", "ブラウンレオパード (ロゼット模様 )", "オス", "小"),
        ("cat", "ブリティッシュショートヘアー", "ブラウンティックドタビー", "オス", "小"),
        ("cat", "ペルシャ", "茶", "オス", "小")]
    assert "MC装着" in animals[1]["note"] and animals[1]["note"].endswith("届出日：令和8年11月4日")
