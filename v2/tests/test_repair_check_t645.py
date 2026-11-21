"""W006 T645: エージェントのあとに必ず通す固定の検査（repair-check）。エージェントは偽物（ファイルを書くだけ）で、pytest・ruff も差し替える。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from collector import repair_check as rc

SLUG = "x_test"
YMD = "20261121"
URL = "https://x.test/animals/"
OLD_RECIPE = '# 古い（サイト改修前）\nrows: "ul.animals > li"\nfields:\n  sex: "span.sex"\n'
NEW_RECIPE = '# 1 頭 = table.list の tr\nrows: "table.list tr"\nfields:\n  sex: "td:nth-of-type(2)"\n  shelter_date: "td:nth-of-type(3)"\n'
BOTH_RECIPE = ('# 旧と新の両方を読む\nrows: "table.list tr, ul.animals > li"\nfields:\n  sex: "td:nth-of-type(2), span.sex"\n'
               '  shelter_date: "td:nth-of-type(3)"\n')
TODAY = """<html><body><h2>保護犬情報</h2><table class="list">
<tr><th>写真</th><th>性別</th><th>収容日</th></tr>
<tr><td><img src="photo/d1.jpg"></td><td>メス</td><td>令和8年9月20日</td></tr>
<tr><td><img src="photo/d2.jpg"></td><td>オス</td><td>令和8年9月21日</td></tr>
</table></body></html>"""
TODAY_EMPTY = '<html><body><h2>保護犬情報</h2><p>現在、収容している犬はいません。</p><table class="list"></table></body></html>'
PAST_OLD = """<html><body><ul class="animals">
<li><img src="photo/o1.jpg"><span class="sex">メス</span></li>
<li><img src="photo/o2.jpg"><span class="sex">オス</span></li></ul></body></html>"""
SOURCES = f"""sources:
  - slug: {SLUG}
    name: テスト市
    municipality: テスト市
    prefecture: テスト県
    url: {URL}
    kind: sheltered
    species: dog
"""
TEST_PY = "def test_repro():\n    assert True\n"


def _git(wt: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True)


@pytest.fixture
def wt(tmp_path) -> Path:
    r = tmp_path / "wt"
    for rel, text in {
        "v2/registry/sources.yaml": SOURCES,
        f"v2/recipes/{SLUG}.yaml": OLD_RECIPE,
        f"v2/tests/fixtures/{SLUG}_20261001.html": PAST_OLD,
        "v2/collector/x.py": "x = 1\n",
    }.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "init", "-q", "-b", "main"], check=True)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "base")
    _git(r, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(r, "checkout", "-q", "-b", f"repair/{SLUG}")
    return r


def _agent(wt: Path, recipe: str = NEW_RECIPE, today: str | None = TODAY, test: str | None = TEST_PY, extra: dict | None = None) -> None:
    """偽のエージェント: レシピを直し、今日のページと試験を足す。"""
    files = {f"v2/recipes/{SLUG}.yaml": recipe, f"v2/tests/fixtures/repair_{SLUG}_{YMD}.html": today,
             f"v2/tests/test_repair_{SLUG}_{YMD}.py": test, **(extra or {})}
    for rel, text in files.items():
        if text is None:
            continue
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text, encoding="utf-8")


class Exec:
    """pytest・ruff の差し替え。Red の確認（旧レシピに戻した状態）では新しい試験が落ちるふり。"""

    def __init__(self, wt: Path, full_rc: int = 0, new_rc: int = 0, ruff_rc: int = 0, red_passes: bool = False) -> None:
        self.wt, self.full_rc, self.new_rc, self.ruff_rc, self.red_passes = wt, full_rc, new_rc, ruff_rc, red_passes
        self.calls: list[list[str]] = []
        self.envs: list[dict] = []

    def __call__(self, cmd: list[str], cwd: Path, env: dict | None, timeout: int) -> tuple[int, str]:
        self.calls.append(list(cmd))
        self.envs.append(env or {})
        assert cwd == self.wt
        if "ruff" in cmd:
            return self.ruff_rc, "All checks passed!" if self.ruff_rc == 0 else "E999 boom"
        if rc_is_old(self.wt):
            return (0, "1 passed in 0.1s") if self.red_passes else (1, "1 failed in 0.1s")
        if any(c.endswith(".py") for c in cmd):
            return self.new_rc, "3 passed in 0.1s" if self.new_rc == 0 else "1 failed, 2 passed"
        return self.full_rc, "4052 passed, 80 warnings in 500s" if self.full_rc == 0 else "3 failed, 4049 passed"


def rc_is_old(wt: Path) -> bool:
    return (wt / f"v2/recipes/{SLUG}.yaml").read_text(encoding="utf-8").startswith("# 古い")


def _check(wt: Path, **kw) -> rc.CheckResult:
    return rc.check(SLUG, wt, exec_fn=Exec(wt, **kw))


def test_good_fix_passes_with_numbers(wt):
    _agent(wt, BOTH_RECIPE)
    ex = Exec(wt)
    res = rc.check(SLUG, wt, exec_fn=ex)
    assert res.ok, res.problems
    d = res.details
    assert d["before_count"] == 0 and d["after_count"] == 2
    assert d["regression_compared"] == 1 and d["tests_total"] == 4052 and d["tests_added"] == 3
    assert sorted(d["changed_files"]) == sorted([f"v2/recipes/{SLUG}.yaml", f"v2/tests/fixtures/repair_{SLUG}_{YMD}.html",
                                                  f"v2/tests/test_repair_{SLUG}_{YMD}.py"])
    # 追加した試験 → 全体 → ruff の順。ruff は台帳と同じ設定で
    flat = [" ".join(c) for c in ex.calls]
    assert any(f"test_repair_{SLUG}_{YMD}.py" in c for c in flat)
    assert any(c.endswith("-m ruff check --config ruff.toml v2") for c in flat)
    # 作業ツリーの v2 を先に見る（本番の collector でなく）
    assert all(e.get("PYTHONPATH") == str(wt / "v2") for e in ex.envs)


def test_recipe_restored_after_red_check(wt):
    _agent(wt, BOTH_RECIPE)
    _check(wt)
    assert (wt / f"v2/recipes/{SLUG}.yaml").read_text(encoding="utf-8") == BOTH_RECIPE


@pytest.mark.parametrize("extra", [
    {"v2/collector/x.py": "x = 2\n"},
    {"v2/registry/sources.yaml": SOURCES.replace("テスト市", "別の市")},
    {"v2/recipes/other.yaml": "rows: a\n"},
    {".github/workflows/x.yml": "on: push\n"},
    {"v2/tests/test_other.py": "def test_a(): pass\n"},
    {f"v2/tests/test_repair_other_{YMD}.py": TEST_PY},
    {"v2/tests/fixtures/something.html": "<p>x</p>"},
])
def test_paths_outside_allowed_are_rejected(wt, extra):
    _agent(wt, BOTH_RECIPE, extra=extra)
    res = _check(wt)
    assert not res.ok and any("触ってよいパス" in p for p in res.problems)


def test_pytest_and_ruff_not_run_when_cheap_checks_fail(wt):
    _agent(wt, BOTH_RECIPE, extra={"v2/collector/x.py": "x = 2\n"})
    ex = Exec(wt)
    rc.check(SLUG, wt, exec_fn=ex)
    assert ex.calls == []


def test_missing_test_file_or_unchanged_recipe_is_rejected(wt):
    _agent(wt, BOTH_RECIPE, test=None)
    assert any("試験" in p for p in _check(wt).problems)


def test_unchanged_recipe_is_rejected(wt):
    _agent(wt, OLD_RECIPE)
    assert any("レシピが変わっていない" in p for p in _check(wt).problems)


def test_schema_violation_is_rejected(wt):
    _agent(wt, BOTH_RECIPE + "url: https://evil.test/\n")
    res = _check(wt)
    assert not res.ok and any("schema" in p for p in res.problems)


def test_today_fixture_missing_is_rejected(wt):
    _agent(wt, BOTH_RECIPE, today=None)
    assert any("今日のページ" in p for p in _check(wt).problems)


def test_zero_animals_without_evidence_is_rejected(wt):
    # 雛形の表だけで、0 頭の根拠（empty_text など）が無い
    _agent(wt, BOTH_RECIPE, today="<html><body><table class='list'><tr><td></td></tr></table></body></html>")
    res = _check(wt)
    assert not res.ok and any("0 頭" in p for p in res.problems)


def test_zero_animals_with_real_empty_text_passes(wt):
    (wt / f"v2/tests/fixtures/{SLUG}_20261001.html").unlink()   # 過去の fixture が無い slug
    _git(wt, "commit", "-q", "-am", "x", "--allow-empty")
    _git(wt, "update-ref", "refs/remotes/origin/main", "HEAD")
    _agent(wt, NEW_RECIPE + 'empty_text: ["現在、収容している犬はいません"]\n', today=TODAY_EMPTY)
    res = _check(wt)
    assert res.ok, res.problems
    assert res.details["after_count"] == 0 and res.details["empty_evidence"] == "empty_text"


def test_zero_animals_with_template_text_marker_only_rejected(wt):
    # 全行を除外しただけ（all_excluded）は 0 頭の根拠にしない
    page = '<html><body><table class="list"><tr><td>見本</td><td></td></tr></table></body></html>'
    _agent(wt, NEW_RECIPE + 'row_filter:\n  text_lacks: ["見本"]\n', today=page)
    assert not _check(wt).ok


def test_adoption_violation_on_today_is_rejected(wt):
    # 見出しの語がそのまま値に入る
    bad = '<html><body><table class="list"><tr><td><img src="a.jpg"></td><td>性別：メス</td><td>収容日</td></tr></table></body></html>'
    _agent(wt, BOTH_RECIPE, today=bad)
    res = _check(wt)
    assert not res.ok and any("今日のページ" in p or "見出し" in p or "日付" in p for p in res.problems)


def test_regression_on_past_fixture_is_rejected(wt):
    _agent(wt, NEW_RECIPE)       # 今の構造だけ読み、過去の構造（旧レシピが 2 頭読めていた）を読まなくなる
    res = _check(wt)
    assert not res.ok and any("退行" in p for p in res.problems)


def test_regression_when_ids_change(wt):
    other = BOTH_RECIPE.replace('rows: "table.list tr, ul.animals > li"', 'rows: "table.list tr, ul.animals > li:first-child"')
    _agent(wt, other)
    res = _check(wt)
    assert not res.ok and any("退行" in p for p in res.problems)


@pytest.mark.parametrize("pii", ["TEL 090-1234-5678", "mail someone@gmail.com", "TEL ０９０－１２３４－５６７８"])
def test_personal_contact_in_diff_is_rejected(wt, pii):
    _agent(wt, BOTH_RECIPE, today=TODAY.replace("<h2>", f"<p>{pii}</p><h2>"))
    res = _check(wt)
    assert not res.ok and any("連絡先" in p for p in res.problems)


def test_placeholder_contact_is_allowed(wt):
    _agent(wt, BOTH_RECIPE, today=TODAY.replace("<h2>", "<p>TEL 090-0000-0000 masked@example.jp 095-895-2364</p><h2>"))
    assert _check(wt).ok


def test_new_test_that_passes_on_old_recipe_is_rejected(wt):
    _agent(wt, BOTH_RECIPE)
    res = _check(wt, red_passes=True)
    assert not res.ok and any("直す前" in p for p in res.problems)


def test_failing_added_test_full_suite_or_ruff_is_rejected(wt):
    _agent(wt, BOTH_RECIPE)
    assert any("追加した試験" in p for p in _check(wt, new_rc=1).problems)
    assert any("全体の pytest" in p for p in _check(wt, full_rc=1).problems)
    assert any("ruff" in p for p in _check(wt, ruff_rc=1).problems)


def test_existing_tests_that_mention_slug_run_before_full_suite(wt):
    (wt / "v2/tests/test_old_x.py").write_text(f'SLUG = "{SLUG}"\n', encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "t")
    _git(wt, "update-ref", "refs/remotes/origin/main", "HEAD")
    _agent(wt, BOTH_RECIPE)
    ex = Exec(wt)
    rc.check(SLUG, wt, exec_fn=ex)
    targeted = [c for c in ex.calls if any(x.endswith("test_old_x.py") for x in c)]
    assert targeted and any(x.endswith(f"test_repair_{SLUG}_{YMD}.py") for x in targeted[0])


def test_committed_changes_are_also_checked(wt):
    # エージェントが commit していても、origin/main との差分で見る
    _agent(wt, BOTH_RECIPE, extra={"v2/collector/x.py": "x = 3\n"})
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", "agent")
    assert any("触ってよいパス" in p for p in _check(wt).problems)


def test_pages_json_lets_check_serve_child_pages(wt):
    child = ('<html><body><div class="d"><img src="c1.jpg"><span class="sex">メス</span></div></body></html>')
    index = '<html><body><a class="detail" href="/animals/1.html">1</a></body></html>'
    recipe = ('# 子を辿る\nsteps:\n  - follow_all: "a.detail@href"\nrows: "div.d"\nfields:\n  sex: "span.sex"\n')
    (wt / f"v2/tests/fixtures/{SLUG}_20261001.html").unlink()
    _git(wt, "commit", "-q", "-am", "x", "--allow-empty")
    _git(wt, "update-ref", "refs/remotes/origin/main", "HEAD")
    pages = '{"https://x.test/animals/1.html": "repair_x_test_20261121_c1.html"}'
    _agent(wt, recipe, today=index, extra={f"v2/tests/fixtures/repair_{SLUG}_{YMD}_pages.json": pages,
                                           f"v2/tests/fixtures/repair_{SLUG}_{YMD}_c1.html": child})
    res = _check(wt)
    assert res.ok, res.problems
    assert res.details["after_count"] == 1
