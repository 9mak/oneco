"""W006 T632: empty の見張り。0 頭と確定した日の本文の指紋を state に持ち、empty が続いているのに本文が変わった日を通知する。
ネットワークなし。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from collector import ai_repair, empty_watch
from collector import run as run_mod
from collector.fetch import FakeFetcher
from collector.notify import build_message
from collector.recipe import Doc
from collector.registry import Source
from collector.state import JST, load_state, save_state

URL = "https://www.city.example.jp/pets/"
ZERO = "現在、保護している犬はいません"


def _doc(body: str, url: str = URL, extra_head: str = "") -> Doc:
    html = f"<html><head><title>t</title>{extra_head}</head><body>{body}</body></html>"
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _fp(body: str, **kw) -> str:
    fp = empty_watch.fingerprint([_doc(body, **kw)], [URL])
    assert fp is not None
    return fp["fp"]


# --- 指紋 -----------------------------------------------------------------------------
def test_digits_and_fullwidth_digits_are_the_same():
    a = _fp(f"<main><p>{ZERO}</p><p>更新日 2026年11月5日 アクセス 1234</p></main>")
    b = _fp(f"<main><p>{ZERO}</p><p>更新日 ２０２６年１１月６日 アクセス 98765</p></main>")
    assert a == b


def test_changed_text_changes_the_fingerprint():
    a = _fp(f"<main><p>{ZERO}</p></main>")
    b = _fp(f"<main><p>{ZERO}</p><ul><li>ポチ オス 柴犬</li></ul></main>")
    assert a != b


def test_menu_header_footer_script_and_forms_are_ignored():
    base = f"<main><p>{ZERO}</p></main>"
    noisy = (
        "<header>本日のお知らせ 新着情報</header><nav>トップ くらし</nav><script>var x=Math.random()</script>"
        f"{base}<aside>人気ページ</aside><footer>Copyright</footer><form><select><option>A</option></select></form>"
    )
    assert _fp(base) == _fp(noisy)


def test_whitespace_layout_changes_are_ignored():
    assert _fp(f"<main><p>{ZERO}</p></main>") == _fp(
        f"<main>\n  <div>\n<p>  {ZERO}\n</p></div>\n</main>"
    )


def test_only_the_docs_that_hold_the_evidence_count():
    entry = _doc(f"<main><p>{ZERO}</p></main>")
    other = _doc("<main><p>別のページ</p></main>", url=URL + "other")
    one = empty_watch.fingerprint([entry, other], [URL])
    both = empty_watch.fingerprint([entry, other], [URL, URL + "other"])
    assert (
        one is not None
        and both is not None
        and one["docs"] == 1
        and both["docs"] == 2
        and one["fp"] != both["fp"]
    )
    assert empty_watch.fingerprint([entry], ["https://nothing/"]) is None


def test_rendered_page_can_be_fingerprinted_from_the_runs_own_page():
    """render の slug は last_ok が無い。その run のページ（描画後の HTML）から作れる。"""
    d = _doc(f"<main><p>{ZERO}</p></main>")
    d.rendered = True
    fp = empty_watch.fingerprint([d], [URL])
    assert fp is not None and len(fp["fp"]) == 16 and fp["chars"] > 0


def test_pdf_text_is_fingerprinted():
    pdf = Doc(
        url="https://x/a.pdf", pdf_text="令和8年11月5日 現在の収容はありません", pdf_tables=[]
    )
    pdf2 = Doc(
        url="https://x/a.pdf", pdf_text="令和8年11月6日 現在の収容はありません", pdf_tables=[]
    )
    pdf3 = Doc(url="https://x/a.pdf", pdf_text="令和8年11月6日 柴犬 1 頭", pdf_tables=[])
    a = empty_watch.fingerprint([pdf], ["https://x/a.pdf"])
    assert a is not None
    assert a == {**a, "fp": empty_watch.fingerprint([pdf2], ["https://x/a.pdf"])["fp"]}  # type: ignore[index]
    assert empty_watch.fingerprint([pdf3], ["https://x/a.pdf"])["fp"] != a["fp"]  # type: ignore[index]


# --- judge / update（state の純関数）-------------------------------------------------------
def _row(fp: str, chars: int = 100, status: str = "empty") -> dict:
    return {
        "slug": "s",
        "status": status,
        "empty_fp": {"fp": fp, "chars": chars, "docs": 1} if fp else None,
    }


def _day(st: dict, date: str, row: dict, prev_status: str | None = None) -> dict | None:
    """run の順序どおり: 判定してから状態を更新する。prev_status は update_sources が書くのと同じ。"""
    changed = empty_watch.judge(st, row, date)
    if st.get("last_date") != date:
        st["prev_status"] = st.get("last_status")
    empty_watch.update(st, row, date)
    st["last_status"], st["last_date"] = row["status"], date
    return changed


def test_first_day_sets_the_baseline_without_alarm_then_same_text_is_silent():
    st: dict = {}
    assert _day(st, "2026-11-01", _row("aaaa")) is None
    assert _day(st, "2026-11-02", _row("aaaa")) is None
    assert st["empty_watch"]["fp"] == "aaaa"


def test_change_while_empty_continues_is_reported_once_then_becomes_the_new_baseline():
    st: dict = {}
    _day(st, "2026-11-01", _row("aaaa", 100))
    _day(st, "2026-11-02", _row("aaaa", 100))
    ch = _day(st, "2026-11-03", _row("bbbb", 900))
    assert ch == {"from": "2026-11-02", "chars": [100, 900]}
    assert _day(st, "2026-11-04", _row("bbbb", 900)) is None  # 顔ぶれが変わった日だけ
    assert _day(st, "2026-11-05", _row("cccc", 905)) is not None  # また変われば、また 1 回


def test_rerun_on_the_same_day_compares_with_the_previous_days_baseline():
    st: dict = {}
    _day(st, "2026-11-01", _row("aaaa"))
    first = _day(st, "2026-11-02", _row("bbbb"))
    second = _day(st, "2026-11-02", _row("bbbb"))  # 16:04 の再実行
    assert first is not None and second == first


def test_a_day_that_was_not_empty_resets_without_alarm():
    st: dict = {}
    _day(st, "2026-11-01", _row("aaaa"))
    _day(
        st, "2026-11-02", {"slug": "s", "status": "failed"}
    )  # 読めない日は別の通知が出ている。基準は触らない
    assert st["empty_watch"]["fp"] == "aaaa"
    assert _day(st, "2026-11-03", _row("bbbb")) is None  # 失敗明けの empty は基準の取り直し
    assert st["empty_watch"]["fp"] == "bbbb"
    _day(st, "2026-11-04", {"slug": "s", "status": "ok"})  # 子がいた日は基準を忘れる
    assert "empty_watch" not in st
    assert _day(st, "2026-11-05", _row("cccc")) is None


def test_old_state_without_the_new_keys_is_readable(tmp_path):
    (tmp_path / "sources.json").write_text(
        json.dumps(
            {
                "sources": {
                    "s": {
                        "last_ok": "2026-10-01",
                        "last_status": "empty",
                        "last_date": "2026-11-01",
                    }
                },
                "breaker": {},
            }
        ),
        encoding="utf-8",
    )
    state = load_state(tmp_path)
    st = state["sources"]["s"]
    assert empty_watch.judge(st, _row("aaaa"), "2026-11-02") is None
    empty_watch.update(st, _row("aaaa"), "2026-11-02")
    save_state(state, tmp_path)
    assert load_state(tmp_path)["sources"]["s"]["empty_watch"]["fp"] == "aaaa"


def test_quiet_period_starts_at_the_first_record():
    assert empty_watch.quiet({}, "2026-11-06") is True  # まだ何も記録していない最初の日
    state = {"empty_watch_since": "2026-11-06"}
    assert empty_watch.quiet(state, "2026-11-12") is True
    assert empty_watch.quiet(state, "2026-11-13") is False


# --- run / notify につないだ動き -------------------------------------------------------------
RECIPE = f'rows: "ul.animals li"\nfields:\n  species: "span.s"\nempty_text:\n  - "{ZERO}"\n'


def _src(tmp_path: Path, slug: str = "w1") -> Source:
    p = tmp_path / f"{slug}.yaml"
    p.write_text(RECIPE, encoding="utf-8")
    return Source(
        slug=slug,
        name="W市",
        municipality="W市",
        prefecture="東京都",
        url=URL,
        kind="stray",
        species="dog",
        recipe=str(p),
    )


def _page(day_note: str, extra: str = "") -> str:
    return f"<html><body><header>メニュー</header><main><p>{ZERO}</p>{extra}<p>{day_note}</p></main></body></html>"


class Runner:
    def __init__(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool = False
    ) -> None:
        self.tmp, self.enabled = tmp_path, enabled
        self.src = _src(tmp_path)
        self.repaired: list[str] = []
        monkeypatch.setattr(ai_repair, "repair", lambda *a, **k: self.repaired.append("x"))

    def run(self, date: str, body: str, hms: tuple[int, int, int] = (0, 5, 0)) -> dict:
        y, m, d = (int(x) for x in date.split("-"))
        out = run_mod.run(
            [self.src],
            date,
            out_dir=self.tmp / "data",
            fetcher=FakeFetcher({URL: body}),
            enabled=self.enabled,
            now=datetime(y, m, d, *hms, tzinfo=JST),
        )
        return out

    def report(self, date: str) -> dict:
        return json.loads((self.tmp / "data" / f"report-{date}.json").read_text(encoding="utf-8"))[
            0
        ]

    def state(self) -> dict:
        return load_state(self.tmp / "data" / "state")

    def message(self, date: str) -> str | None:
        rows = json.loads((self.tmp / "data" / f"report-{date}.json").read_text(encoding="utf-8"))
        return build_message(rows, self.state())

    def events(self, date: str) -> list[dict]:
        p = self.tmp / "data" / "logs" / f"events-{date}.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def rn(tmp_path, monkeypatch):
    return Runner(tmp_path, monkeypatch)


def _quiet_over(rn: Runner) -> None:
    """見張りを入れて 7 日たった状態にする（QUIET_DAYS の間は記録だけ）。"""
    st = rn.state()
    st["empty_watch_since"] = "2026-10-01"
    save_state(st, rn.tmp / "data" / "state")


def test_date_only_changes_stay_silent_for_many_days(rn):
    for d in range(1, 9):
        rn.run(f"2026-11-{d:02d}", _page(f"更新日 11月{d}日"))
        _quiet_over(rn)
        assert rn.report(f"2026-11-{d:02d}")["status"] == "empty"
        assert rn.message(f"2026-11-{d:02d}") is None


def test_rows_break_but_zero_text_remains_is_reported_and_ai_is_not_called(tmp_path, monkeypatch):
    rn = Runner(tmp_path, monkeypatch, enabled=True)
    rn.run("2026-11-01", _page("更新日 11月1日"))
    rn.run("2026-11-02", _page("更新日 11月2日"))
    _quiet_over(rn)
    # 子はいるが、行の作りが変わって rows（ul.animals li）に当たらない。0 頭の文言は常設の案内として残っている
    broken = _page(
        "更新日 11月3日",
        '<div class="list"><div class="item">ポチ 柴犬 オス 収容日 11月3日</div></div>',
    )
    out = rn.run("2026-11-03", broken)
    row = rn.report("2026-11-03")
    assert row["status"] == "empty" and row["empty_changed"]["from"] == "2026-11-02"
    msg = rn.message("2026-11-03")
    assert msg is not None and "W市" in msg and "0 頭のまま本文が変わった" in msg
    assert rn.repaired == []  # AI 修復は起動しない
    # 公開データには出さない
    latest = json.loads((rn.tmp / "data" / "latest.json").read_text(encoding="utf-8"))
    assert out["animals"] == [] and latest["animals"] == []
    for src in (latest["sources"][0], out["sources"][0]):
        assert "empty_fp" not in src and "empty_changed" not in src
    # 翌日も同じ崩れ方なら、もう送らない（顔ぶれが変わった日だけ）
    rn.run("2026-11-04", broken.replace("11月3日", "11月4日"))
    assert rn.message("2026-11-04") is None


def test_first_week_only_records_to_events(rn):
    rn.run("2026-11-01", _page("a"))
    rn.run("2026-11-02", _page("b"))
    out = rn.run("2026-11-03", _page("c", "<p>ポチ</p>"))
    row = rn.report("2026-11-03")
    assert row["empty_changed"]["quiet"] is True
    assert rn.message("2026-11-03") is None  # 最初の 7 日は通知しない
    ev = next(e for e in rn.events("2026-11-03") if e["slug"] == "w1")
    assert ev["empty_changed"] is True
    assert out["animals"] == []
    assert rn.state()["empty_watch_since"] == "2026-11-01"


def test_state_keeps_the_fingerprint_not_the_page(rn):
    rn.run("2026-11-01", _page("a"))
    ew = rn.state()["sources"]["w1"]["empty_watch"]
    assert set(ew) <= {"fp", "chars", "date", "ref"} and len(ew["fp"]) == 16


def test_children_returning_forgets_the_baseline(rn):
    rn.run("2026-11-01", _page("a"))
    ok_page = "<html><body><ul class='animals'><li><span class='s'>犬</span><img src='/a.jpg'></li></ul></body></html>"
    rn.run("2026-11-02", ok_page)
    assert rn.report("2026-11-02")["status"] == "ok"
    assert "empty_watch" not in rn.state()["sources"]["w1"]
