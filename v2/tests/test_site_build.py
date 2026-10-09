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
    assert "本日は読めませんでした。自治体のページをご確認ください" in h and "https://example.jp/failed" in h
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
    assert "<img" not in h.split("<main")[1].split("</main>")[0]   # 本文には img が無い（フッターのロゴは除く）
    assert 'property="og:image" content="https://oneco.pages.dev/brand/oneco-avatar-512.png"' in h   # 写真が無い子はブランド画像
    assert "D999" in h
    with_img = _read(out / "animals" / data["animals"][0]["id"] / "index.html")
    assert "<img" in with_img and 'property="og:image" content="' + data["animals"][0]["image_url"] in with_img


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


def test_affiliate_box_only_on_adoption_pages(tmp_path: Path):
    """T506: 「迎える準備」枠（広告）は里親募集の子のページにだけ出す。保護中・迷子・探してます の子は
    飼い主の元に帰るかもしれない子なので、迎える準備の広告を並べない。"""
    data = _merged()
    base = next(a for a in data["animals"] if a["kind"] == "adoption")
    for kind in ("stray", "lost"):
        a = dict(base)
        a.update({"id": f"{kind}00000001", "kind": kind})
        data["animals"].append(a)
    cfg = dict(CONFIG)
    cfg["affiliate"] = [{"title": "ケージ", "url": "https://example.com/cage", "note": ""}]
    out = tmp_path / "d"
    _load_build().build_site(data, cfg, out)
    kinds = {a["id"]: a["kind"] for a in data["animals"]}
    assert set(kinds.values()) == {"adoption", "sheltered", "stray", "lost"}
    for aid, kind in kinds.items():
        h = _read(out / "animals" / aid / "index.html")
        assert ("迎える準備" in h) is (kind == "adoption"), (aid, kind)
    about = _read(out / "about" / "index.html")
    assert "里親募集の子のページ" in about and "各ページの「迎える準備」枠" not in about


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


# ---------------------------------------------------------------- T510 / T511（ロゴ・配色・about）

def test_brand_assets_copied_and_logo_in_header(built):
    """site/static/ のブランド素材が dist に入り、ヘッダーに「ふたつの円」とワードマークが出る。"""
    _, _, out = built
    for rel in ("brand/oneco-mark.svg", "brand/oneco-logo.svg", "brand/oneco-avatar-512.png",
                "favicon.ico", "icon.svg", "apple-touch-icon.png"):
        assert (out / rel).exists(), rel
    index = _read(out / "index.html")
    assert 'class="mark" src="/brand/oneco-mark.svg"' in index   # ふたつの円
    mark = _read(out / "brand" / "oneco-mark.svg")
    assert "#E8826E" in mark and "#6FAEBB" in mark            # コーラル（ポム）・ブルーグリーン（ビリー）
    assert 'aria-label="oneco"' in index and 'class="wordmark"' in index
    assert 'rel="icon" href="/favicon.ico"' in index and 'rel="apple-touch-icon"' in index
    assert 'property="og:image" content="https://oneco.pages.dev/brand/oneco-avatar-512.png"' in index   # 写真の無いページの OG 画像
    assert "ふたつの円は、犬のポムと猫のビリー" in index   # フッター
    css = _read(out / "style.css")
    assert "#0369a1" in css and "#075985" in css     # 旧サイトの primary
    assert "#E8826E" in css and "#6FAEBB" in css     # ブランド 2 色
    assert "#1f3a5f" not in css                      # 旧 v2 の紺は残さない


def test_about_has_pom_billy_and_operator(built):
    _, _, out = built
    h = _read(out / "about" / "index.html")
    assert "ポム" in h and "ビリー" in h
    for f, alt in _load_build().ABOUT_PHOTOS_POM + _load_build().ABOUT_PHOTOS_BILLY:
        assert f'/images/about/{f}' in h, f
        assert alt in h, alt
        assert (out / "images" / "about" / f).exists(), f
    assert "運営者" in h and "9mak" in h
    assert "小熊" not in h and "和喜" not in h   # 2026-10-04 おまえさん判断: 運営者欄は実名でなくハンドル名だけ
    assert "トリミング実習" in h and "輸血ドナー" in h
    assert "非営利" not in h            # W005: 「非営利」とは書かない
    assert "アフィリエイト" in h        # 運営費の明記
    assert "取り下げ・訂正の依頼窓口" in h


def test_about_review_fixes_20261004(tmp_path: Path):
    """公開前レビュー（2026-10-04 reviewer）の指摘: 実在しない代替窓口・載っていない広告を現在形で書かない、
    4 区分と犬猫以外を説明する、件数は読み取りとリンクのみを分ける、免責、取り下げ窓口へのアンカー。"""
    mod = _load_build()
    data = _merged()
    out = tmp_path / "d"
    mod.build_site(data, CONFIG, out)
    h = _read(out / "about" / "index.html")
    assert "同じページに記載の方法" not in h                      # F-01: 実在しない代替手段
    assert "GitHub アカウント（無料）が必要" in h                  # contact_email が無いとき
    assert "いまは広告を載せていません" in h                       # F-02: affiliate が空
    assert "各ページの「迎える準備」枠に載せている" not in h
    assert "個人や団体の掲載情報は扱いません" not in h             # F-03
    for label in ("里親募集", "保護中", "迷子", "探してます"):
        assert label in h, label
    assert "犬猫以外" in h
    assert "ページを毎日読み取" in h and "毎日確認しています" not in h   # F-04（リンクのみが 0 件のときは「読み取っています」）
    assert "自治体の公式サイトではなく" in h                       # F-05
    assert 'id="takedown"' in h                                    # F-06
    assert "/about/#takedown" in _read(out / "index.html")
    assert "翌日の更新で消えます" in h
    assert "ひとつに、という意味" in h                             # F-07 (2)

    cfg = dict(CONFIG)
    cfg["contact_email"] = "contact@example.com"
    cfg["affiliate"] = [{"title": "ケージ", "url": "https://example.com/cage", "note": ""}]
    out2 = tmp_path / "d2"
    mod.build_site(data, cfg, out2)
    h2 = _read(out2 / "about" / "index.html")
    assert "mailto:contact@example.com" in h2 and "GitHub アカウント（無料）が必要" not in h2
    assert "いまは広告を載せていません" not in h2 and "「迎える準備」枠" in h2


def test_lost_kind_is_labelled_and_filterable(tmp_path: Path):
    """新区分 lost（飼い主さんが探している迷子）: バッジ「探してます」・絞り込み・区分説明・項目名が収容の言い方にならない（2026-10-02）。"""
    data = _merged()
    a = dict(data["animals"][0])
    a.update({"id": "lost00000001", "kind": "lost", "shelter_date": "2026年9月1日", "location": "甲府市中央"})
    data["animals"].append(a)
    out = tmp_path / "dist"
    _load_build().build_site(data, CONFIG, out)
    pref = _read(out / "pref" / a["prefecture"] / "index.html")
    assert "kd-lost" in pref and "探してます" in pref
    assert "'lost'" in pref or '"lost"' in pref            # 絞り込みの選択肢と JS の表示名
    assert "里親募集" in pref and "保護中" in pref and "収容中" not in pref and "譲渡対象" not in pref
    d = _read(out / "animals" / "lost00000001" / "index.html")
    assert "探してます" in d and "飼い主さんが探している" in d
    assert "いなくなった日" in d and "いなくなった場所" in d and "収容日" not in d
    idx = _read(out / "index.html")
    assert "探してます＝" in idx                              # 区分の意味のヒント
