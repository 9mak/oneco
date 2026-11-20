"""W006: city_hiroshima-1（広島市 迷子犬）の 0 頭誤認バグ修正テスト（ネットワークなし）。

現行レシピが常時表示される休館案内文を empty_text にしており、犬がいる日にも empty_hits が成立していた。
city_hiroshima-2 と同じ empty_selector: "div#voice dl dd" に切り替え、以下を固定する:
- 今日のページ（犬がいる日）で、これまでと同じ頭数・ID・全項目が取れ、empty_hits が当たらない
- 0 頭の日（dl が空の &nbsp; 雛形だけの状態）は 0 頭と確定できる
- 構造崩れの日（div#voice や対象の器 dl/dd が消えた等）は fail-closed（failed / ambiguous_empty）になる
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import empty_hits
from collector.fetch import FakeFetcher
from collector.recipe import Doc, Recipe
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
SLUG = "city_hiroshima-1"
TODAY_FIXTURE = "w006_city_hiroshima-1_child_20261120.html"

sys.path.insert(0, str(ROOT / "ops"))
import audit_empty  # noqa: E402


def _today_html() -> str:
    return (FIX / TODAY_FIXTURE).read_text(encoding="utf-8")


def _single(html: str) -> Collected:
    src = SOURCES[SLUG]
    return collect_one(src, FakeFetcher({src.url: html}))


def _hits(html: str):
    src = SOURCES[SLUG]
    recipe = Recipe.load(ROOT / "recipes" / f"{SLUG}.yaml")
    doc = Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))
    return empty_hits(recipe, [doc], [doc])


def _zero_template_html(heading: str = "整理番号：8-") -> str:
    """今日のページから犬1頭ブロックを抜き、city_hiroshima-2 と同じ &nbsp; 雛形 dl に差し替えた 0 頭 HTML。"""
    blank_block = (
        f"<h2>{heading}</h2>"
        "<dl>"
        "<dt>収容月日</dt><dd>\n<p>&nbsp;</p>\n</dd>"
        "<dt>種類</dt><dd>\n<p>&nbsp;</p>\n</dd>"
        "<dt>推定年齢</dt><dd>&nbsp;</dd>"
        "<dt>毛色</dt><dd>&nbsp;</dd>"
        "<dt>性別</dt><dd>&nbsp;</dd>"
        "<dt>首輪等</dt><dd>&nbsp;</dd>"
        "<dt>拾得等の場所</dt><dd>&nbsp;</dd>"
        "<dt>備考</dt><dd>\n<p>&nbsp;</p>\n</dd>"
        "</dl>"
    )
    html = _today_html()
    start = html.index("<h2>8-11-7</h2>")
    end = html.index("</dl>", start) + len("</dl>")
    return html[:start] + blank_block + html[end:]


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


def test_today_page_reads_same_dog_id_and_fields():
    c = _single(_today_html())
    assert c.status == "ok", c.error
    assert c.result is not None and len(c.result.animals) == 1
    a = c.result.animals[0]
    assert a == {
        "id": "b201a9f20157",
        "source": "city_hiroshima-1",
        "municipality": "広島市",
        "prefecture": "広島県",
        "phone": "082-243-6058",
        "address": "〒730-0043 広島県広島市中区富士見町11番27号（広島市動物愛護センター）",
        "contact_scope": "facility",
        "kind": "stray",
        "species": "dog",
        "image_url": "https://www.city.hiroshima.lg.jp/_res/projects/default_project/_page_/001/037/461/20261109.jpg",
        "source_url": "https://www.city.hiroshima.lg.jp/living/pet-doubutsu/1021301/1026245/1037461.html",
        "name": None,
        "sex": "オス(未去勢)",
        "age": "3歳くらい",
        "breed": "雑種",
        "color": "茶色",
        "size": None,
        "management_no": "8-11-7",
        "shelter_date": "令和8年11月9日",
        "note": "マイクロチップなし",
        "location": "安芸区中野東5丁目",
    }


def test_empty_hits_never_match_on_dog_day():
    # 犬がいる日に empty_hits が絶対に当たらないこと（修正前は休館案内文が当たっていた）
    assert _hits(_today_html()) == []


def test_empty_hits_never_match_when_dog_and_blank_template_coexist():
    # 犬の後ろに空の雛形 dl が残っていても、犬がいる日は empty_hits が当たらない
    blank = (
        "<h2>整理番号：</h2><dl>"
        "<dt>収容月日</dt><dd>&nbsp;</dd><dt>種類</dt><dd>&nbsp;</dd>"
        "<dt>推定年齢</dt><dd>&nbsp;</dd><dt>毛色</dt><dd>&nbsp;</dd>"
        "<dt>性別</dt><dd>&nbsp;</dd><dt>首輪等</dt><dd>&nbsp;</dd>"
        "<dt>拾得等の場所</dt><dd>&nbsp;</dd><dt>備考</dt><dd>&nbsp;</dd></dl>"
    )
    html = _today_html().replace("</dl>", "</dl>" + blank, 1)
    c = _single(html)
    assert c.status == "ok" and c.result is not None and len(c.result.animals) == 1
    assert _hits(html) == []


def test_zero_day_blank_dl_template_is_confirmed_empty():
    for heading in ("整理番号：8-", "整理番号：", ""):
        c = _single(_zero_template_html(heading))
        assert _zero(c), (heading, c.status, c.error)
        assert c.result is not None and c.result.empty_evidence == "empty_selector"


def test_structure_change_is_fail_closed():
    # div#voice が消えた日
    no_voice = _zero_template_html().replace('id="voice"', 'id="main_content"')
    c1 = _single(no_voice)
    assert c1.status in ("failed", "ambiguous_empty") and not _zero(c1)

    # dd が別のタグに変わった（対象の器が消えた）日
    no_dd = _zero_template_html().replace("<dd", "<span").replace("</dd>", "</span>")
    c2 = _single(no_dd)
    assert c2.status in ("failed", "ambiguous_empty") and not _zero(c2)

    # dl 自体が消えた（対象の器自体が消えた）日
    no_dl = _zero_template_html().replace("<dl>", '<div class="list">').replace("</dl>", "</div>")
    c3 = _single(no_dl)
    assert c3.status in ("failed", "ambiguous_empty") and not _zero(c3)

    # 犬がいる日に dl の構造が変わって行が取れなくなった日（休館案内文が残っていても 0 頭にしない）
    broken_dog = _today_html().replace("<dl>", "<table>").replace("</dl>", "</table>")
    c4 = _single(broken_dog)
    assert c4.status in ("failed", "ambiguous_empty") and not _zero(c4)


def test_audit_empty_reports_no_findings_for_today_last_ok(tmp_path):
    src = SOURCES[SLUG]
    last_ok_dir = tmp_path / "last_ok" / SLUG
    last_ok_dir.mkdir(parents=True)
    (last_ok_dir / "0.bin").write_bytes(_today_html().encode("utf-8"))
    (last_ok_dir / "index.json").write_text(
        json.dumps({"date": "2026-11-20", "count": 1, "docs": [{"url": src.url, "final_url": src.url, "file": "0.bin"}]}),
        encoding="utf-8",
    )
    recipe = Recipe.load(ROOT / "recipes" / f"{SLUG}.yaml")
    res = audit_empty.audit(tmp_path, [(src, recipe)])
    assert res.scanned == 1
    assert res.child_days == 1
    assert res.findings == []
