"""静的サイト生成（site/build.py）のテスト。

徳島 20 頭・佐賀 2 頭のサンプル JSON（tests/fixtures にコピー）を合成した一時 data で build を走らせる。
`site` は標準ライブラリのモジュール名なので `import site.build` はできない。ファイルパスから読み込む。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
BUILD_PY = ROOT / "site" / "build.py"


def _load_build():
    spec = importlib.util.spec_from_file_location("oneco_site_build", BUILD_PY)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _merged() -> dict[str, Any]:
    a = json.loads((FIX / "animals_tokushima.json").read_text(encoding="utf-8"))
    b = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
    return {"date": "2026-09-28", "animals": a["animals"] + b["animals"], "sources": a["sources"] + b["sources"]}


CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


@pytest.fixture
def built(tmp_path: Path):
    """合成 data で build した dist を返す。"""
    data = _merged()
    data_path = tmp_path / "latest.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    out = tmp_path / "dist"
    mod = _load_build()
    mod.build(data_path, out, CONFIG)
    return data, data_path, out


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_generates_index_animals_sitemap(built):
    data, data_path, out = built
    assert len(data["animals"]) == 22
    index = _read(out / "index.html")
    assert "徳島県" in index and "佐賀県" in index
    assert quote("徳島県") in index   # 県ページへのリンクは URL エンコード
    for a in data["animals"]:
        page = out / "animals" / a["id"] / "index.html"
        assert page.exists(), a["id"]
        h = _read(page)
        assert a["id"] in h
        assert a["municipality"] in h
        assert "自治体のページで詳細を見る" in h
        assert 'property="og:title"' in h
    sitemap = _read(out / "sitemap.xml")
    for a in data["animals"]:
        assert f"https://oneco.pages.dev/animals/{a['id']}/" in sitemap
    assert f"https://oneco.pages.dev/pref/{quote('徳島県')}/" in sitemap
    assert "https://oneco.pages.dev/sources/" in sitemap
    assert "https://oneco.pages.dev/about/" in sitemap
    assert (out / "pref" / "徳島県" / "index.html").exists()
    assert (out / "pref" / "佐賀県" / "index.html").exists()
    assert (out / "sources" / "index.html").exists()
    assert (out / "about" / "index.html").exists()
    assert "Sitemap: https://oneco.pages.dev/sitemap.xml" in _read(out / "robots.txt")
    assert (out / "data.json").read_bytes() == data_path.read_bytes()
    assert (out / "style.css").exists()


def test_index_counts_per_prefecture(built):
    _, _, out = built
    index = _read(out / "index.html")
    assert 'data-pref="徳島県"' in index and 'data-dog="20"' in index
    assert 'data-pref="佐賀県"' in index and 'data-dog="2"' in index


def test_pref_page_lists_only_that_prefecture(built):
    data, _, out = built
    saga = _read(out / "pref" / "佐賀県" / "index.html")
    for a in data["animals"]:
        if a["prefecture"] == "佐賀県":
            assert a["id"] in saga
        else:
            assert a["id"] not in saga
    assert "data.json" in saga   # 絞り込みはページ内 JS が data.json を読む


def test_sources_page_status(tmp_path: Path):
    data = _merged()
    data["sources"].append({"slug": "x_failed", "name": "失敗市（収容）", "municipality": "失敗市", "prefecture": "徳島県",
                            "url": "https://example.jp/failed", "kind": "sheltered", "species": "mixed",
                            "phone": None, "address": None, "mode": "recipe", "recipe": "recipes/x.yaml",
                            "enabled": True, "status": "failed", "count": 0, "error": "timeout"})
    data["sources"].append({"slug": "x_link", "name": "リンク市（譲渡）", "municipality": "リンク市", "prefecture": "佐賀県",
                            "url": "https://example.jp/link", "kind": "adoption", "species": "dog",
                            "phone": None, "address": None, "mode": "link_only", "recipe": None,
                            "enabled": True, "status": "link_only", "count": 0, "error": None})
    out = tmp_path / "dist"
    _load_build().build_site(data, CONFIG, out)
    h = _read(out / "sources" / "index.html")
    assert "徳島県動物愛護管理センター（譲渡犬）" in h and "20 頭" in h
    assert "本日は確認できませんでした" in h and "https://example.jp/failed" in h
    assert "リンク市（譲渡）" in h and "https://example.jp/link" in h
    assert "timeout" not in h   # エラー内容は公開しない


def test_html_is_escaped_and_unsafe_urls_dropped(tmp_path: Path):
    data = _merged()
    a = dict(data["animals"][0])
    a["id"] = "deadbeef0001"
    a["note"] = "<script>alert(1)</script> & \"q\""
    a["municipality"] = "A&B <市>"
    a["source_url"] = "javascript:alert(1)"
    a["image_url"] = "javascript:alert(2)"
    data["animals"].append(a)
    out = tmp_path / "dist"
    _load_build().build_site(data, CONFIG, out)
    h = _read(out / "animals" / "deadbeef0001" / "index.html")
    assert "<script>alert(1)</script>" not in h
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in h
    assert "A&amp;B &lt;市&gt;" in h
    assert "javascript:" not in h
    # 県ページ・トップの見出しも通る
    assert "&lt;市&gt;" in _read(out / "pref" / "徳島県" / "index.html")


def test_placeholder_when_no_image(tmp_path: Path):
    data = _merged()
    a = dict(data["animals"][0])
    a["id"] = "noimg0000001"
    a["image_url"] = None
    a["management_no"] = "D999"
    data["animals"].append(a)
    out = tmp_path / "dist"
    _load_build().build_site(data, CONFIG, out)
    h = _read(out / "animals" / "noimg0000001" / "index.html")
    assert 'class="ph"' in h
    assert "<img" not in h.split("<main")[1]   # 本文には img が無い
    assert 'property="og:image"' not in h
    assert "D999" in h
    with_img = _read(out / "animals" / data["animals"][0]["id"] / "index.html")
    assert "<img" in with_img and 'property="og:image"' in with_img


def test_affiliate_box_only_when_configured(tmp_path: Path):
    data = _merged()
    aid = data["animals"][0]["id"]
    out1 = tmp_path / "d1"
    _load_build().build_site(data, CONFIG, out1)
    assert "迎える準備" not in _read(out1 / "animals" / aid / "index.html")
    cfg = dict(CONFIG)
    cfg["affiliate"] = [{"title": "ケージ", "url": "https://example.com/cage?a=1&b=2", "note": "最初の 1 週間用"}]
    out2 = tmp_path / "d2"
    _load_build().build_site(data, cfg, out2)
    h = _read(out2 / "animals" / aid / "index.html")
    assert "迎える準備" in h and "ケージ" in h and "https://example.com/cage?a=1&amp;b=2" in h
    assert 'rel="sponsored' in h


def test_rebuild_removes_stale_pages(tmp_path: Path):
    data = _merged()
    out = tmp_path / "dist"
    mod = _load_build()
    mod.build_site(data, CONFIG, out)
    gone = data["animals"].pop()["id"]
    assert (out / "animals" / gone / "index.html").exists()
    mod.build_site(data, CONFIG, out)
    assert not (out / "animals" / gone / "index.html").exists()
    # 自分が作ったものでないディレクトリは消さない
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod.build_site(data, CONFIG, foreign)
    assert (foreign / "keep.txt").exists()


def test_cli(tmp_path: Path):
    data_path = tmp_path / "latest.json"
    data_path.write_text(json.dumps(_merged(), ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "dist"
    r = subprocess.run([sys.executable, str(BUILD_PY), "--data", str(data_path), "--out", str(out)],
                       capture_output=True, text=True, cwd=ROOT, check=False)
    assert r.returncode == 0, r.stderr
    assert (out / "index.html").exists()
    assert "22" in r.stdout   # 頭数を報告する
