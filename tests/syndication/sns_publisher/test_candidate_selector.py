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


@pytest.mark.asyncio
class TestIdentityDedup:
    """個体照合キーによる再投稿防止 (T058)

    source_url の形式変更 (T026 山梨の実例) で URL 照合をすり抜けても、
    個体の特徴 (画像名 / 種別+性別+毛色+初出日) で「投稿済み」を判定する。
    """

    async def test_skips_when_image_key_matches(self):
        posted_same_cat = _animal(
            source_url="https://example.jp/new-format/33833.html",
            image_urls=["https://example.jp/uploads/33833no2.jpg"],
        )
        other = _animal(
            source_url="https://example.jp/animals/9",
            image_urls=["https://example.jp/uploads/other.jpg"],
        )
        repo = _repo([posted_same_cat, other])
        chosen = await select_candidate(
            repo,
            already_posted_urls=set(),
            already_posted_identity_keys={"img:33833no2.jpg"},
        )
        assert chosen == other

    async def test_skips_when_profile_key_matches(self):
        cat = AnimalData(
            species="猫",
            sex="女の子",
            color="三毛（黒茶白）",
            shelter_date=date(2026, 6, 26),
            location="山梨県",
            source_url="https://example.jp/new-format/1.html",
            category="adoption",
            image_urls=["https://example.jp/uploads/noimage01.jpg"],
            status=AnimalStatus.SHELTERED,
        )
        repo = _repo([cat])
        chosen = await select_candidate(
            repo,
            already_posted_urls=set(),
            already_posted_identity_keys={"prof:猫|女の子|三毛（黒茶白）|2026-06-26"},
        )
        assert chosen is None

    async def test_placeholder_image_does_not_match_other_animal(self):
        """プレースホルダ画像 (noimage) は img キーにならず、別個体を誤ブロックしない"""
        cat = AnimalData(
            species="猫",
            sex="男の子",
            color="黒",
            shelter_date=date(2026, 7, 1),
            location="山梨県",
            source_url="https://example.jp/new-format/2.html",
            category="adoption",
            image_urls=["https://example.jp/uploads/noimage01.jpg"],
            status=AnimalStatus.SHELTERED,
        )
        repo = _repo([cat])
        chosen = await select_candidate(
            repo,
            already_posted_urls=set(),
            already_posted_identity_keys={"img:noimage01.jpg"},
        )
        assert chosen == cat

    async def test_no_keys_keeps_existing_behavior(self):
        a = _animal(source_url="https://example.jp/animals/1")
        repo = _repo([a])
        chosen = await select_candidate(repo, already_posted_urls=set())
        assert chosen == a
