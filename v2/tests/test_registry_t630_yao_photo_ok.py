"""W006 T630: 八尾市保健所の返事（2026-10-30。収容動物の画像は掲載していないが、そのうえで掲載は可能・手続き不要）。

写真表示のお伺いへの「可」なので photo: ok に戻す（八尾市は画像を載せない運用なので、表示される写真は実際には出ない）。
"""

from pathlib import Path

from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def test_yao_photo_ok():
    s = SOURCES["city_yao-1"]
    assert (s.mode, s.enabled, s.photo) == ("recipe", True, "ok")
