"""data-collector → auto-fix-adapter 自動橋渡しのテスト

検知シグナル (broken_tracker.critical_sites / zero_count_regressions /
field_drifts) を集約して `gh workflow run auto-fix-adapter.yml` を起動する
ロジックを検証する。subprocess を mock して呼び出し回数・引数を assert。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from src.data_collector.__main__ import _trigger_auto_fix


def _logger() -> logging.Logger:
    return logging.getLogger("test_trigger_auto_fix")


class TestTriggerAutoFix:
    def test_disabled_does_not_invoke(self, monkeypatch):
        """ONECO_AUTO_FIX_ENABLED が未設定/false なら gh workflow run を呼ばない。"""
        monkeypatch.delenv("ONECO_AUTO_FIX_ENABLED", raising=False)
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            result = _trigger_auto_fix(["サイトA", "サイトB"], logger=_logger())
        assert result == {"invoked": 0, "attempted": 0, "candidates": 2, "disabled": True}
        mock_run.assert_not_called()

    def test_enabled_invokes_gh_workflow_run(self, monkeypatch):
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _trigger_auto_fix(["サイトA"], logger=_logger())
        assert result["invoked"] == 1
        assert result["attempted"] == 1
        assert result["candidates"] == 1
        assert result["disabled"] is False
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["gh", "workflow", "run"]
        assert "auto-fix-adapter.yml" in cmd
        # site_name input
        assert "site_name=サイトA" in cmd

    def test_dry_run_default_true(self, monkeypatch):
        """初期はサイレントドロップ回避のため dry_run=true デフォルト。"""
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        monkeypatch.delenv("ONECO_AUTO_FIX_DRY_RUN", raising=False)
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _trigger_auto_fix(["サイトA"], logger=_logger())
        cmd = mock_run.call_args[0][0]
        assert "dry_run=true" in cmd

    def test_dry_run_false_when_explicit(self, monkeypatch):
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        monkeypatch.setenv("ONECO_AUTO_FIX_DRY_RUN", "false")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _trigger_auto_fix(["サイトA"], logger=_logger())
        cmd = mock_run.call_args[0][0]
        assert "dry_run=false" in cmd

    def test_dispatch_failures_visible_in_result(self, monkeypatch):
        """dispatch 失敗を attempted > invoked で可視化する (silent failure 防止)。
        この差分が Discord summary に出ることで「自己修復が静かに動いていない」
        状態を検知できる (これが無いと feature 自体が silent fail する皮肉)。"""
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        monkeypatch.setenv("ONECO_AUTO_FIX_MAX_SITES", "3")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="token has no actions: write scope"
            )
            result = _trigger_auto_fix(["A", "B", "C"], logger=_logger())
        assert result["invoked"] == 0
        assert result["attempted"] == 3
        # attempted > invoked = 全件失敗 = critical な silent failure 兆候

    def test_max_sites_caps_invocations(self, monkeypatch):
        """並列爆発・LLM コスト爆発防止のため 1 run あたり最大 N サイト。"""
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        monkeypatch.setenv("ONECO_AUTO_FIX_MAX_SITES", "2")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _trigger_auto_fix(
                ["サイトA", "サイトB", "サイトC", "サイトD"], logger=_logger()
            )
        assert result["invoked"] == 2
        assert result["candidates"] == 4
        assert mock_run.call_count == 2

    def test_empty_input_no_invocations(self, monkeypatch):
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            result = _trigger_auto_fix([], logger=_logger())
        assert result == {"invoked": 0, "attempted": 0, "candidates": 0, "disabled": False}
        mock_run.assert_not_called()

    def test_dedup_site_names(self, monkeypatch):
        """同じサイトが複数経路 (broken + drift + zero) から来ても 1 度だけ起動。"""
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        monkeypatch.setenv("ONECO_AUTO_FIX_MAX_SITES", "10")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            result = _trigger_auto_fix(
                ["サイトA", "サイトB", "サイトA", "サイトA"], logger=_logger()
            )
        assert result["invoked"] == 2  # サイトA + サイトB
        assert result["candidates"] == 2  # dedup 後
        # 順序保持 dedup
        call_sites = [c[0][0] for c in mock_run.call_args_list]
        flat = [arg for cmd in call_sites for arg in cmd]
        assert sum(1 for x in flat if x == "site_name=サイトA") == 1
        assert sum(1 for x in flat if x == "site_name=サイトB") == 1

    def test_gh_failure_is_swallowed_and_continues(self, monkeypatch):
        """gh workflow run が失敗しても collection は止めない。残サイトの起動継続。
        attempted=3 / invoked=2 の差分が silent failure シグナルになる。"""
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        monkeypatch.setenv("ONECO_AUTO_FIX_MAX_SITES", "5")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="", stderr=""),
                MagicMock(returncode=1, stdout="", stderr="not authorized"),
                MagicMock(returncode=0, stdout="", stderr=""),
            ]
            result = _trigger_auto_fix(["A", "B", "C"], logger=_logger())
        # 2 件成功 (A, C)、B は失敗だがクラッシュしない。attempted=3.
        assert result["invoked"] == 2
        assert result["attempted"] == 3
        assert result["candidates"] == 3
        assert mock_run.call_count == 3

    def test_subprocess_exception_swallowed(self, monkeypatch):
        """subprocess 自体が例外 (gh CLI 未インストール等) でもクラッシュしない。
        attempted は試行数を反映 (= 1)、invoked は 0 のまま。"""
        monkeypatch.setenv("ONECO_AUTO_FIX_ENABLED", "true")
        with patch("src.data_collector.__main__.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("gh: command not found")
            result = _trigger_auto_fix(["サイトA"], logger=_logger())
        # クラッシュせず 0 件成功・1 件試行
        assert result["invoked"] == 0
        assert result["attempted"] == 1
