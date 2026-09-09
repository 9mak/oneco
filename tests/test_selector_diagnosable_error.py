"""検知シグナルの選別ロジックのテスト (T406)

broken_tracker.critical_sites / zero_count_regressions の検知結果を
構造診断 (diagnosis.py) にかける前段のフィルタ (`_is_selector_diagnosable_error`)
と、0件回帰の軽量再検証 (`_verify_zero_regressions`) を検証する。
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from src.data_collector.__main__ import (
    _is_selector_diagnosable_error,
    _verify_zero_regressions,
)
from src.data_collector.infrastructure.site_baseline_tracker import ZeroCountRegression
from src.data_collector.infrastructure.zero_count_verifier import ZeroCountVerification


def _logger() -> logging.Logger:
    return logging.getLogger("test_selector_diagnosable_error")


def _regression(name: str) -> ZeroCountRegression:
    return ZeroCountRegression(
        site_name=name, baseline_count=1, consecutive_zero_runs=2, last_nonzero_at=None
    )


class TestIsSelectorDiagnosableError:
    """critical_sites の失敗原因が LLM コード修正で直せるかの分類

    ネットワーク断・HTTP エラー・タイムアウトは adapter コードを
    いくらパッチしても直らないため診断対象から除外する
    (2026-07 に山梨県のネットワーク断続エラーが日次 3 枠を 2 週間
    占有し、本当に壊れていた柏市・群馬に修理が回らなかった反省)。
    """

    def test_network_error_is_not_fixable(self):
        # broken_sites.yaml の実記録 (山梨県)
        assert not _is_selector_diagnosable_error(
            "ネットワークエラー: HTTPSConnectionPool(host='www.pref.yamanashi.jp', port=443): "
            "Max retries exceeded with url: /doubutsu/p_dog/index.html "
            "(Caused by NewConnectionError(...: Failed to establish a new connection: "
            "[Errno 111] Connection refused))"
        )

    def test_connect_timeout_is_not_fixable(self):
        assert not _is_selector_diagnosable_error(
            "ネットワークエラー: HTTPSConnectionPool(host='aniwel.jp', port=443): "
            "Max retries exceeded with url: /cats/ (Caused by ConnectTimeoutError(..., "
            "'Connection to aniwel.jp timed out. (connect timeout=30)'))"
        )

    def test_http_error_is_not_fixable(self):
        # 403/404 はコード修正では直らない (URL 変更 / WAF ブロック)
        assert not _is_selector_diagnosable_error(
            "HTTP エラー: 403 Client Error: Forbidden for url: https://www.city.nagoya.jp/..."
        )

    def test_site_timeout_is_not_fixable(self):
        # per-site SIGALRM timeout (処理が固まった) もコード修正対象外
        assert not _is_selector_diagnosable_error(
            "timeout: site 山梨県（探している犬） timed out after 120.0s"
        )
        assert not _is_selector_diagnosable_error(
            "site collection timed out after 240s: 高知県動物愛護センター"
        )

    def test_parsing_error_is_fixable(self):
        # DOM 構造変化 → セレクタ修正で直せる本来の診断対象
        assert _is_selector_diagnosable_error("行要素が見つかりません")

    def test_zero_count_anomaly_is_fixable(self):
        assert _is_selector_diagnosable_error(
            "件数低下異常: 前回 2 件 → 今回 0 件 (adapter 破損 or サイト構造変更の可能性)"
        )

    def test_unknown_or_empty_error_is_fixable(self):
        # 分類不能な失敗は安全側 (= 従来通り対象に含める)
        assert _is_selector_diagnosable_error("")
        assert _is_selector_diagnosable_error(None)
        assert _is_selector_diagnosable_error("RawAnimalData バリデーション失敗: ...")


class TestVerifyZeroRegressions:
    """0件回帰検知の直後にかける軽量再検証 (LLM不使用)。

    baseline 1〜2件の薄いサイトが一時的に0件になっただけの誤検知
    (2026-07-24 実データ: 検知15件中14件がbaseline 1〜2件)を、
    thresholdを緩めるのではなく毎回の軽量チェックで弾く。
    """

    def test_should_flag_true_is_kept(self, monkeypatch):
        adapter_cls = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(
            "src.data_collector.__main__.SiteAdapterRegistry.get",
            lambda name: adapter_cls,
        )
        monkeypatch.setattr(
            "src.data_collector.__main__.verify_zero_count",
            lambda adapter, list_url: ZeroCountVerification(should_flag=True, reason="怪しい"),
        )
        site = MagicMock(list_url="https://example.com/")
        result = _verify_zero_regressions(
            [_regression("サイトA")], sites_by_name={"サイトA": site}, logger=_logger()
        )
        assert [r.site_name for r in result] == ["サイトA"]

    def test_should_flag_false_is_removed(self, monkeypatch):
        adapter_cls = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(
            "src.data_collector.__main__.SiteAdapterRegistry.get",
            lambda name: adapter_cls,
        )
        monkeypatch.setattr(
            "src.data_collector.__main__.verify_zero_count",
            lambda adapter, list_url: ZeroCountVerification(should_flag=False, reason="正常"),
        )
        site = MagicMock(list_url="https://example.com/")
        result = _verify_zero_regressions(
            [_regression("サイトA")], sites_by_name={"サイトA": site}, logger=_logger()
        )
        assert result == []

    def test_missing_site_config_falls_back_to_flagged(self, monkeypatch):
        """site_config が見つからない(未登録等) → 安全側で候補に残す"""
        result = _verify_zero_regressions(
            [_regression("未知のサイト")], sites_by_name={}, logger=_logger()
        )
        assert [r.site_name for r in result] == ["未知のサイト"]

    def test_missing_adapter_falls_back_to_flagged(self, monkeypatch):
        """adapter が registry に未登録 → 安全側で候補に残す"""
        monkeypatch.setattr(
            "src.data_collector.__main__.SiteAdapterRegistry.get", lambda name: None
        )
        site = MagicMock(list_url="https://example.com/")
        result = _verify_zero_regressions(
            [_regression("サイトA")], sites_by_name={"サイトA": site}, logger=_logger()
        )
        assert [r.site_name for r in result] == ["サイトA"]

    def test_exception_during_verification_falls_back_to_flagged(self, monkeypatch):
        adapter_cls = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(
            "src.data_collector.__main__.SiteAdapterRegistry.get",
            lambda name: adapter_cls,
        )
        site = MagicMock(list_url="https://example.com/")
        result = _verify_zero_regressions(
            [_regression("サイトA")], sites_by_name={"サイトA": site}, logger=_logger()
        )
        assert [r.site_name for r in result] == ["サイトA"]

    def test_multiple_sites_each_judged_independently(self, monkeypatch):
        adapter_cls = MagicMock(return_value=MagicMock())
        monkeypatch.setattr(
            "src.data_collector.__main__.SiteAdapterRegistry.get",
            lambda name: adapter_cls,
        )

        def fake_verify(adapter, list_url):
            flagged = "壊れてる" in list_url
            return ZeroCountVerification(should_flag=flagged, reason="test")

        monkeypatch.setattr("src.data_collector.__main__.verify_zero_count", fake_verify)
        sites_by_name = {
            "正常サイト": MagicMock(list_url="https://ok.example.com/"),
            "壊れサイト": MagicMock(list_url="https://壊れてる.example.com/"),
        }
        result = _verify_zero_regressions(
            [_regression("正常サイト"), _regression("壊れサイト")],
            sites_by_name=sites_by_name,
            logger=_logger(),
        )
        assert [r.site_name for r in result] == ["壊れサイト"]
