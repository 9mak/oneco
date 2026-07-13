"""auto_fix_adapter.py のテスト

LLM 呼び出しと git/gh の subprocess を mock し、純粋ロジック
(extract_search_replace_blocks / apply_search_replace_edits / evaluate_improvement /
_slugify / build_prompt / apply_full_file_replacement)
を単体で検証する。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# scripts/ をパスに通して auto_fix_adapter を import
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import auto_fix_adapter as afa  # noqa: E402


class TestExtractSearchReplaceBlocks:
    def test_single_block(self):
        text = """ここはサマリ
<<<<<<< SEARCH
old_line
=======
new_line
>>>>>>> REPLACE
余分な後書き
"""
        result = afa.extract_search_replace_blocks(text)
        assert result == [("old_line", "new_line")]

    def test_multiple_blocks(self):
        text = """<<<<<<< SEARCH
a
=======
A
>>>>>>> REPLACE

<<<<<<< SEARCH
b
=======
B
>>>>>>> REPLACE
"""
        result = afa.extract_search_replace_blocks(text)
        assert result == [("a", "A"), ("b", "B")]

    def test_no_blocks_returns_empty_list(self):
        assert afa.extract_search_replace_blocks("説明文だけで形式無視") == []

    def test_multiline_search_and_replace(self):
        text = """<<<<<<< SEARCH
    ROW_SELECTOR: ClassVar[str] = "div.menu_item"
    SKIP_FIRST_ROW: ClassVar[bool] = False
=======
    ROW_SELECTOR: ClassVar[str] = "div.new_item"
    SKIP_FIRST_ROW: ClassVar[bool] = True
>>>>>>> REPLACE
"""
        result = afa.extract_search_replace_blocks(text)
        assert len(result) == 1
        search, replace = result[0]
        assert "div.menu_item" in search
        assert "div.new_item" in replace

    def test_reversed_arrow_direction_is_tolerated(self):
        """llama-3.3-70b は実測で `>>>>>>> SEARCH` / `<<<<<<< REPLACE` のように
        矢印の向きを逆にすることがあった。向きは区切り記号としてのみ扱い、
        どちらの向きでも受理する。"""
        text = """>>>>>>> SEARCH
old_line
=======
new_line
<<<<<<< REPLACE
"""
        result = afa.extract_search_replace_blocks(text)
        assert result == [("old_line", "new_line")]


class TestApplySearchReplaceEdits:
    def test_single_edit_applies(self):
        original = "class Foo:\n    x = 1\n    y = 2\n"
        blocks = [("x = 1", "x = 99")]
        new_code, reason = afa.apply_search_replace_edits(original, blocks)
        assert reason == "ok"
        assert new_code == "class Foo:\n    x = 99\n    y = 2\n"

    def test_multiple_edits_apply_in_sequence(self):
        original = "class Foo:\n    x = 1\n    y = 2\n"
        blocks = [("x = 1", "x = 99"), ("y = 2", "y = 100")]
        new_code, reason = afa.apply_search_replace_edits(original, blocks)
        assert reason == "ok"
        assert new_code == "class Foo:\n    x = 99\n    y = 100\n"

    def test_no_blocks_rejected(self):
        new_code, reason = afa.apply_search_replace_edits("class Foo:\n    pass\n", [])
        assert new_code is None
        assert "no search/replace" in reason.lower()

    def test_search_not_found_rejected(self):
        original = "class Foo:\n    x = 1\n"
        new_code, reason = afa.apply_search_replace_edits(original, [("z = 9", "z = 10")])
        assert new_code is None
        assert "not found" in reason.lower()
        # 元のファイルは変更されない (呼び出し側が None を見て書き込みをスキップする)
        assert original == "class Foo:\n    x = 1\n"

    def test_ambiguous_search_rejected(self):
        """SEARCH が複数箇所にマッチする場合は、誤った箇所を書き換えるリスクを
        避けるため安全側に倒して reject する。"""
        original = "class Foo:\n    x = 1\nclass Bar:\n    x = 1\n"
        new_code, reason = afa.apply_search_replace_edits(original, [("x = 1", "x = 99")])
        assert new_code is None
        assert "ambiguous" in reason.lower() or "2" in reason


class TestSlugify:
    def test_japanese_name_to_slug(self):
        # 全角文字は -, ascii 化される
        assert afa._slugify("川崎市（収容犬）") == "site" or "kawasaki" in afa._slugify(
            "Kawasaki City"
        )

    def test_ascii_name_normalization(self):
        assert afa._slugify("Oita City Dog") == "oita-city-dog"

    def test_truncation(self):
        long_name = "a" * 100
        slug = afa._slugify(long_name)
        assert len(slug) <= 40

    def test_empty_fallback(self):
        assert afa._slugify("") == "site"
        assert afa._slugify("（）") == "site"


class TestEvaluateImprovement:
    def test_detail_error_to_ok_is_improvement(self):
        before = afa.Metrics(status="detail_error", list_count=3)
        after = afa.Metrics(status="ok", list_count=3, missing_rates={"location": 0.0})
        improved, reason = afa.evaluate_improvement(before, after)
        assert improved is True
        assert "ok" in reason

    def test_empty_to_ok_is_improvement(self):
        before = afa.Metrics(status="empty", list_count=0)
        after = afa.Metrics(status="ok", list_count=5, missing_rates={"location": 0.0})
        improved, reason = afa.evaluate_improvement(before, after)
        assert improved is True
        assert "5" in reason

    def test_missing_rate_drop_is_improvement(self):
        before = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 1.0})
        after = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.2})
        improved, reason = afa.evaluate_improvement(before, after)
        assert improved is True
        assert "location" in reason

    def test_small_missing_rate_change_not_improvement(self):
        before = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.50})
        after = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.48})
        improved, _ = afa.evaluate_improvement(before, after)
        assert improved is False

    def test_no_change_no_improvement(self):
        before = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.3})
        after = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.3})
        improved, _ = afa.evaluate_improvement(before, after)
        assert improved is False

    def test_regression_not_improvement(self):
        # 欠損率が悪化したケースは improvement ではない
        before = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.2})
        after = afa.Metrics(status="ok", list_count=10, missing_rates={"location": 0.9})
        improved, _ = afa.evaluate_improvement(before, after)
        assert improved is False


class TestBuildPrompt:
    def test_includes_essential_inputs(self):
        from data_collector.llm.config import SiteConfig

        sc = SiteConfig(
            name="サイトX",
            prefecture="東京都",
            prefecture_code="13",
            list_url="https://example.lg.jp/list",
            category="sheltered",
            single_page=False,
        )
        before = afa.Metrics(status="detail_error", list_count=1, detail_errors=1)
        samples = {
            "list_html": "<html>list</html>",
            "detail_url": "https://example.lg.jp/detail/1",
            "detail_html": "<html>detail</html>",
        }
        system_msg, user_msg = afa.build_prompt(
            adapter_code="class Foo: pass",
            adapter_file_rel="src/.../foo.py",
            site_config=sc,
            before=before,
            samples=samples,
        )
        assert "rule-based" in system_msg
        assert "SEARCH/REPLACE" in system_msg
        assert "サイトX" in user_msg
        assert "https://example.lg.jp/list" in user_msg
        assert "class Foo: pass" in user_msg
        assert "detail_error" in user_msg
        assert "RawAnimalData" in user_msg
        # SEARCH/REPLACE 形式の出力指示が含まれ、全文出力は明示的に禁止されている
        assert "<<<<<<< SEARCH" in user_msg
        assert ">>>>>>> REPLACE" in user_msg
        assert "ファイル全文は出力しない" in user_msg


class TestValidateFullFileReplacement:
    """LLM が返した『修正後の完全なファイル内容』を書き込み前に検証する gate。

    diff 方式では LLM が行番号/context を幻覚し git apply が『patch does not
    apply』で落ち続けた (実測: 山梨県 adapter、--recount 導入後も解消せず)。
    全文書き込み方式ではこの失敗クラス自体が発生しない代わりに、LLM が壊れた/
    無関係な内容を返すケースを別の観点で弾く必要がある。
    """

    def test_valid_python_with_class_and_registration_passes(self):
        code = "class FooAdapter:\n    pass\n\nSiteAdapterRegistry.register('foo', FooAdapter)\n"
        ok, reason = afa.validate_full_file_replacement(code, "FooAdapter")
        assert ok is True
        assert reason == "ok"

    def test_empty_content_rejected(self):
        ok, reason = afa.validate_full_file_replacement("   \n", "FooAdapter")
        assert ok is False
        assert "empty" in reason.lower()

    def test_syntax_error_rejected(self):
        code = "class FooAdapter(:\n    pass\n"
        ok, reason = afa.validate_full_file_replacement(code, "FooAdapter")
        assert ok is False
        assert "valid python" in reason.lower()

    def test_missing_class_name_rejected(self):
        """クラス名が消えている = registry から脱落しサイトがサイレントに
        収集対象外になる。過去のサイレントドロップと同種のリスクなので reject。"""
        code = (
            "class SomethingElse:\n    pass\n\nSiteAdapterRegistry.register('foo', SomethingElse)\n"
        )
        ok, reason = afa.validate_full_file_replacement(code, "FooAdapter")
        assert ok is False
        assert "FooAdapter" in reason

    def test_missing_registration_call_rejected(self):
        code = "class FooAdapter:\n    pass\n"
        ok, reason = afa.validate_full_file_replacement(code, "FooAdapter")
        assert ok is False
        assert "register" in reason.lower()


class TestApplyFullFileReplacement:
    def test_writes_valid_replacement(self, tmp_path):
        target = tmp_path / "adapter.py"
        target.write_text("class FooAdapter:\n    pass\n", encoding="utf-8")
        new_code = (
            "class FooAdapter:\n    x = 1\n\nSiteAdapterRegistry.register('foo', FooAdapter)\n"
        )
        ok, reason = afa.apply_full_file_replacement(new_code, target, "FooAdapter")
        assert ok is True
        assert reason == "ok"
        assert target.read_text(encoding="utf-8") == new_code

    def test_rejected_replacement_does_not_touch_file(self, tmp_path):
        target = tmp_path / "adapter.py"
        original = "class FooAdapter:\n    pass\n"
        target.write_text(original, encoding="utf-8")
        ok, _reason = afa.apply_full_file_replacement("", target, "FooAdapter")
        assert ok is False
        assert target.read_text(encoding="utf-8") == original


class TestCompressHtml:
    def test_strips_script_style_comment_and_collapses_whitespace(self):
        html = (
            "<div>  a   b\n\n<script>var x=1;</script>"
            "<style>.c{color:red}</style>\n  <!-- note -->  <span>keep</span></div>"
        )
        out = afa._compress_html(html)
        assert "<script>" not in out and "var x" not in out
        assert "<style>" not in out and "color:red" not in out
        assert "<!--" not in out and "note" not in out
        assert "  " not in out  # 連続空白は1つに圧縮
        assert "<span>keep</span>" in out  # タグ構造とラベルは保持
        assert "<div>" in out


class TestRetryAfterSeconds:
    @staticmethod
    def _err(headers):
        response = type("Resp", (), {"headers": headers})()
        return type("Err", (Exception,), {"response": response})()

    def test_reads_numeric_header(self):
        assert afa._retry_after_seconds(self._err({"retry-after": "30"})) == 30.0

    def test_absent_header_returns_none(self):
        assert afa._retry_after_seconds(self._err({})) is None

    def test_garbage_header_returns_none(self):
        assert afa._retry_after_seconds(self._err({"retry-after": "soon"})) is None

    def test_no_response_returns_none(self):
        assert afa._retry_after_seconds(Exception("x")) is None


class TestRateLimitRetry:
    def test_retries_on_rate_limit_then_succeeds(self, monkeypatch):
        """並列 dispatch で 429 を踏んでも、待って再試行し成功することを確認。
        build_prompt はスタブ化し (TestBuildPrompt で別途カバー)、retry 制御だけ検証。"""
        import httpx
        import openai

        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setattr(afa.time, "sleep", lambda _s: None)
        monkeypatch.setattr(afa, "build_prompt", lambda *a, **k: ("sys", "user"))

        calls = {"n": 0}

        def fake_create(**_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
                resp = httpx.Response(429, headers={"retry-after": "1"}, request=req)
                raise openai.RateLimitError("rate limited", response=resp, body=None)
            content = "<<<<<<< SEARCH\nold\n=======\nOK-PATCH\n>>>>>>> REPLACE"
            msg = type("M", (), {"content": content})()
            return type("Resp", (), {"choices": [type("C", (), {"message": msg})()]})()

        class FakeClient:
            def __init__(self, **_kw):
                self.chat = type(
                    "Chat",
                    (),
                    {"completions": type("Comp", (), {"create": staticmethod(fake_create)})()},
                )()

        monkeypatch.setattr(openai, "OpenAI", FakeClient)

        result = afa.ask_llm_for_fix(
            "code", ROOT / "scripts" / "auto_fix_adapter.py", None, None, {}
        )
        assert calls["n"] == 2  # 1回目 429 → 2回目成功
        assert result == [("old", "OK-PATCH")]


class TestVerifyNoUnexpectedChanges:
    """git status で allowed 以外に変更が無いことを再確認する gate。"""

    def _init_git(self, path: Path) -> None:
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "test"], cwd=path, check=True, capture_output=True
        )

    def test_clean_tree_passes(self, tmp_path):
        self._init_git(tmp_path)
        ok, reason = afa.verify_no_unexpected_changes(["adapter.py"], cwd=tmp_path)
        assert ok is True
        assert reason == "ok"

    def test_only_allowed_file_dirty_passes(self, tmp_path):
        self._init_git(tmp_path)
        (tmp_path / "adapter.py").write_text("x", encoding="utf-8")
        ok, reason = afa.verify_no_unexpected_changes(["adapter.py"], cwd=tmp_path)
        assert ok is True, f"unexpected reject: {reason}"

    def test_test_file_dirty_rejected(self, tmp_path):
        """テストファイルが書き換わっていたら reject (test 改ざんの最後の砦)。"""
        self._init_git(tmp_path)
        (tmp_path / "adapter.py").write_text("x", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_adapter.py").write_text("y", encoding="utf-8")
        ok, reason = afa.verify_no_unexpected_changes(["adapter.py"], cwd=tmp_path)
        assert ok is False
        assert "tests/test_adapter.py" in reason

    def test_other_file_dirty_rejected(self, tmp_path):
        self._init_git(tmp_path)
        (tmp_path / "adapter.py").write_text("x", encoding="utf-8")
        (tmp_path / "other.py").write_text("y", encoding="utf-8")
        ok, reason = afa.verify_no_unexpected_changes(["adapter.py"], cwd=tmp_path)
        assert ok is False
        assert "other.py" in reason


class TestMetrics:
    def test_to_dict_serializable(self):
        m = afa.Metrics(status="ok", list_count=5, missing_rates={"location": 0.1})
        d = m.to_dict()
        assert d["status"] == "ok"
        assert d["list_count"] == 5
        assert d["missing_rates"]["location"] == pytest.approx(0.1)
        # JSON シリアライズ可能
        import json

        json.dumps(d)

    def test_to_dict_with_none_missing_rates(self):
        m = afa.Metrics(status="empty", list_count=0)
        d = m.to_dict()
        assert d["missing_rates"] == {}


class TestDryRunExit:
    """観察モード (--dry-run) では『LLM 提案が却下された』はスクリプトの失敗では
    なく想定内の観察結果。GitHub Actions の step を赤にして Discord ノイズにする
    のを避けるため、当該 exit code は 0 に丸める。

    exit 2 (LLM 呼び出し自体の例外) は却下ではなく本当のスクリプト障害なので、
    dry-run でも丸めない。"""

    def test_rejection_codes_neutralized_in_dry_run(self):
        for code in (3, 4, 5):
            assert afa._dry_run_exit(code, dry_run=True) == 0

    def test_rejection_codes_preserved_when_not_dry_run(self):
        for code in (3, 4, 5):
            assert afa._dry_run_exit(code, dry_run=False) == code

    def test_llm_call_failure_not_neutralized_even_in_dry_run(self):
        assert afa._dry_run_exit(2, dry_run=True) == 2

    def test_success_code_passthrough(self):
        assert afa._dry_run_exit(0, dry_run=True) == 0
        assert afa._dry_run_exit(0, dry_run=False) == 0


class TestGhWarning:
    """修復却下時の GitHub Actions warning annotation

    dry-run では却下 (exit 3/4/5) を 0 に丸めるため、workflow conclusion
    だけ見ると全 run が success になり、パッチ適用失敗が 2 週間
    サイレントに続いた (2026-07 発見)。annotation なら conclusion を
    変えずに run 一覧・summary 上で失敗が見える。
    """

    def test_emits_single_line_warning_annotation(self, capsys):
        afa.gh_warning("パッチ適用失敗 (SEARCH block not found)")
        out = capsys.readouterr().out
        assert out.startswith("::warning::")
        assert "パッチ適用失敗" in out

    def test_newlines_are_flattened(self, capsys):
        """annotation は 1 行でないと GitHub が後続を無視する"""
        afa.gh_warning("1行目\n2行目\n3行目")
        out = capsys.readouterr().out.rstrip("\n")
        assert "\n" not in out
        assert "2行目" in out
