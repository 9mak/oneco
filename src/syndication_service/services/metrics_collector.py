"""Metrics collection service"""

from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

from src.syndication_service.models.metrics import MetricsSnapshot


class MetricsCollector:
    """フィード生成数、キャッシュヒット率、レスポンスタイムを記録"""

    def __init__(self):
        self.feed_generation_count: dict[str, int] = defaultdict(int)
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.response_times: list[float] = []

    def record_feed_generation(self, timestamp: datetime) -> None:
        """フィード生成をカウント"""
        hour_key = timestamp.strftime("%Y-%m-%d %H:00")
        self.feed_generation_count[hour_key] += 1

    def record_cache_hit(self) -> None:
        """キャッシュヒットを記録"""
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        """キャッシュミスを記録"""
        self.cache_misses += 1

    def record_response_time(self, duration_ms: float) -> None:
        """レスポンスタイムを記録"""
        self.response_times.append(duration_ms)
        # 直近1000件のみ保持
        if len(self.response_times) > 1000:
            self.response_times.pop(0)

    def get_metrics_snapshot(self) -> MetricsSnapshot:
        """現在のメトリクスを取得"""
        now = datetime.now()
        one_hour_ago_key = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:00")
        current_hour_key = now.strftime("%Y-%m-%d %H:00")

        feed_count_1h = self.feed_generation_count.get(
            one_hour_ago_key, 0
        ) + self.feed_generation_count.get(current_hour_key, 0)

        total_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0.0

        p50 = float(np.percentile(self.response_times, 50)) if self.response_times else 0.0
        p95 = float(np.percentile(self.response_times, 95)) if self.response_times else 0.0
        p99 = float(np.percentile(self.response_times, 99)) if self.response_times else 0.0

        return MetricsSnapshot(
            feed_generation_count_1h=feed_count_1h,
            cache_hit_rate=cache_hit_rate,
            response_time_p50=p50,
            response_time_p95=p95,
            response_time_p99=p99,
        )
