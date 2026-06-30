"""auto_fix_adapter.py のテスト

LLM 呼び出しと git/gh の subprocess を mock し、純粋ロジック
(extract_diff / evaluate_improvement / _slugify / build_prompt / apply_patch)
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


class TestExtractDiff:
    def test_diff_code_block(self):
        text = """ここはサマリ
```diff
--- a/foo.py
+++ b/foo.py
@@ -1 +1 @@
-old
+new
```
余分な後書き
"""
        result = afa.extract_diff(text)
        assert result.startswith("--- a/foo.py")
        assert "+new" in result
        assert "余分な後書き" not in result

    def test_generic_code_block_fallback(self):
        text = "```\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n```"
        result = afa.extract_diff(text)
        assert "+b" in result

    def test_raw_text_when_no_code_block(self):
        text = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"
        result = afa.extract_diff(text)
        assert result == text.strip()


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
        assert "unified diff" in system_msg
        assert "サイトX" in user_msg
        assert "https://example.lg.jp/list" in user_msg
        assert "class Foo: pass" in user_msg
        assert "detail_error" in user_msg
        assert "RawAnimalData" in user_msg
        # diff format header の指示が含まれる
        assert "--- a/" in user_msg


class TestApplyPatch:
    def test_applies_valid_diff(self, tmp_path):
        # 一時 git リポジトリで apply
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "test"], cwd=tmp_path, check=True, capture_output=True
        )
        target = tmp_path / "x.txt"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        subprocess.run(["git", "add", "x.txt"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
        )

        patch = """--- a/x.txt
+++ b/x.txt
@@ -1,3 +1,3 @@
 alpha
-beta
+BETA
 gamma
"""
        assert afa.apply_patch(patch, cwd=tmp_path) is True
        assert "BETA" in target.read_text(encoding="utf-8")

    def test_returns_false_on_invalid_diff(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        # 対象ファイルがないので apply 失敗するはず
        patch = """--- a/nope.txt
+++ b/nope.txt
@@ -1 +1 @@
-a
+b
"""
        assert afa.apply_patch(patch, cwd=tmp_path) is False

    def test_recount_tolerates_wrong_hunk_line_count(self, tmp_path):
        """LLM が出しがちな『ハンクヘッダの行数が実ハンクとズレた diff』を
        --recount で救えることを確認 (本物の山梨県 patch で踏んだ corrupt ケース)。"""
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "t@e.com"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True
        )
        target = tmp_path / "x.txt"
        target.write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
        subprocess.run(["git", "add", "x.txt"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True
        )
        # ヘッダは「-1,3 +1,3」と宣言するが、実際は旧4行(alpha/beta/gamma/delta)・
        # 新3行 で行数が合わず、--recount 無しでは "corrupt patch" になる。
        patch = """--- a/x.txt
+++ b/x.txt
@@ -1,3 +1,3 @@
 alpha
-beta
-gamma
+BETAGAMMA
 delta
"""
        assert afa.apply_patch(patch, cwd=tmp_path) is True
        assert "BETAGAMMA" in target.read_text(encoding="utf-8")


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
            msg = type("M", (), {"content": "OK-PATCH"})()
            return type("Resp", (), {"choices": [type("C", (), {"message": msg})()]})()

        class FakeClient:
            def __init__(self, **_kw):
                self.chat = type(
                    "Chat",
                    (),
                    {"completions": type("Comp", (), {"create": staticmethod(fake_create)})()},
                )()

        monkeypatch.setattr(openai, "OpenAI", FakeClient)

        result = afa.ask_llm_for_patch(
            "code", ROOT / "scripts" / "auto_fix_adapter.py", None, None, {}
        )
        assert calls["n"] == 2  # 1回目 429 → 2回目成功
        assert "OK-PATCH" in result


class TestValidatePatchScope:
    """diff が「指定 adapter ファイル」のみを変更することを enforce する gate。

    LLM が prompt の制約を無視してテストや他ファイルを書き換えるパッチを返した
    場合に apply_patch の前で reject する。これが無いと「テスト改ざんでガード1
    を欺いた garbage adapter」が auto-merge される最悪ケースが残る。
    """

    def test_single_allowed_file_passes(self):
        patch = """--- a/src/data_collector/adapters/rule_based/sites/foo.py
+++ b/src/data_collector/adapters/rule_based/sites/foo.py
@@ -1 +1 @@
-old
+new
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is True
        assert reason == "ok"

    def test_test_file_change_rejected(self):
        """tests/ 配下を含む diff は reject。これが core gate。"""
        patch = """--- a/src/data_collector/adapters/rule_based/sites/foo.py
+++ b/src/data_collector/adapters/rule_based/sites/foo.py
@@ -1 +1 @@
-old
+new
--- a/tests/adapters/rule_based/sites/test_foo.py
+++ b/tests/adapters/rule_based/sites/test_foo.py
@@ -10 +10 @@
-    assert breed == "雑種"
+    assert breed is None
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "tests/" in reason

    def test_other_adapter_change_rejected(self):
        """1 サイト修復で他 adapter を巻き込む diff も reject。"""
        patch = """--- a/src/data_collector/adapters/rule_based/sites/foo.py
+++ b/src/data_collector/adapters/rule_based/sites/foo.py
@@ -1 +1 @@
-old
+new
--- a/src/data_collector/adapters/rule_based/sites/bar.py
+++ b/src/data_collector/adapters/rule_based/sites/bar.py
@@ -1 +1 @@
-x
+y
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "bar.py" in reason

    def test_normalizer_change_rejected(self):
        """domain/normalizer.py 等の基盤層書き換えも reject。"""
        patch = """--- a/src/data_collector/domain/normalizer.py
+++ b/src/data_collector/domain/normalizer.py
@@ -1 +1 @@
-old
+new
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "normalizer.py" in reason

    def test_file_deletion_rejected(self):
        """+++ /dev/null (ファイル削除) を含むパッチは reject。"""
        patch = """--- a/src/data_collector/adapters/rule_based/sites/foo.py
+++ /dev/null
@@ -1,3 +0,0 @@
-line1
-line2
-line3
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "deletion" in reason or "/dev/null" in reason

    def test_new_file_creation_rejected(self):
        """--- /dev/null (新規ファイル作成) を含むパッチは reject。"""
        patch = """--- /dev/null
+++ b/src/data_collector/adapters/rule_based/sites/new.py
@@ -0,0 +1,3 @@
+line1
+line2
+line3
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "creation" in reason or "/dev/null" in reason

    def test_empty_patch_rejected(self):
        """空 / ヘッダなし の patch は reject。"""
        ok, reason = afa.validate_patch_scope(
            "", ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "no file" in reason.lower() or "header" in reason.lower()

    def test_path_without_a_b_prefix_is_handled(self):
        """diff のパスに a/ b/ prefix が無いケース (git apply は受け付ける) も検証。"""
        patch = """--- src/data_collector/adapters/rule_based/sites/foo.py
+++ src/data_collector/adapters/rule_based/sites/foo.py
@@ -1 +1 @@
-old
+new
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is True, f"unexpected reject: {reason}"

    def test_workflow_file_change_rejected(self):
        """`.github/workflows/` 配下の変更も reject (auto-fix のスコープ外)。"""
        patch = """--- a/.github/workflows/data-collector.yml
+++ b/.github/workflows/data-collector.yml
@@ -1 +1 @@
-old
+new
"""
        ok, reason = afa.validate_patch_scope(
            patch, ["src/data_collector/adapters/rule_based/sites/foo.py"]
        )
        assert ok is False
        assert "workflows" in reason or ".yml" in reason


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
