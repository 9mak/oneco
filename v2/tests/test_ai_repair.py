"""AI 修復のテスト（ネットワークなし。Claude の呼び出しは差し替える）。"""

from pathlib import Path

import pytest

from collector import ai_repair
from collector.ai_repair import RepairResult, extract_yaml, repair, strip_html
from collector.fetch import FakeFetcher
from collector.registry import Source
from collector.run import run

URL = "https://x.test/animals/"
PAGE = """<html><head><style>.a{color:red}</style><script>var x = 1;</script></head><body>
<h2>保護犬情報</h2>
<table class="list">
  <tr><th>写真</th><th>性別</th><th>収容日</th></tr>
  <tr><td><img src="photo/d1.jpg"></td><td>メス</td><td>令和8年9月20日</td></tr>
  <tr><td><img src="photo/d2.jpg"></td><td>オス</td><td>令和8年9月21日</td></tr>
</table></body></html>"""

OLD_RECIPE = "# 古い（サイト改修前）\nrows: \"ul.animals > li\"\nfields:\n  sex: {label: \"性別\"}\n"
NEW_RECIPE = "# 1 頭 = table.list の tr\nrows: \"table.list tr\"\nfields:\n  sex: \"td:nth-of-type(2)\"\n  shelter_date: \"td:nth-of-type(3)\"\n"


def _source(tmp_path: Path) -> Source:
    p = tmp_path / "x_test.yaml"
    p.write_text(OLD_RECIPE, encoding="utf-8")
    # recipe に絶対パスを入れると ROOT / 絶対パス = 絶対パス になる
    return Source(slug="x_test", name="テスト市", municipality="テスト市", prefecture="テスト県",
                  url=URL, kind="sheltered", species="dog", recipe=str(p))


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def test_saves_recipe_when_claude_yaml_works(tmp_path, api_key):
    src = _source(tmp_path)
    calls: list[tuple[str, str, str]] = []

    def fake_ask(system: str, user: str, model: str) -> str:
        calls.append((system, user, model))
        return "```yaml\n" + NEW_RECIPE + "```"

    r = repair(src, fetcher=FakeFetcher({URL: PAGE}), ask=fake_ask, error="0 頭で empty_text も無い")
    assert r.status == "ok" and r.count == 2 and r.saved
    assert src.recipe_path.read_text(encoding="utf-8") == NEW_RECIPE
    # Claude に渡したもの: 現行レシピ・RECIPE.md・script/style を除いた本文・失敗理由
    system, user, model = calls[0]
    assert model == ai_repair.DEFAULT_MODEL
    assert OLD_RECIPE in user and "0 頭で empty_text も無い" in user
    assert "## レシピの書き方" in user and "rows" in user
    assert "photo/d1.jpg" in user and "var x = 1" not in user and "color:red" not in user


def test_restores_recipe_when_claude_yaml_fails(tmp_path, api_key):
    src = _source(tmp_path)

    def fake_ask(system: str, user: str, model: str) -> str:
        return "rows: \"div.nothing\"\nfields:\n  sex: {label: \"性別\"}\n"   # 何も取れないレシピ

    r = repair(src, fetcher=FakeFetcher({URL: PAGE}), ask=fake_ask)
    assert r.status == "failed" and not r.saved and "0 頭" in (r.error or "")
    assert src.recipe_path.read_text(encoding="utf-8") == OLD_RECIPE

    # YAML として壊れていても元のまま
    r = repair(src, fetcher=FakeFetcher({URL: PAGE}), ask=lambda s, u, m: "rows: [unclosed\n  - :\n")
    assert r.status == "failed" and "新レシピが動かない" in (r.error or "")
    assert src.recipe_path.read_text(encoding="utf-8") == OLD_RECIPE


def test_no_api_key_does_not_call_claude(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    src = _source(tmp_path)
    r = repair(src, fetcher=FakeFetcher({URL: PAGE}), ask=lambda s, u, m: pytest.fail("呼ばれてはいけない"))
    assert r.status == "no_key"
    assert src.recipe_path.read_text(encoding="utf-8") == OLD_RECIPE


def test_run_repairs_once_and_recollects(tmp_path, api_key, monkeypatch):
    src = _source(tmp_path)
    monkeypatch.setattr(ai_repair, "ask_claude", lambda s, u, m: NEW_RECIPE)
    out = run([src], "2026-09-28", out_dir=tmp_path / "data", fetcher=FakeFetcher({URL: PAGE}), enabled=True)
    assert len(out["animals"]) == 2
    rep = out["sources"][0]
    assert rep["status"] == "ok" and rep["count"] == 2 and rep["repair"].startswith("AI がレシピを書き直した")
    assert src.recipe_path.read_text(encoding="utf-8") == NEW_RECIPE


def test_run_without_repair_leaves_failed(tmp_path, api_key, monkeypatch):
    src = _source(tmp_path)
    monkeypatch.setattr(ai_repair, "ask_claude", lambda s, u, m: pytest.fail("enabled=False では呼ばれない"))
    out = run([src], "2026-09-28", out_dir=tmp_path / "data", fetcher=FakeFetcher({URL: PAGE}), enabled=False)
    assert out["sources"][0]["status"] == "failed" and out["sources"][0]["repair"] is None
    assert src.recipe_path.read_text(encoding="utf-8") == OLD_RECIPE


def test_helpers():
    assert extract_yaml("```yaml\nrows: a\n```") == "rows: a\n"
    assert extract_yaml("rows: a") == "rows: a\n"
    body = strip_html(PAGE, limit=100)
    assert len(body) <= 100 and "<script" not in body and "<style" not in body
    assert "photo/d1.jpg" in strip_html(PAGE)
