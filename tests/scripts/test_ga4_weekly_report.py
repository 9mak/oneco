"""scripts/ga4_weekly_report.py のテスト。

GA4 API は一切呼ばない。fetch_metrics/render_* の純粋ロジックのみ検証する。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ga4_weekly_report as ga4  # noqa: E402


def _metric_row(*values: str) -> SimpleNamespace:
    return SimpleNamespace(metric_values=[SimpleNamespace(value=v) for v in values])


def _dim_metric_row(dim: str, metric: str) -> SimpleNamespace:
    return SimpleNamespace(
        dimension_values=[SimpleNamespace(value=dim)],
        metric_values=[SimpleNamespace(value=metric)],
    )


class FakeGA4Client:
    """GA4Client と同じ run_report インターフェースを持つスタブ。

    呼び出し順を dimensions の有無で判別し、決め打ちの応答を返す。
    """

    def __init__(
        self,
        total_users: str,
        events: dict[str, str],
        animal_views: list[tuple[str, str]],
        top_pages: list[tuple[str, str]],
    ):
        self._total_users = total_users
        self._events = events
        self._animal_views = animal_views
        self._top_pages = top_pages
        self.calls: list[dict] = []

    def run_report(self, **kwargs):
        self.calls.append(kwargs)
        dims = kwargs.get("dimensions") or []
        dim_names = [d.name for d in dims]

        if not dim_names:
            # totalUsers
            return SimpleNamespace(rows=[_metric_row(self._total_users)])

        if dim_names == ["eventName"]:
            return SimpleNamespace(
                rows=[_dim_metric_row(name, count) for name, count in self._events.items()]
            )

        # pagePath dimension: either animal-filtered or top-pages (order_bys present)
        if "order_bys" in kwargs:
            return SimpleNamespace(
                rows=[_dim_metric_row(path, views) for path, views in self._top_pages]
            )
        return SimpleNamespace(
            rows=[_dim_metric_row(path, views) for path, views in self._animal_views]
        )


class TestComputePeriods:
    def test_current_is_last_7_days_ending_yesterday(self):
        current, _previous = ga4.compute_periods(date(2026, 9, 8))
        assert current.start == date(2026, 9, 1)
        assert current.end == date(2026, 9, 7)

    def test_previous_is_the_7_days_before_current(self):
        _current, previous = ga4.compute_periods(date(2026, 9, 8))
        assert previous.start == date(2026, 8, 25)
        assert previous.end == date(2026, 8, 31)

    def test_periods_are_contiguous_no_gap_no_overlap(self):
        current, previous = ga4.compute_periods(date(2026, 9, 8))
        assert previous.end + ga4.timedelta(days=1) == current.start


class TestDeltaAndPct:
    def test_delta_positive(self):
        assert ga4.delta_str(10, 7) == "+3"

    def test_delta_negative(self):
        assert ga4.delta_str(5, 8) == "-3"

    def test_delta_zero(self):
        assert ga4.delta_str(5, 5) == "±0"

    def test_pct_positive(self):
        assert ga4.pct_str(110, 100) == "+10.0%"

    def test_pct_from_zero_previous_nonzero_current(self):
        assert ga4.pct_str(5, 0) == "+∞%"

    def test_pct_from_zero_previous_zero_current(self):
        assert ga4.pct_str(0, 0) == "n/a"


class TestFetchMetrics:
    def test_fetch_metrics_aggregates_expected_shape(self):
        client = FakeGA4Client(
            total_users="42",
            events={"page_view": "100", "external_link_click": "5", "click": "20"},
            animal_views=[("/animals/1", "10"), ("/animals/2", "7")],
            top_pages=[("/", "50"), ("/animals/1", "10")],
        )
        period = ga4.Period(start=date(2026, 9, 1), end=date(2026, 9, 7))
        result = ga4.fetch_metrics(client, period)  # type: ignore[arg-type]

        assert result["total_users"] == 42
        assert result["events"] == {"page_view": 100, "external_link_click": 5, "click": 20}
        assert result["animal_page_views"] == 17
        assert result["top_pages"] == [("/", 50), ("/animals/1", 10)]

    def test_fetch_metrics_missing_tracked_event_defaults_to_zero(self):
        client = FakeGA4Client(
            total_users="0",
            events={"page_view": "10"},
            animal_views=[],
            top_pages=[],
        )
        period = ga4.Period(start=date(2026, 9, 1), end=date(2026, 9, 7))
        result = ga4.fetch_metrics(client, period)  # type: ignore[arg-type]

        assert result["events"]["external_link_click"] == 0
        assert result["events"]["click"] == 0
        assert result["animal_page_views"] == 0
        assert result["top_pages"] == []


class TestRenderMarkdown:
    def test_render_markdown_includes_summary_table_and_top_pages(self):
        current = ga4.Period(start=date(2026, 9, 1), end=date(2026, 9, 7))
        previous = ga4.Period(start=date(2026, 8, 25), end=date(2026, 8, 31))
        cur = {
            "total_users": 100,
            "events": {"page_view": 300, "external_link_click": 10, "click": 50},
            "animal_page_views": 60,
            "top_pages": [("/animals/1", 20)],
        }
        prev = {
            "total_users": 80,
            "events": {"page_view": 250, "external_link_click": 8, "click": 40},
            "animal_page_views": 45,
            "top_pages": [],
        }
        md = ga4.render_markdown(current, previous, cur, prev)

        assert "GA4 週次レポート" in md
        assert "ユーザー数" in md
        assert "動物詳細ページ閲覧数" in md
        assert "external_link_click" in md
        assert "/animals/1" in md
        assert "+20" in md  # total_users delta

    def test_render_markdown_handles_empty_top_pages(self):
        current = ga4.Period(start=date(2026, 9, 1), end=date(2026, 9, 7))
        previous = ga4.Period(start=date(2026, 8, 25), end=date(2026, 8, 31))
        empty = {"total_users": 0, "events": {}, "animal_page_views": 0, "top_pages": []}
        md = ga4.render_markdown(current, previous, empty, empty)
        assert "データなし" in md


class TestRenderDiscordMessage:
    def test_discord_message_contains_three_metrics_with_deltas(self):
        current = ga4.Period(start=date(2026, 9, 1), end=date(2026, 9, 7))
        cur = {
            "total_users": 100,
            "events": {"external_link_click": 10},
            "animal_page_views": 60,
        }
        prev = {
            "total_users": 80,
            "events": {"external_link_click": 8},
            "animal_page_views": 45,
        }
        msg = ga4.render_discord_message(current, cur, prev)

        assert "GA4 週次" in msg
        assert "ユーザー数: 100" in msg
        assert "動物詳細PV: 60" in msg
        assert "external_link_click: 10" in msg
        assert "+20" in msg

    def test_discord_message_within_discord_content_limit(self):
        current = ga4.Period(start=date(2026, 9, 1), end=date(2026, 9, 7))
        cur = {"total_users": 100, "events": {"external_link_click": 10}, "animal_page_views": 60}
        prev = {"total_users": 80, "events": {"external_link_click": 8}, "animal_page_views": 45}
        msg = ga4.render_discord_message(current, cur, prev)
        assert len(msg) < 2000
