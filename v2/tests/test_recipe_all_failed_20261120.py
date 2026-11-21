"""W006 T656 付随・項目 6: recipe.py の _raise_if_all_failed が、全部失敗の例外に子の失敗理由（ErrorInfo）を持たせる（2026-11-20）。

`failed` には文字列（"URL: HTTP 404: URL"）しか入らないので `isinstance(failed[0], FetchError)` は常に偽で、
例外の info は常に other だった。run.py はその穴を「メッセージに HTTP 404・410 が入っているか」の正規表現
（_GONE_IN_MESSAGE）で埋めていた。子の FetchError の info をそのまま渡し、正規表現は外す。
掲載の読み方・通知（children_gone の印と kind=http・status=404）は変わらない。
"""

import pytest
from collector import run as run_mod
from collector.fetch import FakeFetcher, FetchError, page_gone
from collector.recipe import Executor, Recipe
from collector.registry import Source

LIST = '<html><body><a class="d" href="/c/1.html">1</a><a class="d" href="/c/2.html">2</a></body></html>'
ENTRY = "https://a.jp/list"


def _recipe(tmp_path, step: str = 'follow_all: "a.d@href"') -> Recipe:
    p = tmp_path / "f.yaml"
    p.write_text(f"steps:\n  - {step}\n    skip_errors: true\nrows: \"body\"\n", encoding="utf-8")
    return Recipe.load(p)


@pytest.mark.parametrize("code", [404, 410])
def test_all_children_gone_raises_with_the_childs_error_info(tmp_path, code):
    fetcher = FakeFetcher({ENTRY: LIST}, status={"https://a.jp/c/1.html": code, "https://a.jp/c/2.html": code})
    with pytest.raises(FetchError) as ei:
        Executor(fetcher, _recipe(tmp_path)).resolve(ENTRY)
    info = ei.value.info
    assert info.kind == "http" and info.status == code and info.host == "a.jp"
    assert info.url == "https://a.jp/c/1.html"          # 最初に失敗した子
    assert page_gone(ei.value)                           # メッセージの正規表現でなく info で「ページが無い」と分かる
    assert "辿った 2 本がすべて取得に失敗" in str(ei.value) and "https://a.jp/c/1.html: HTTP" in str(ei.value)


def test_some_children_ok_does_not_raise(tmp_path):
    fetcher = FakeFetcher({ENTRY: LIST, "https://a.jp/c/1.html": "<html><body>x</body></html>"}, status={"https://a.jp/c/2.html": 404})
    docs = Executor(fetcher, _recipe(tmp_path)).resolve(ENTRY)
    assert len(docs) == 1


def test_run_no_longer_needs_the_message_regex(tmp_path):
    assert not hasattr(run_mod, "_GONE_IN_MESSAGE")
    fetcher = FakeFetcher({ENTRY: LIST}, status={"https://a.jp/c/1.html": 404, "https://a.jp/c/2.html": 404})
    with pytest.raises(FetchError) as ei:
        Executor(fetcher, _recipe(tmp_path)).resolve(ENTRY)
    assert run_mod._is_gone(ei.value)


def test_collect_one_result_is_unchanged(tmp_path):
    s = Source(slug="f1", name="f1市", municipality="f1", prefecture="東京都", url=ENTRY, kind="stray", species="dog",
               recipe=str(_recipe_path(tmp_path)))
    fetcher = FakeFetcher({ENTRY: LIST}, status={"https://a.jp/c/1.html": 404, "https://a.jp/c/2.html": 404})
    c = run_mod.collect_one(s, fetcher)
    assert c.status == "failed" and c.error_info["children_gone"] is True
    assert c.error_info["kind"] == "http" and c.error_info["status"] == 404
    assert c.error_info["url"] is None   # 入口の 404 と区別する（children_gone の作り。run.collect_one）


def _recipe_path(tmp_path):
    _recipe(tmp_path)
    return tmp_path / "f.yaml"
