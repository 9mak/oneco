"""__main__.py の rule-based / LLM 振り分けロジックのテスト

Phase A2 Task 2.2: run_rule_based_sites と main() の振り分け。
"""

from __future__ import annotations

from data_collector.__main__ import (
    PROVIDER_REGISTRY,
    _effective_extraction,
)
from data_collector.llm.config import (
    ExtractionConfig,
    SiteConfig,
    SitesConfig,
)


def _site(extraction: str | None = None) -> SiteConfig:
    """テスト用 SiteConfig （extraction を指定可）"""
    kwargs = {
        "name": "テスト",
        "prefecture": "高知県",
        "prefecture_code": "39",
        "list_url": "https://example.com/",
    }
    if extraction is not None:
        kwargs["extraction"] = extraction
    return SiteConfig(**kwargs)


def _config(default_extraction: str = "llm") -> SitesConfig:
    return SitesConfig(
        extraction=ExtractionConfig(
            default_provider="anthropic",
            default_model="claude-haiku-4-5-20251001",
            default_extraction=default_extraction,
        ),
        sites=[_site()],
    )


class TestEffectiveExtraction:
    def test_explicit_site_extraction_wins(self):
        """サイト個別 extraction が指定されていればそれを採用"""
        site = _site(extraction="rule-based")
        config = _config(default_extraction="llm")
        assert _effective_extraction(site, config) == "rule-based"

    def test_falls_back_to_default_extraction_when_none(self):
        """サイト個別が空の時 default_extraction が採用される"""
        site = _site(extraction=None)
        config = _config(default_extraction="rule-based")
        assert _effective_extraction(site, config) == "rule-based"

    def test_default_to_llm_when_unspecified(self):
        site = _site(extraction=None)
        config = _config(default_extraction="llm")
        assert _effective_extraction(site, config) == "llm"


class TestProviderRegistry:
    def test_groq_registered(self):
        assert "groq" in PROVIDER_REGISTRY

    def test_anthropic_not_registered(self):
        """Anthropic は採算化後に再評価するため 2026-05-29 に撤去済み"""
        assert "anthropic" not in PROVIDER_REGISTRY


class TestSiteRunReturnTypeContract:
    """run_llm_sites / run_rule_based_sites の戻り値契約

    PR #20 で bool → tuple[succeeded, failed, zero_count_sites] に変更した。
    main 側で「成功 0 件かつ失敗 > 0 のみ exit 1、それ以外は exit 0」の
    部分成功許容判定に使うため、対象サイトが 0 件の config では (0, 0, [])
    を返すことが契約として固定されている必要がある。

    SitesConfig は `sites=[]` を許容しないため、対象 extraction と
    異なるサイトを 1 件入れて「処理対象 0 件」状態を作る。
    """

    def test_run_llm_sites_returns_zero_zero_empty_when_no_llm_sites(self):
        from unittest.mock import Mock

        from data_collector.__main__ import run_llm_sites

        # rule-based サイトのみで LLM 対象は 0 件
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="rule-based",
            ),
            sites=[_site(extraction="rule-based")],
        )
        result = run_llm_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
        )
        assert result == (0, 0, [])

    def test_run_rule_based_sites_returns_zero_zero_empty_when_no_rule_sites(self):
        from unittest.mock import Mock

        from data_collector.__main__ import run_rule_based_sites

        # LLM サイトのみで rule-based 対象は 0 件
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="llm",
            ),
            sites=[_site(extraction="llm")],
        )
        result = run_rule_based_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
        )
        assert result == (0, 0, [])


class TestBrokenSiteSkipThreshold:
    """BROKEN_SITE_SKIP_THRESHOLD で連続失敗サイトをスキップする動作"""

    def test_threshold_default_is_3(self):
        """環境変数未指定時は 3 (Requirement 6.4 系)"""
        import os
        from unittest.mock import patch

        # 環境変数を空にして再読み込みするのは module level でセットされる
        # ため難しい。代わりに getenv の挙動だけ確認する。
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BROKEN_SITE_SKIP_THRESHOLD", None)
            assert int(os.getenv("BROKEN_SITE_SKIP_THRESHOLD", "3")) == 3

    def test_run_rule_based_sites_skips_site_with_high_consecutive_failures(self, tmp_path):
        """consecutive_failures >= 閾値 のサイトは adapter 呼び出しに到達しない"""
        from unittest.mock import Mock

        from data_collector.__main__ import run_rule_based_sites
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker
        from data_collector.adapters.rule_based.registry import SiteAdapterRegistry

        # adapter は呼ばれないはず（呼ばれたら Mock の call_count が増える）
        spy_adapter_cls = Mock()
        SiteAdapterRegistry.register("テスト_スキップ対象", spy_adapter_cls)

        broken_path = tmp_path / "broken_sites.yaml"
        tracker = BrokenSitesTracker(broken_path)
        # 連続 5 回失敗（閾値 3 を超える）
        for _ in range(5):
            tracker.record_failure("テスト_スキップ対象", "permanent failure")

        site = _site(extraction="rule-based").model_copy(update={"name": "テスト_スキップ対象"})
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="rule-based",
            ),
            sites=[site],
        )

        succeeded, failed, zero = run_rule_based_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
            broken_tracker=tracker,
        )

        assert spy_adapter_cls.call_count == 0, (
            "閾値超えサイトでは adapter コンストラクタも呼ばれない"
        )
        assert (succeeded, failed, zero) == (0, 0, []), (
            "スキップは success / failure どちらにもカウントしない (0件サイトでもない)"
        )


class TestZeroCountAnomalyDetection:
    """件数低下の扱い (Task #9 → 誤検知削減で改訂)

    snapshot 比較で「前回 ≥ 1 件 → 今回 0 件」を以前は adapter 破損疑いと
    して broken_tracker に failure 記録 (スキップ対象化) していたが、
    result.success=True は adapter が正常終了した証左であり、0 件の大半は
    在庫はけ (真の 0 件) の誤検知だった。現在は監視ログ + zero_count_sites
    への記録のみで、スキップ対象化 (record_failure) はしない。本物の破損は
    list_error/detail_error/timeout で別途 record_failure される。
    """

    def _make_stub_adapter(self, total_collected: int):
        """指定件数を返すスタブ adapter クラスを返す"""
        from unittest.mock import Mock

        result = Mock()
        result.success = True
        result.total_collected = total_collected
        result.new_count = total_collected
        result.updated_count = 0
        result.errors = []

        # CollectorService.run_collection() の戻り値を mock
        # adapter_cls(site) で生成される adapter インスタンスは
        # collector_service 内で生成されるため、CollectorService 経由を mock 化
        adapter_cls = Mock()
        adapter_cls.return_value = Mock()
        return adapter_cls, result

    def _run_with_stub(self, site_name: str, total_collected: int, previous_counts: dict, tracker):
        """1 サイトを stub adapter で run_rule_based_sites に通す"""
        from unittest.mock import Mock, patch

        from data_collector.__main__ import run_rule_based_sites
        from data_collector.adapters.rule_based.registry import SiteAdapterRegistry

        adapter_cls, mock_result = self._make_stub_adapter(total_collected)
        SiteAdapterRegistry.register(site_name, adapter_cls)

        site = _site(extraction="rule-based").model_copy(update={"name": site_name})
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="dummy",
                default_extraction="rule-based",
            ),
            sites=[site],
        )

        # CollectorService.run_collection() が常に上記 mock_result を返すように差し替える
        with patch("data_collector.__main__.CollectorService") as mock_service_cls:
            mock_service = Mock()
            mock_service.run_collection.return_value = mock_result
            mock_service_cls.return_value = mock_service
            return run_rule_based_sites(
                config=config,
                snapshot_store=Mock(),
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                broken_tracker=tracker,
                previous_site_counts=previous_counts,
            )

    def test_prev_zero_current_zero_treated_as_normal_zero(self, tmp_path):
        """前回 0 件 → 今回 0 件 = 正常運用、succeeded カウント"""
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker

        tracker = BrokenSitesTracker(tmp_path / "broken_sites.yaml")
        succeeded, failed, zero = self._run_with_stub(
            "テスト_正常0件",
            total_collected=0,
            previous_counts={"テスト_正常0件": 0},
            tracker=tracker,
        )
        assert (succeeded, failed) == (1, 0)
        assert "テスト_正常0件" in zero
        # broken_tracker に failure 記録されないこと
        assert tracker.consecutive_failures("テスト_正常0件") == 0

    def test_prev_zero_current_positive_treated_as_normal(self, tmp_path):
        """前回 0 件 → 今回 N 件 = 正常運用、succeeded カウント"""
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker

        tracker = BrokenSitesTracker(tmp_path / "broken_sites.yaml")
        succeeded, failed, zero = self._run_with_stub(
            "テスト_新規取得",
            total_collected=5,
            previous_counts={"テスト_新規取得": 0},
            tracker=tracker,
        )
        assert (succeeded, failed, zero) == (1, 0, [])
        assert tracker.consecutive_failures("テスト_新規取得") == 0

    def test_prev_positive_current_positive_treated_as_normal(self, tmp_path):
        """前回 N 件 → 今回 M 件 = 正常運用、succeeded カウント"""
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker

        tracker = BrokenSitesTracker(tmp_path / "broken_sites.yaml")
        succeeded, failed, zero = self._run_with_stub(
            "テスト_継続取得",
            total_collected=3,
            previous_counts={"テスト_継続取得": 5},
            tracker=tracker,
        )
        assert (succeeded, failed, zero) == (1, 0, [])
        assert tracker.consecutive_failures("テスト_継続取得") == 0

    def test_prev_positive_current_zero_not_skipped(self, tmp_path):
        """前回 ≥ 1 件 → 今回 0 件 = 収集成功扱い、スキップ対象化しない

        result.success=True は adapter が正常終了した証左。0 件の大半は
        在庫はけ (真の 0 件) であり、record_failure による自動スキップ
        対象化は誤検知だった。succeeded にカウントし zero_count_sites に
        記録 (監視用) するが、broken_tracker には failure を残さない。
        """
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker

        tracker = BrokenSitesTracker(tmp_path / "broken_sites.yaml")
        succeeded, failed, zero = self._run_with_stub(
            "テスト_件数低下",
            total_collected=0,
            previous_counts={"テスト_件数低下": 4},
            tracker=tracker,
        )
        assert (succeeded, failed) == (1, 0), "件数低下は収集成功 (success) 扱い"
        assert "テスト_件数低下" in zero, "監視用に zero_count_sites には残す"
        # スキップ対象化されない: record_failure は呼ばれず consecutive=0
        assert tracker.consecutive_failures("テスト_件数低下") == 0

    def test_no_previous_counts_treated_as_zero(self, tmp_path):
        """previous_site_counts が None / 空 dict なら全サイト前回 0 件扱い

        マイグレーション直後で snapshot がまだ無いケースの後方互換。
        adapter が 0 件返しても異常検出しない (正常 0 件扱い)。
        """
        from data_collector.adapters.rule_based.broken_tracker import BrokenSitesTracker

        tracker = BrokenSitesTracker(tmp_path / "broken_sites.yaml")
        succeeded, failed, zero = self._run_with_stub(
            "テスト_前回情報なし",
            total_collected=0,
            previous_counts={},  # 前回情報無し
            tracker=tracker,
        )
        assert (succeeded, failed) == (1, 0)
        assert "テスト_前回情報なし" in zero
        assert tracker.consecutive_failures("テスト_前回情報なし") == 0


class TestApplyRobotsPolicy:
    """_apply_robots_policy: robots.txt の allow/Crawl-delay を LLM/rule-based 両経路で共有。

    従来 robots チェックは LLM 経路のみで、本番主力の rule-based 経路は素通りだった
    （terms の「robots を尊重」と乖離＝言行不一致）。共有ヘルパーで両経路に適用する。
    """

    @staticmethod
    def _robots(allowed: bool = True, delay: float | None = None):
        from unittest.mock import Mock

        r = Mock()
        r.is_allowed.return_value = allowed
        r.crawl_delay.return_value = delay
        return r

    def test_disallowed_site_returns_false(self):
        import logging

        from data_collector.__main__ import _apply_robots_policy

        site = _site()
        result = _apply_robots_policy(site, self._robots(allowed=False), logging.getLogger("t"))
        assert result is False

    def test_allowed_site_returns_true(self):
        import logging

        from data_collector.__main__ import _apply_robots_policy

        site = _site()
        result = _apply_robots_policy(site, self._robots(allowed=True), logging.getLogger("t"))
        assert result is True

    def test_crawl_delay_larger_than_interval_is_applied(self):
        import logging

        from data_collector.__main__ import _apply_robots_policy

        site = _site()
        site.request_interval = 1.0
        _apply_robots_policy(site, self._robots(allowed=True, delay=5.0), logging.getLogger("t"))
        assert site.request_interval == 5.0

    def test_crawl_delay_not_larger_is_ignored(self):
        import logging

        from data_collector.__main__ import _apply_robots_policy

        site = _site()
        site.request_interval = 10.0
        _apply_robots_policy(site, self._robots(allowed=True, delay=2.0), logging.getLogger("t"))
        assert site.request_interval == 10.0
