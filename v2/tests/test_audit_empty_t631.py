"""W006 T631: ops/audit_empty.py（子がいた日の保存ページに今のレシピを当て、0 頭の根拠が成立する slug を挙げる）。ネットワークなし。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from collector.recipe import Recipe
from collector.registry import Source

AUDIT_PY = Path(__file__).resolve().parent.parent / "ops" / "audit_empty.py"
URL = "https://www.city.example.jp/a/"
ZERO = "現在、保護している犬はいません"
ANIMAL = '<ul><li class="animal"><img src="/a.jpg"></li></ul>'


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_audit_empty", AUDIT_PY)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod  # dataclass（from __future__ annotations）が型を引くのに要る
    spec.loader.exec_module(mod)
    return mod


def _src(slug: str) -> Source:
    return Source(
        slug=slug,
        name=slug,
        municipality="x市",
        prefecture="x県",
        url=URL,
        kind="stray",
        species="dog",
    )


def _save(data: Path, slug: str, html: str, extra: dict[str, str] | None = None) -> None:
    """last_ok と同じ形（index.json + N.bin）で保存ページを置く。"""
    d = data / "last_ok" / slug
    d.mkdir(parents=True)
    pages = {URL: html, **(extra or {})}
    docs = []
    for i, (u, body) in enumerate(pages.items()):
        (d / f"{i}.bin").write_bytes(body.encode("utf-8"))
        docs.append({"url": u, "final_url": u, "file": f"{i}.bin"})
    (d / "index.json").write_text(
        json.dumps({"date": "2026-11-05", "count": 1, "docs": docs}), encoding="utf-8"
    )


def _recipe(**kw) -> Recipe:
    return Recipe.from_dict({"rows": "li.animal", **kw})


def test_detects_empty_text_that_matches_on_a_day_with_animals(tmp_path):
    m = _mod()
    # 子がいる日にも出る文（別の節の雛形）。今のレシピなら読み方が崩れた日に「本日は 0 頭」と出てしまう
    _save(tmp_path, "bad-1", f"<body>{ANIMAL}<p>{ZERO}</p><p>{ZERO}</p></body>")
    found = m.run_audit(tmp_path, [(_src("bad-1"), _recipe(empty_text=[ZERO, "ほかの文"]))])
    assert len(found) == 1
    f = found[0]
    assert (f.slug, f.kind, f.detail, f.count, f.url) == ("bad-1", "empty_text", ZERO, 2, URL)


def test_does_not_report_slug_whose_phrase_is_absent(tmp_path):
    m = _mod()
    _save(tmp_path, "good-1", f"<body>{ANIMAL}</body>")
    assert m.run_audit(tmp_path, [(_src("good-1"), _recipe(empty_text=[ZERO]))]) == []


def test_day_without_animals_is_not_a_child_day(tmp_path):
    m = _mod()
    # 保存ページに今のレシピを当てて 0 頭なら「子がいた日」ではないので、根拠が成立していても対象外
    _save(tmp_path, "zero-1", f"<body><p>{ZERO}</p></body>")
    assert m.run_audit(tmp_path, [(_src("zero-1"), _recipe(empty_text=[ZERO]))]) == []


def test_reports_url_of_followed_document_and_img_alt(tmp_path):
    m = _mod()
    child = "https://www.city.example.jp/a/child1/"
    _save(
        tmp_path,
        "deep-1",
        '<body><a href="child1/">c</a></body>',
        {child: f'<body>{ANIMAL}<img alt="{ZERO}" src="/n.png"></body>'},
    )
    rec = _recipe(empty_text=[ZERO], steps=[{"follow_all": "a@href"}], max_pages=5)
    found = m.run_audit(tmp_path, [(_src("deep-1"), rec)])
    assert [(f.kind, f.detail, f.url) for f in found] == [("empty_text", ZERO, child)]


def test_detects_empty_selector_and_empty_absent(tmp_path):
    m = _mod()
    _save(tmp_path, "sel-1", f'<body>{ANIMAL}<div class="box"></div></body>')
    _save(tmp_path, "abs-1", f"<body><h1>一覧</h1>{ANIMAL}</body>")
    found = m.run_audit(
        tmp_path,
        [
            (_src("sel-1"), _recipe(empty_selector=["div.box"])),
            # none の器が実際の行と別の名前なので、子がいる日にも「器が無い」が成立する
            (_src("abs-1"), _recipe(empty_absent={"page": "h1", "none": "ul.listlink"})),
        ],
    )
    assert sorted((f.slug, f.kind) for f in found) == [
        ("abs-1", "empty_absent"),
        ("sel-1", "empty_selector"),
    ]


def test_empty_text_all_hit_only_when_every_phrase_present(tmp_path):
    m = _mod()
    cat = "現在、保護している猫はいません"
    _save(tmp_path, "all-hit", f"<body>{ANIMAL}<p>{ZERO}</p><p>{cat}</p></body>")
    _save(tmp_path, "all-part", f"<body>{ANIMAL}<p>{ZERO}</p></body>")
    rec = _recipe(empty_text_all=[ZERO, cat])
    found = m.run_audit(tmp_path, [(_src("all-hit"), rec), (_src("all-part"), rec)])
    assert [(f.slug, f.kind) for f in found] == [("all-hit", "empty_text_all")]


def test_slug_without_last_ok_or_with_broken_page_is_skipped_not_crashed(tmp_path):
    m = _mod()
    _save(tmp_path, "broken-1", "<body>x</body>")
    (tmp_path / "last_ok" / "broken-1" / "0.bin").unlink()
    found = m.run_audit(
        tmp_path,
        [
            (_src("none-1"), _recipe(empty_text=[ZERO])),
            (_src("broken-1"), _recipe(empty_text=[ZERO])),
        ],
    )
    assert found == []


# --- 通知 --------------------------------------------------------------------
def _finds(m, *slugs):
    return [m.Finding(s, "empty_text", ZERO, URL, 1) for s in slugs]


def test_notify_sends_only_when_the_set_changed(tmp_path):
    m = _mod()
    sent: list[str] = []
    state = tmp_path / "audit_empty_state.json"
    assert (
        m.notify_if_changed(_finds(m, "a-1", "b-1"), state, sent.append) is True
    )  # 初回: 前回なし → 送る
    assert (
        m.notify_if_changed(_finds(m, "b-1", "a-1"), state, sent.append) is False
    )  # 同じ集合（順序違い）→ 送らない
    assert m.notify_if_changed(_finds(m, "a-1"), state, sent.append) is True  # 減った → 送る
    assert m.notify_if_changed(_finds(m, "a-1", "c-1"), state, sent.append) is True  # 増えた → 送る
    assert len(sent) == 3
    assert "a-1" in sent[2] and "c-1" in sent[2]
    assert json.loads(state.read_text(encoding="utf-8"))["slugs"] == ["a-1", "c-1"]


def test_notify_first_run_with_nothing_found_stays_silent(tmp_path):
    m = _mod()
    sent: list[str] = []
    assert m.notify_if_changed([], tmp_path / "s.json", sent.append) is False and sent == []


def test_notify_failure_to_send_does_not_record_state(tmp_path):
    m = _mod()
    state = tmp_path / "s.json"

    def boom(_msg: str) -> None:
        raise OSError("down")

    try:
        m.notify_if_changed(_finds(m, "a-1"), state, boom)
    except OSError:
        pass
    assert not state.exists()  # 送れなかった日は記録しない（翌日また送る）
