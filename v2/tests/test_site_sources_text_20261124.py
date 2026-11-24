"""情報源の一覧の行・説明文と about の運営方針の文言（POLICY.md 方針 18・19。ネットワークなし）。

読めなかった日・0 頭と確かめられた日は、どれも「最新の情報は自治体のページでご確認ください」と出す。
「読めませんでした」はこちらの都合なので使わない。
"""

from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from test_site_build import CONFIG, _load_build, _merged, _read

MSG = "最新の情報は自治体のページでご確認ください"
GONE = ("本日は 0 頭", "本日は読めませんでした", "読めなかった")


def _src(slug: str, status: str, **kw: Any) -> dict[str, Any]:
    return {"slug": slug, "name": f"{slug}市（収容）", "municipality": f"{slug}市", "prefecture": "徳島県",
            "url": f"https://example.jp/{slug}", "kind": "sheltered", "species": "dog", "mode": "recipe",
            "enabled": True, "status": status, "count": 0, "error": None, **kw}


def _built(tmp_path: Path) -> tuple[Path, int, str]:
    data = _merged()
    data["sources"].extend([_src("e", "empty"), _src("f", "failed", error="timeout"), _src("a", "ambiguous_empty"),
                            _src("l", "link_only"), _src("d", "disabled", enabled=False)])
    out = tmp_path / "dist"
    mod = _load_build()
    mod.build_site(data, CONFIG, out)
    return out, len(data["sources"]), mod.fmt_date(data.get("date"))


def test_status_rows_use_the_same_sentence(tmp_path: Path):
    out, _, _ = _built(tmp_path)
    soup = BeautifulSoup(_read(out / "sources" / "index.html"), "lxml")
    rows = {li["class"][1]: li.select_one(".src-status").get_text(strip=True) for li in soup.select("li.src")}
    assert rows["st-empty"] == rows["st-failed"] == rows["st-ambiguous_empty"] == MSG
    assert rows["st-link_only"] == "このページは一覧を読み取らず、リンクだけ載せています"
    assert rows["st-disabled"] == "停止中"


def test_sources_description_has_no_breakdown(tmp_path: Path):
    out, n, d = _built(tmp_path)
    soup = BeautifulSoup(_read(out / "sources" / "index.html"), "lxml")
    p = soup.select_one("h1").find_next("p").get_text()
    assert p == (f"{d}に確認した自治体ページ {n} 件の一覧です。"
                 "oneco に掲載している子がいない場合も、自治体のページには情報が載っていることがあります。"
                 "最新の情報はリンク先でご確認ください。")


def test_about_policy_item(tmp_path: Path):
    out, _, _ = _built(tmp_path)
    soup = BeautifulSoup(_read(out / "about" / "index.html"), "lxml")
    lis = [li for li in soup.select("li") if "前の日の情報を載せず" in li.get_text()]
    assert len(lis) == 1
    assert lis[0].get_text() == f"その日の情報を確認できない場合は、前の日の情報を載せず、情報源の一覧に「{MSG}」と表示します。"
    a = lis[0].select_one("a")
    assert a is not None and a["href"] == "/sources/" and a.get_text() == "情報源の一覧"


def test_old_phrases_gone_from_every_page(tmp_path: Path):
    out, _, _ = _built(tmp_path)
    for f in out.rglob("*.html"):
        h = f.read_text(encoding="utf-8")
        for w in GONE:
            assert w not in h, (str(f.relative_to(out)), w)
