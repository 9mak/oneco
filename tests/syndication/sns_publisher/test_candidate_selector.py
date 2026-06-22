"""投稿候補抽出 TDD

design.md 5.2 のステップ 1: DB から status=available, image_urls あり,
shelter_date 降順 top N から 1 件選ぶ。投稿履歴 (already_posted_ids) は除外。
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest

from data_collector.domain.models import AnimalData, AnimalStatus
from syndication_service.sns_publisher.candidate_selector import select_candidate


def _animal(
    *,
    species: str = "犬",
    image_urls: list[str] | None = None,
    shelter_date: date = date(2026, 6, 1),
    source_url: str = "https://example.jp/animals/1",
    status: AnimalStatus | None = AnimalStatus.SHELTERED,
) -> AnimalData:
    return AnimalData(
        species=species,
        shelter_date=shelter_date,
        location="高知県",
        source_url=source_url,
        category="adoption",
        image_urls=image_urls if image_urls is not None else ["https://example.jp/img/1.jpg"],
        status=status,
    )


def _repo(animals: list[AnimalData]) -> Any:
    """list_animals が指定の動物群を返す mock repository。"""
    repo = AsyncMock()
    repo.list_animals.return_value = (animals, len(animals))
    return repo


@pytest.mark.asyncio
class TestSelectCandidate:
    async def test_returns_first_with_image(self):
        a = _animal(source_url="https://example.jp/animals/1")
        b = _animal(source_url="https://example.jp/animals/2")
        repo = _repo([a, b])
        chosen = await select_candidate(repo, already_posted_urls=set())
        assert chosen == a

    async def test_skips_without_image(self):
        no_img = _animal(image_urls=[], source_url="https://example.jp/animals/1")
        with_img = _animal(source_url="https://example.jp/animals/2")
        repo = _repo([no_img, with_img])
        chosen = await select_candidate(repo, already_posted_urls=set())
        assert chosen == with_img

    async def test_skips_already_posted(self):
        first = _animal(source_url="https://example.jp/animals/1")
        second = _animal(source_url="https://example.jp/animals/2")
        repo = _repo([first, second])
        chosen = await select_candidate(repo, already_posted_urls={"https://example.jp/animals/1"})
        assert chosen == second

    async def test_returns_none_when_all_filtered(self):
        no_img = _animal(image_urls=[], source_url="https://example.jp/animals/1")
        already = _animal(source_url="https://example.jp/animals/2")
        repo = _repo([no_img, already])
        chosen = await select_candidate(repo, already_posted_urls={"https://example.jp/animals/2"})
        assert chosen is None

    async def test_returns_none_when_empty(self):
        repo = _repo([])
        chosen = await select_candidate(repo, already_posted_urls=set())
        assert chosen is None

    async def test_calls_repo_with_correct_filters(self):
        """status=SHELTERED, include_non_public=False, descending shelter_date を要求"""
        repo = _repo([_animal()])
        await select_candidate(repo, already_posted_urls=set())
        kwargs = repo.list_animals.call_args.kwargs
        assert kwargs.get("status") == AnimalStatus.SHELTERED
        # public-only (deceased excluded)
        assert kwargs.get("include_non_public", False) is False
        # 多めに取って posted/no-image をフィルタした後に 1 件選ぶ
        assert kwargs.get("limit", 0) >= 20

    async def test_oldest_first_falls_through(self):
        """list_animals は shelter_date.desc() で返してくれる前提なので、最初の有効な動物を選ぶ。"""
        new = _animal(shelter_date=date(2026, 6, 10), source_url="https://example.jp/animals/new")
        old = _animal(shelter_date=date(2026, 1, 1), source_url="https://example.jp/animals/old")
        repo = _repo([new, old])  # repo が新しい順で返す前提
        chosen = await select_candidate(repo, already_posted_urls=set())
        assert chosen == new
