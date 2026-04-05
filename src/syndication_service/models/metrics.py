"""Data models for metrics"""

from pydantic import BaseModel


class MetricsSnapshot(BaseModel):
    """メトリクススナップショット"""

    feed_generation_count_1h: int
    cache_hit_rate: float
    response_time_p50: float
    response_time_p95: float
    response_time_p99: float
