"""digest.py: 前日新着の集計 TDD (T160)"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from data_collector.domain.models import AnimalData
from syndication_service.sns_publisher.digest import collect_daily_digest

_JST = ZoneInfo("Asia/Tokyo")


def _animal(*, species: str = "犬", prefecture: str | None = "高知県") -> AnimalData:
    return AnimalData(
        species=species,
        shelter_date=date(2026, 1, 1),
        location=prefecture or "不明",
        prefecture=prefecture,
        source_url="https://example.jp/animals/1",
        category="adoption",
    )


def _repo(animals: list[AnimalData]) -> Any:
    repo = AsyncMock()
    repo.list_animals_first_seen_between.return_value = animals
    return repo


@pytest.mark.asyncio
class TestCollectDailyDigest:
    async def test_zero_animals_returns_none(self):
        repo = _repo([])
        result = await collect_daily_digest(repo, target_date_jst=date(2026, 9, 10))
        assert result is None

    async def test_counts_total_and_species(self):
        repo = _repo(
            [
                _animal(species="犬"),
                _animal(species="犬"),
                _animal(species="猫"),
                _animal(species="その他"),
            ]
        )
        result = await collect_daily_digest(repo, target_date_jst=date(2026, 9, 10))
        assert result is not None
        assert result.total == 4
        assert result.dog == 2
        assert result.cat == 1
        assert result.other == 1

    async def test_prefecture_counts_sorted_descending(self):
        repo = _repo(
            [
                _animal(prefecture="東京都"),
                _animal(prefecture="東京都"),
                _animal(prefecture="大阪府"),
                _animal(prefecture="高知県"),
                _animal(prefecture="高知県"),
                _animal(prefecture="高知県"),
            ]
        )
        result = await collect_daily_digest(repo, target_date_jst=date(2026, 9, 10))
        assert result is not None
        assert result.prefecture_counts == [
            ("高知県", 3),
            ("東京都", 2),
            ("大阪府", 1),
        ]

    async def test_none_prefecture_becomes_unknown_at_tail(self):
        repo = _repo(
            [
                _animal(prefecture=None),
                _animal(prefecture="高知県"),
                _animal(prefecture="高知県"),
            ]
        )
        result = await collect_daily_digest(repo, target_date_jst=date(2026, 9, 10))
        assert result is not None
        # 件数だけなら 不明(1) が 高知県(2) より少ないので自然に末尾だが、
        # 同数でも不明は必ず末尾に回ることを別テストで検証する
        assert result.prefecture_counts[-1] == ("不明", 1)

    async def test_none_prefecture_tail_even_when_tied(self):
        """不明が他都道府県と同数でも必ず末尾に回る"""
        repo = _repo(
            [
                _animal(prefecture=None),
                _animal(prefecture="高知県"),
            ]
        )
        result = await collect_daily_digest(repo, target_date_jst=date(2026, 9, 10))
        assert result is not None
        assert result.prefecture_counts == [("高知県", 1), ("不明", 1)]

    async def test_queries_jst_day_boundary_in_utc(self):
        """JST 2026-09-10 00:00〜23:59:59 の範囲が UTC 2026-09-09 15:00〜2026-09-10 15:00 になる"""
        repo = _repo([_animal()])
        await collect_daily_digest(repo, target_date_jst=date(2026, 9, 10))

        call_kwargs = repo.list_animals_first_seen_between.call_args.kwargs
        start = call_kwargs["start"]
        end = call_kwargs["end"]

        assert start == datetime(2026, 9, 9, 15, 0, tzinfo=UTC)
        assert end == datetime(2026, 9, 10, 15, 0, tzinfo=UTC)
