"""サイト別件数の記録が adapter の実収集件数に基づくことを検証する

背景 (2026-08-03):
    `site_baselines.yaml` の件数は `snapshot_store.load_counts_by_site_url_prefix`
    で集計していた。これは「動物の source_url が list_url で前方一致する」
    前提だが、1 頭ごとに独立した詳細ページ URL を持つサイトでは成立しない。

        list_url  : https://animal-net.pref.nagasaki.jp/jyouto
        source_url: https://animal-net.pref.nagasaki.jp/animal/no-19847/

    結果、公開 729 頭のうち 317 頭 (43%) が計測から漏れ、収集は成功して
    いるのに baseline 上は永久に 0 件・consecutive_zero_runs が加算され
    続けていた。さらに `previous_site_counts` も同じ集計を使うため
    `is_zero_count_drop` が常に False となり、当該サイトでは件数低下異常が
    検知されない状態だった。

    正確な件数は adapter が `result.total_collected` として保持しており、
    ログにも出力されている。URL から逆算せずこの値を記録する。
"""

from __future__ import annotations

from unittest.mock import Mock, patch

from data_collector.llm.config import ExtractionConfig, SiteConfig, SitesConfig


def _site(
    name: str = "テストサイト",
    list_url: str = "https://example.com/list",
    extraction: str = "rule-based",
) -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="東京都",
        prefecture_code="13",
        list_url=list_url,
        category="adoption",
        extraction=extraction,
    )


def _config(extraction: str, sites: list[SiteConfig]) -> SitesConfig:
    return SitesConfig(
        extraction=ExtractionConfig(
            default_provider="groq",
            default_model="dummy",
            default_extraction=extraction,
        ),
        sites=sites,
    )


class TestSucceededSiteCountsContract:
    """run_llm_sites / run_rule_based_sites は件数付き dict を返す

    従来の 4 要素目 `succeeded_site_names: list[str]` を
    `succeeded_site_counts: dict[str, int]` に置き換える。
    キー集合は従来の名前リストと等価なので情報は失われない。
    """

    def test_run_llm_sites_returns_empty_dict_when_no_llm_sites(self):
        from data_collector.__main__ import run_llm_sites

        config = _config("rule-based", [_site(extraction="rule-based")])
        result = run_llm_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
        )
        assert result == (0, 0, [], {})

    def test_run_rule_based_sites_returns_empty_dict_when_no_rule_sites(self):
        from data_collector.__main__ import run_rule_based_sites

        config = _config("llm", [_site(extraction="llm")])
        result = run_rule_based_sites(
            config=config,
            snapshot_store=Mock(),
            diff_detector=Mock(),
            output_writer=Mock(),
            notification_client=Mock(),
            db_connection=None,
            logger=Mock(),
        )
        assert result == (0, 0, [], {})


class TestCountsComeFromAdapterNotUrlPrefix:
    """記録される件数は adapter の total_collected であること

    詳細ページ URL が list_url と無関係なサイト (長崎犬猫ネット型) でも
    正しい件数が返ることを固定する。これが 43% 取りこぼしの回帰テスト。
    """

    def test_rule_based_records_total_collected_for_independent_detail_urls(self):
        from data_collector.__main__ import run_rule_based_sites

        site = _site(
            name="長崎犬猫ネット（保健所収容）",
            list_url="https://animal-net.pref.nagasaki.jp/syuuyou",
        )
        config = _config("rule-based", [site])

        result_obj = Mock(
            success=True, total_collected=12, new_count=12, updated_count=0, errors=[]
        )

        # snapshot 側の prefix 集計は 0 を返す (URL が list_url で始まらないため)。
        # それでも記録は 12 件でなければならない。
        snapshot_store = Mock()
        snapshot_store.load_counts_by_site_url_prefix.return_value = {site.name: 0}

        with (
            patch("data_collector.__main__.SiteAdapterRegistry") as registry,
            patch("data_collector.__main__.CollectorService") as service_cls,
            patch("data_collector.__main__._apply_robots_policy", return_value=True),
        ):
            registry.get.return_value = Mock()
            service_cls.return_value.run_collection.return_value = result_obj

            _, _, _, counts = run_rule_based_sites(
                config=config,
                snapshot_store=snapshot_store,
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                previous_site_counts={site.name: 0},
            )

        assert counts == {"長崎犬猫ネット（保健所収容）": 12}

    def test_zero_collected_site_is_recorded_as_zero(self):
        """0 件で成功したサイトは 0 として記録される (未実行とは区別する)"""
        from data_collector.__main__ import run_rule_based_sites

        site = _site(name="真にゼロのサイト", list_url="https://example.com/empty")
        config = _config("rule-based", [site])
        result_obj = Mock(success=True, total_collected=0, new_count=0, updated_count=0, errors=[])

        with (
            patch("data_collector.__main__.SiteAdapterRegistry") as registry,
            patch("data_collector.__main__.CollectorService") as service_cls,
            patch("data_collector.__main__._apply_robots_policy", return_value=True),
        ):
            registry.get.return_value = Mock()
            service_cls.return_value.run_collection.return_value = result_obj

            _, _, zero_sites, counts = run_rule_based_sites(
                config=config,
                snapshot_store=Mock(),
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                previous_site_counts={site.name: 0},
            )

        assert counts == {"真にゼロのサイト": 0}
        assert zero_sites == ["真にゼロのサイト"]

    def test_failed_site_is_not_recorded(self):
        """失敗サイトは dict に入らない (baseline を 0 で汚染しない)"""
        from data_collector.__main__ import run_rule_based_sites

        site = _site(name="失敗サイト", list_url="https://example.com/broken")
        config = _config("rule-based", [site])
        result_obj = Mock(success=False, total_collected=0, errors=["boom"])

        with (
            patch("data_collector.__main__.SiteAdapterRegistry") as registry,
            patch("data_collector.__main__.CollectorService") as service_cls,
            patch("data_collector.__main__._apply_robots_policy", return_value=True),
        ):
            registry.get.return_value = Mock()
            service_cls.return_value.run_collection.return_value = result_obj

            _, failed, _, counts = run_rule_based_sites(
                config=config,
                snapshot_store=Mock(),
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                previous_site_counts={site.name: 0},
            )

        assert counts == {}
        assert failed == 1


class TestCollectedUrlsWiring:
    """収集した source_url が品質メトリクスまで配線されていること

    このリポジトリで実際に起きた事故は「集計側の前提と収集側の実態が
    食い違っているのに、どちらの単体テストも通るため誰も気付かない」
    という形だった。同じ轍を踏まないよう、
    `CollectionResult.source_urls` → `collected_urls_by_site` →
    `group_animals_by_site` の経路を通しで固定する。
    """

    def _run_rule_based(self, site, result_obj, collected: dict[str, list[str]]):
        from data_collector.__main__ import run_rule_based_sites

        config = _config("rule-based", [site])
        with (
            patch("data_collector.__main__.SiteAdapterRegistry") as registry,
            patch("data_collector.__main__.CollectorService") as service_cls,
            patch("data_collector.__main__._apply_robots_policy", return_value=True),
        ):
            registry.get.return_value = Mock()
            service_cls.return_value.run_collection.return_value = result_obj
            return run_rule_based_sites(
                config=config,
                snapshot_store=Mock(),
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                previous_site_counts={site.name: 0},
                collected_urls_by_site=collected,
            )

    def test_rule_based_fills_collected_urls(self):
        """run_rule_based_sites が collected_urls_by_site を埋める"""
        site = _site(
            name="長崎犬猫ネット（保健所収容）",
            list_url="https://animal-net.pref.nagasaki.jp/syuuyou",
        )
        urls = [
            "https://animal-net.pref.nagasaki.jp/animal/no-19847/",
            "https://animal-net.pref.nagasaki.jp/animal/no-19823/",
        ]
        result_obj = Mock(
            success=True,
            total_collected=2,
            new_count=2,
            updated_count=0,
            errors=[],
            source_urls=urls,
        )
        collected: dict[str, list[str]] = {}
        self._run_rule_based(site, result_obj, collected)

        assert collected == {"長崎犬猫ネット（保健所収容）": urls}

    def test_llm_path_fills_collected_urls(self):
        """run_llm_sites も同じ dict を埋める"""
        from data_collector.__main__ import run_llm_sites

        site = _site(
            name="LLMサイト",
            list_url="https://llm.example.com/list",
            extraction="llm",
        )
        config = _config("llm", [site])
        urls = ["https://llm.example.com/detail/1"]
        result_obj = Mock(
            success=True,
            total_collected=1,
            new_count=1,
            updated_count=0,
            errors=[],
            source_urls=urls,
        )
        collected: dict[str, list[str]] = {}

        with (
            patch("data_collector.__main__.CollectorService") as service_cls,
            patch("data_collector.__main__._apply_robots_policy", return_value=True),
            patch("data_collector.__main__.create_provider"),
            patch("data_collector.__main__.LlmAdapter"),
            patch("data_collector.__main__.HtmlPreprocessor"),
        ):
            service_cls.return_value.run_collection.return_value = result_obj
            run_llm_sites(
                config=config,
                snapshot_store=Mock(),
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                collected_urls_by_site=collected,
            )

        assert collected == {"LLMサイト": urls}

    def test_collected_urls_feed_quality_grouping(self):
        """埋めた dict がそのまま group_animals_by_site で機能する

        収集側が返す source_url の形 (list_url と無関係な detail URL) のまま
        品質メトリクス側でグルーピングできることを、両者を繋いで確認する。
        """
        from datetime import date

        from data_collector.domain.models import AnimalData
        from data_collector.domain.quality_metrics import group_animals_by_site

        site = _site(
            name="長崎犬猫ネット（保健所収容）",
            list_url="https://animal-net.pref.nagasaki.jp/syuuyou",
        )
        urls = [
            "https://animal-net.pref.nagasaki.jp/animal/no-19847/",
            "https://animal-net.pref.nagasaki.jp/animal/no-19823/",
        ]
        result_obj = Mock(
            success=True,
            total_collected=2,
            new_count=2,
            updated_count=0,
            errors=[],
            source_urls=urls,
        )
        collected: dict[str, list[str]] = {}
        self._run_rule_based(site, result_obj, collected)

        animals = [
            AnimalData(
                species="犬",
                shelter_date=date(2026, 7, 21),
                location="長崎市",
                sex="男の子",
                age_months=24,
                color="茶",
                size="中型",
                phone="095-000-0000",
                image_urls=["https://animal-net.pref.nagasaki.jp/img/1.jpg"],
                source_url=u,
                category="sheltered",
            )
            for u in urls
        ]
        groups = group_animals_by_site(animals, collected)

        assert len(groups["長崎犬猫ネット（保健所収容）"]) == 2

    def test_none_collected_urls_is_tolerated(self):
        """collected_urls_by_site 未指定でも収集は動く (best-effort)"""
        site = _site(name="サイト", list_url="https://example.com/list")
        result_obj = Mock(
            success=True,
            total_collected=1,
            new_count=1,
            updated_count=0,
            errors=[],
            source_urls=["https://example.com/detail/1"],
        )
        from data_collector.__main__ import run_rule_based_sites

        config = _config("rule-based", [site])
        with (
            patch("data_collector.__main__.SiteAdapterRegistry") as registry,
            patch("data_collector.__main__.CollectorService") as service_cls,
            patch("data_collector.__main__._apply_robots_policy", return_value=True),
        ):
            registry.get.return_value = Mock()
            service_cls.return_value.run_collection.return_value = result_obj
            _, _, _, counts = run_rule_based_sites(
                config=config,
                snapshot_store=Mock(),
                diff_detector=Mock(),
                output_writer=Mock(),
                notification_client=Mock(),
                db_connection=None,
                logger=Mock(),
                previous_site_counts={site.name: 0},
            )

        assert counts == {"サイト": 1}
