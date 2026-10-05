"""ops/ab_compare.py（エンジン・レシピ変更の回帰確認）のテスト。ネットワークなし。

1. 取得結果をディスクに残し、2 回目はネットワークに出ずに同じ Page を返す（失敗した取得も同じ失敗として再生する）
2. render の結果（描画中に捕まえた JSON 応答を含む）も残す
3. 2 つの実行結果を slug ごとに比べ、増減・消えた子・項目の変化を出す
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from collector.fetch import FakeFetcher, FetchError, Page

AB_PY = Path(__file__).resolve().parent.parent / "ops" / "ab_compare.py"


def _load():
    spec = importlib.util.spec_from_file_location("oneco_ab_compare", AB_PY)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _fetcher(mod, pages, cache: Path, offline: bool = False, captures=None):
    cls = mod.caching_fetcher_class(FakeFetcher, FetchError, Page)
    return cls(cache, offline, pages, captures=captures)


def test_get_is_recorded_then_replayed_offline(tmp_path: Path):
    mod = _load()
    url = "https://x.jp/list.html"
    f1 = _fetcher(mod, {url: "<p>ポム</p>", "https://x.jp/a.pdf": b"%PDF-1.4 dummy"}, tmp_path)
    assert f1.get(url).html == "<p>ポム</p>"
    assert f1.get("https://x.jp/a.pdf").content == b"%PDF-1.4 dummy"
    with pytest.raises(FetchError, match="FakeFetcher に無い URL"):
        f1.get("https://x.jp/404.html")
    assert f1.misses == 3

    f2 = _fetcher(mod, {}, tmp_path, offline=True)        # 元の取得先が空でもキャッシュから返る
    page = f2.get(url)
    assert page.html == "<p>ポム</p>" and page.final_url == url
    pdf = f2.get("https://x.jp/a.pdf")
    assert pdf.html is None and pdf.content == b"%PDF-1.4 dummy"
    with pytest.raises(FetchError, match="FakeFetcher に無い URL"):   # 失敗も同じ失敗として再生
        f2.get("https://x.jp/404.html")
    assert f2.hits == 3 and f2.misses == 0
    with pytest.raises(FetchError, match="キャッシュに無い"):          # offline で未取得の URL は取りに行かない
        f2.get("https://x.jp/other.html")


def test_get_cache_key_includes_encoding(tmp_path: Path):
    mod = _load()
    url = "https://x.jp/euc.html"
    f1 = _fetcher(mod, {url: "<p>a</p>"}, tmp_path)
    f1.get(url, encoding="euc-jp")
    f2 = _fetcher(mod, {}, tmp_path, offline=True)
    assert f2.get(url, encoding="euc-jp").html == "<p>a</p>"
    with pytest.raises(FetchError, match="キャッシュに無い"):
        f2.get(url)


def test_render_with_capture_is_replayed(tmp_path: Path):
    mod = _load()
    url = "https://spa.jp/"
    f1 = _fetcher(mod, {url: "<div id=app></div>"}, tmp_path, captures={url: [{"hits": {"hits": [{"_id": "x1"}]}}]})
    p1 = f1.render(url, capture="elasticsearch/search", wait_for="div.card")
    assert p1.captured == [{"hits": {"hits": [{"_id": "x1"}]}}]
    f2 = _fetcher(mod, {}, tmp_path, offline=True)
    p2 = f2.render(url, capture="elasticsearch/search", wait_for="div.card")
    assert p2.html == "<div id=app></div>" and p2.captured == p1.captured
    with pytest.raises(FetchError, match="キャッシュに無い"):          # capture・wait_for が違えば別物
        f2.render(url, capture=None)


def _res(status, animals, dropped=0, error=None):
    return {"status": status, "count": len(animals), "error": error, "dropped": dropped, "animals": animals}


def test_diff_reports_counts_ids_and_field_changes():
    mod = _load()
    a = {"slugs": {
        "same": _res("ok", [{"id": "s1", "name": "ポム"}]),
        "more": _res("ok", [{"id": "m1", "name": "ビリー", "image_url": None}]),
        "broken": _res("ok", [{"id": "b1"}, {"id": "b2"}]),
        "gone": _res("empty", []),
    }}
    b = {"slugs": {
        "same": _res("ok", [{"id": "s1", "name": "ポム"}]),
        "more": _res("ok", [{"id": "m1", "name": "ビリー", "image_url": "https://x.jp/1.jpg"}, {"id": "m2", "name": "タロ"}]),
        "broken": _res("failed", [], error="HTTP 404"),
        "new": _res("ok", [{"id": "n1"}]),
    }}
    d = mod.diff_results(a, b)
    assert d["unchanged"] == ["same"]
    ch = {c["slug"]: c for c in d["changed"]}
    assert set(ch) == {"more", "broken", "gone", "new"}
    assert ch["more"]["count"] == [1, 2] and ch["more"]["added"] == ["m2"] and ch["more"]["removed"] == []
    assert ch["more"]["fields"] == {"image_url": [["m1", None, "https://x.jp/1.jpg"]]}
    assert ch["broken"]["status"] == ["ok", "failed"] and ch["broken"]["removed"] == ["b1", "b2"]
    assert ch["gone"]["status"] == ["empty", None] and ch["new"]["status"] == [None, "ok"]
    text = mod.format_diff(d)
    assert "more" in text and "1 → 2" in text and "image_url" in text and "ok → failed" in text
