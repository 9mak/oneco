"""情報源の一覧の「写真を出していない」の書き方（W006 T652・ネットワークなし）。

台帳の photo が no の掲載元には「（写真は自治体の意向で出していません）」と出していたが、飼い主が探している迷子（kind: lost）のページは、
自治体の返事ではなくこちらの決まりで写真を出していない（飼い主の方が届け出た写真と思われるため。町田市 -2〜-4・鳥取県 -2・前橋市 -2・
旭川市あにまある -9〜-11 など）。自治体の意向とは書かない（2026-11-18 の追伸の reviewer の指摘）。
"""

import importlib.util
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent


def _build_mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_t652", ROOT / "site" / "build.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _build_mod()


def _src(**kw: Any) -> dict[str, Any]:
    return {"slug": "x", "name": "テスト市（犬）", "municipality": "テスト市", "prefecture": "東京都",
            "url": "https://example.jp/", "kind": "stray", "species": "dog", "status": "ok", "count": 2, "photo": "ok", **kw}


def _status_texts(sources: list[dict[str, Any]]) -> dict[str, str]:
    html = B.build_sources({**B.DEFAULT_CFG, "site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []},
                           {"date": "2026-11-19", "animals": [], "sources": sources})
    soup = BeautifulSoup(html, "lxml")
    return {li.select_one(".src-name").get_text(strip=True): li.select_one(".src-status").get_text(strip=True)
            for li in soup.select("li.src")}


def test_sources_list_does_not_blame_the_municipality_for_our_own_rule():
    got = _status_texts([
        _src(slug="a", name="迷子（こちらの決まり）", kind="lost", photo="no"),
        _src(slug="b", name="保護中（自治体の返事）", kind="stray", photo="no"),
        _src(slug="c", name="譲渡（自治体の返事）", kind="adoption", photo="no"),
        _src(slug="d", name="迷子（返事待ち）", kind="lost", photo="pending"),
        _src(slug="e", name="写真あり", kind="lost", photo="ok"),
    ])
    assert got["迷子（こちらの決まり）"] == "2 頭（写真は出していません）"
    assert got["保護中（自治体の返事）"] == "2 頭（写真は自治体の意向で出していません）"
    assert got["譲渡（自治体の返事）"] == "2 頭（写真は自治体の意向で出していません）"
    assert got["迷子（返事待ち）"] == "2 頭（写真は自治体の確認が取れるまで出していません）"  # 2026-11-22: まだお伺いしていない自治体もあるので「返事待ち」とは書かない
    assert got["写真あり"] == "2 頭"
