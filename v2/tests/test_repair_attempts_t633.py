"""W006 T633: AI 修復の試行を、不採用も含めて run ごとに data/repair_attempts/<日付>/ へ残す。
判定は変えない（残すだけ）。入口の HTML も run ごとに残し、同じ日の 2 回目の run で上書きしない。"""

import hashlib
from datetime import datetime
from pathlib import Path

import pytest
import yaml
from collector import ai_repair
from collector.fetch import FakeFetcher
from collector.registry import Source
from collector.run import JST, run

URL = "https://x.test/animals/"
OLD_RECIPE = '# 古い\nrows: "ul.animals > li"\nfields:\n  sex: {label: "性別"}\n'
ZERO_PAGE = "<html><body><h2>保護犬情報</h2><p>現在、保護犬はいません。</p><p>お問い合わせは窓口へ</p></body></html>"
JUNK_PAGE = (
    '<html><body><table class="list">'
    + "".join(f"<tr><td>見出し{i}</td></tr>" for i in range(5))
    + "</table></body></html>"
)
GOOD_PAGE = """<html><body><table class="list">
<tr><td><img src="photo/d1.jpg"></td><td>メス</td><td>令和8年9月20日</td></tr>
<tr><td><img src="photo/d2.jpg"></td><td>オス</td><td>令和8年9月21日</td></tr></table></body></html>"""
ZERO_AI = '# 0 頭の文言を足した\nrows: "ul.animals > li"\nempty_text: ["保護犬はいません"]\n'
JUNK_AI = '# tr を 1 頭\nrows: "table.list tr"\nfields:\n  sex: "td:nth-of-type(2)"\n'
GOOD_AI = '# tr を 1 頭\nrows: "table.list tr"\nfields:\n  sex: "td:nth-of-type(2)"\n  shelter_date: "td:nth-of-type(3)"\n'


@pytest.fixture(autouse=True)
def _agy(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ai_repair, "ask_agy", ai_repair.ask_agy
    )  # テスト内で差し替えた値を終了時に戻す
    monkeypatch.setattr(ai_repair.shutil, "which", lambda name: "/usr/local/bin/agy")
    monkeypatch.setattr(ai_repair, "PROPOSALS_DIR", tmp_path / "proposals")
    monkeypatch.setattr(ai_repair, "LAST_OK_DIR", tmp_path / "no_last_ok")


def _source(tmp_path: Path) -> Source:
    p = tmp_path / "x_test.yaml"
    p.write_text(OLD_RECIPE, encoding="utf-8")
    return Source(
        slug="x_test",
        name="テスト市",
        municipality="テスト市",
        prefecture="テスト県",
        url=URL,
        kind="sheltered",
        species="dog",
        recipe=str(p),
    )


def _at(hms: str) -> datetime:
    h, m, s = (int(x) for x in hms.split(":"))
    return datetime(2026, 11, 5, h, m, s, tzinfo=JST)


def _run(tmp_path, page, ai_yaml, date="2026-11-05", hms="00:05:00", note="メモ"):
    ai_repair.ask_agy = lambda prompt, schema, timeout: {"recipe_yaml": ai_yaml, "note": note}
    return run(
        [_source(tmp_path)],
        date,
        out_dir=tmp_path / "data",
        fetcher=FakeFetcher({URL: page}),
        enabled=True,
        now=_at(hms),
    )


def _records(tmp_path, date="2026-11-05"):
    d = tmp_path / "data" / "repair_attempts" / date
    return sorted(d.glob("*.yaml")), sorted(d.glob("*.html"))


def test_zero_answer_records_evidence_and_matched_text(tmp_path):
    _run(tmp_path, ZERO_PAGE, ZERO_AI)
    ymls, htmls = _records(tmp_path)
    assert [p.name for p in ymls] == ["x_test-2026-11-05T000500.yaml"]
    rec = yaml.safe_load(ymls[0].read_text(encoding="utf-8"))
    assert (
        rec["slug"] == "x_test" and rec["run_id"] == "2026-11-05T000500" and rec["called"] is True
    )
    assert rec["status"] == "failed" and "0 頭" in rec["error"]
    assert rec["agy"]["recipe_yaml"] == ZERO_AI and rec["agy"]["note"] == "メモ"
    nr = rec["new_recipe"]
    assert nr["count"] == 0 and nr["empty_confirmed"] is True
    assert nr["empty_evidence"] == "empty_text" and nr["empty_matched"] == ["保護犬はいません"]
    assert rec["reached"] == "ran"
    assert rec["entry"]["sha256"] == hashlib.sha256(ZERO_PAGE.encode("utf-8")).hexdigest()
    assert htmls[0].read_text(encoding="utf-8") == ZERO_PAGE


def test_dropped_rows_keep_first_three_only(tmp_path):
    _run(tmp_path, JUNK_PAGE, JUNK_AI)
    rec = yaml.safe_load(_records(tmp_path)[0][0].read_text(encoding="utf-8"))
    nr = rec["new_recipe"]
    assert nr["rows"] == 5 and nr["dropped"] == 5
    assert len(nr["dropped_head"]) == 3 and nr["dropped_head"][0]["text"].startswith("見出し0")
    assert nr["empty_evidence"] is None and nr["empty_matched"] == []


def test_schema_rejected_answer_is_still_recorded(tmp_path):
    _run(tmp_path, ZERO_PAGE, 'rows: "x"\nunknown_key: 1\n')
    rec = yaml.safe_load(_records(tmp_path)[0][0].read_text(encoding="utf-8"))
    assert "schema" in rec["error"] and rec["agy"]["recipe_yaml"].startswith("rows:")
    assert rec["reached"] == "answered" and "new_recipe" not in rec


def test_adopted_proposal_is_recorded_with_path(tmp_path):
    _run(tmp_path, GOOD_PAGE, GOOD_AI)
    rec = yaml.safe_load(_records(tmp_path)[0][0].read_text(encoding="utf-8"))
    assert (
        rec["status"] == "ok" and rec["count"] == 2 and rec["proposal_path"].endswith("x_test.yaml")
    )
    assert rec["new_recipe"]["count"] == 2


def test_second_run_same_day_does_not_overwrite(tmp_path):
    _run(tmp_path, ZERO_PAGE, ZERO_AI, hms="00:05:00")
    _run(tmp_path, JUNK_PAGE, JUNK_AI, hms="16:04:00")
    ymls, htmls = _records(tmp_path)
    assert [p.name for p in ymls] == [
        "x_test-2026-11-05T000500.yaml",
        "x_test-2026-11-05T160400.yaml",
    ]
    assert [p.read_text(encoding="utf-8") for p in htmls] == [
        ZERO_PAGE,
        JUNK_PAGE,
    ]  # today.html を上書きしない


def test_old_date_directories_are_rotated_at_run_start(tmp_path):
    root = tmp_path / "data" / "repair_attempts"
    for d in ("2026-10-05", "2026-10-06", "2026-11-04"):
        (root / d).mkdir(parents=True)
        (root / d / "a.yaml").write_text("x: 1\n", encoding="utf-8")
    (root / "memo.txt").parent.mkdir(parents=True, exist_ok=True)
    (root / "memo.txt").write_text("日付名でないものは触らない", encoding="utf-8")
    _run(tmp_path, ZERO_PAGE, ZERO_AI, date="2026-11-05")
    left = sorted(p.name for p in root.iterdir())
    assert left == [
        "2026-10-06",
        "2026-11-04",
        "2026-11-05",
        "memo.txt",
    ]  # 30 日より前（10/05）だけ消える


def test_record_failure_never_breaks_collection(tmp_path, monkeypatch):
    from collector import run as run_mod

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(run_mod, "write_attempt", boom)
    out = _run(tmp_path, ZERO_PAGE, ZERO_AI)
    assert (
        out["sources"][0]["status"] == "failed" and "AI 修復に失敗" in out["sources"][0]["repair"]
    )
