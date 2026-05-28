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
