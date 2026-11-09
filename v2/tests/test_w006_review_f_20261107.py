"""W006 B 班 公開ゲート #105 の指摘 F-01・F-02 への対応（ネットワークなし）。

F-01 相模原市 収容犬の公示: 収容期限（令和8年9月3日）を過ぎた行は載せない。期限が読めない行も載せない（fail-closed）。
     期限切れの行しか無い日は 0 頭と言わず failed。
F-02 山形市: 「保護・収容【その他】情報」の節の行は species other で載せる（種別なしにしない）。
"""

from datetime import date
from pathlib import Path

from collector import extract
from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _single(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


SAGA_DOG = "w006_city_sagamihara-2_dog_wb20260903.html"


def _on(monkeypatch, y: int, m: int, d: int) -> None:
    monkeypatch.setattr(extract, "_today", lambda: date(y, m, d))


def test_sagamihara_dog_is_listed_until_its_expiry_day(monkeypatch):
    for day in (1, 3):      # 収容期限は令和8年9月3日（木曜日）。当日までは収容中
        _on(monkeypatch, 2026, 9, day)
        c = _single("city_sagamihara-2", _fx(SAGA_DOG))
        assert c.status == "ok", c.error
        assert c.result is not None and len(c.result.animals) == 1


def test_sagamihara_dog_past_its_expiry_is_not_listed_and_not_zero(monkeypatch):
    _on(monkeypatch, 2026, 9, 4)
    c = _single("city_sagamihara-2", _fx(SAGA_DOG))
    assert c.status != "empty"          # 0 頭とは言わない
    assert c.status != "ok"
    assert c.result is None or not c.result.animals


def test_sagamihara_dog_without_readable_expiry_is_not_listed(monkeypatch):
    _on(monkeypatch, 2026, 9, 1)
    html = _fx(SAGA_DOG).replace("収容期限　令和8年9月3日（木曜日）", "収容期限　未定")
    c = _single("city_sagamihara-2", html)
    assert c.status not in ("ok", "empty")
    assert c.result is None or not c.result.animals


def test_yamagata_other_section_row_is_species_other():
    html = _fx("w006_city_yamagata-1_zero_wb20240528.html")
    other = ("<h2>保護・収容【その他】情報</h2>"
             "<p>1　11月29日（金曜）千歳一丁目地内で収容 種類：セキセイインコ 性別：不明 マイクロチップなし</p>")
    html = html.replace("<h2>その他自治体等ホームページ</h2>", other + "<h2>その他自治体等ホームページ</h2>")
    c = _single("city_yamagata-1", html)
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    assert c.result.animals[0]["species"] == "other"
