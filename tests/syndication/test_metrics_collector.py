"""Tests for MetricsCollector service"""

from datetime import datetime, timedelta

from src.syndication_service.services.metrics_collector import MetricsCollector


class TestMetricsCollector:
    """Test cases for MetricsCollector"""

    def test_record_feed_generation(self):
        """フィード生成数を記録できる"""
        collector = MetricsCollector()
        now = datetime.now()

        collector.record_feed_generation(now)
        collector.record_feed_generation(now)

        snapshot = collector.get_metrics_snapshot()
        assert snapshot.feed_generation_count_1h >= 2

    def test_record_cache_hit(self):
        """キャッシュヒットを記録できる"""
        collector = MetricsCollector()

        collector.record_cache_hit()
        collector.record_cache_hit()

        collector.get_metrics_snapshot()
        assert collector.cache_hits == 2

    def test_record_cache_miss(self):
        """キャッシュミスを記録できる"""
        collector = MetricsCollector()

        collector.record_cache_miss()

        collector.get_metrics_snapshot()
        assert collector.cache_misses == 1

    def test_calculate_cache_hit_rate(self):
        """キャッシュヒット率を正しく計算する"""
        collector = MetricsCollector()

        collector.record_cache_hit()
        collector.record_cache_hit()
        collector.record_cache_hit()
        collector.record_cache_miss()

        snapshot = collector.get_metrics_snapshot()
        # 3 hits / 4 total = 0.75
        assert snapshot.cache_hit_rate == 0.75

    def test_calculate_cache_hit_rate_zero_requests(self):
        """リクエストが0件の場合、ヒット率は0"""
        collector = MetricsCollector()

        snapshot = collector.get_metrics_snapshot()
        assert snapshot.cache_hit_rate == 0.0

    def test_record_response_time(self):
        """レスポンスタイムを記録できる"""
        collector = MetricsCollector()

        collector.record_response_time(50.0)
        collector.record_response_time(100.0)
        collector.record_response_time(150.0)

        snapshot = collector.get_metrics_snapshot()
        assert snapshot.response_time_p50 == 100.0
        assert snapshot.response_time_p95 >= 100.0
        assert snapshot.response_time_p99 >= 100.0

    def test_response_time_limit_to_1000(self):
        """レスポンスタイムは最新1000件のみ保持"""
        collector = MetricsCollector()

        for i in range(1200):
            collector.record_response_time(float(i))

        assert len(collector.response_times) == 1000

    def test_feed_generation_count_1h(self):
        """1時間以内のフィード生成数を計算"""
        collector = MetricsCollector()
        now = datetime.now()
        two_hours_ago = now - timedelta(hours=2)

        # 2時間前の記録は含まれない
        collector.record_feed_generation(two_hours_ago)
        # 現在時刻の記録は含まれる
        collector.record_feed_generation(now)
        collector.record_feed_generation(now)

        snapshot = collector.get_metrics_snapshot()
        assert snapshot.feed_generation_count_1h >= 2

    def test_metrics_snapshot_structure(self):
        """メトリクススナップショットが正しい構造を持つ"""
        collector = MetricsCollector()
        collector.record_feed_generation(datetime.now())
        collector.record_cache_hit()
        collector.record_response_time(50.0)

        snapshot = collector.get_metrics_snapshot()

        assert hasattr(snapshot, "feed_generation_count_1h")
        assert hasattr(snapshot, "cache_hit_rate")
        assert hasattr(snapshot, "response_time_p50")
        assert hasattr(snapshot, "response_time_p95")
        assert hasattr(snapshot, "response_time_p99")
