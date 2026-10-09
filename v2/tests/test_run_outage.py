"""回線断などで読めないページが多すぎる日は latest.json を書き換えない（サイトは前日のまま。W005 の原則）。
2026-10-04 13:25 の launchd 試運転で回線が途中で落ち、229 ページ中 119 が ConnectError になった（624 頭）。"""

import json

from collector import run as run_mod
from collector.extract import Result
from collector.fetch import FakeFetcher
from collector.notify import build_message
from collector.registry import Source


def _sources(n: int) -> list[Source]:
    return [Source(slug=f"s{i}", name=f"市{i}", municipality=f"市{i}", prefecture="東京都", url=f"https://x.jp/{i}",
                   kind="stray", species="dog") for i in range(n)]


def _fake_collect(failed: set[str]):
    def collect_one(s, fetcher):
        if s.slug in failed:
            return "failed", None, "ConnectError: [Errno 8] nodename nor servname provided, or not known", []
        res = Result(docs=1)
        res.animals.append({"id": s.slug, "source": s.slug})
        return "ok", res, None, []
    return collect_one


def test_outage_keeps_previous_latest(tmp_path, monkeypatch):
    (tmp_path / "latest.json").write_text('{"date": "2026-10-03", "animals": [1, 2, 3]}', encoding="utf-8")
    srcs = _sources(10)
    monkeypatch.setattr(run_mod, "collect_one", _fake_collect({f"s{i}" for i in range(5)}))   # 5/10 = 50% 失敗
    out = run_mod.run(srcs, "2026-10-04", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    assert out["held"] is True
    assert json.loads((tmp_path / "latest.json").read_text())["date"] == "2026-10-03"     # 前日のまま
    assert (tmp_path / "animals-2026-10-04.json").exists() and (tmp_path / "report-2026-10-04.json").exists()
    msg = build_message(json.loads((tmp_path / "report-2026-10-04.json").read_text()))
    assert msg is not None and msg.startswith("読めなかったページが多すぎる")                # 通知の先頭で分かる


def test_normal_day_updates_latest(tmp_path, monkeypatch):
    (tmp_path / "latest.json").write_text('{"date": "2026-10-03", "animals": []}', encoding="utf-8")
    srcs = _sources(10)
    monkeypatch.setattr(run_mod, "collect_one", _fake_collect({"s0"}))                       # 1/10 = 10% 失敗
    out = run_mod.run(srcs, "2026-10-04", out_dir=tmp_path, fetcher=FakeFetcher({}), enabled=False)
    assert out["held"] is False
    assert json.loads((tmp_path / "latest.json").read_text())["date"] == "2026-10-04"
    msg = build_message(json.loads((tmp_path / "report-2026-10-04.json").read_text()))
    assert msg is not None and msg.startswith("読めなかった自治体 1 件")
