"""SNS 投稿候補抽出

design.md 5.2 step 1: DB から status=available, image_urls あり,
shelter_date 降順 top N の中から、未投稿の 1 件を選ぶ。

投稿履歴の永続化は別レイヤ (post_log) で担当。ここは pure な selection。
"""

from __future__ import annotations

from typing import Protocol

from data_collector.domain.models import AnimalData, AnimalStatus

# repo から多めに取ってフィルタを通す。post_log と no-image が混ざるので余裕を持つ。
_CANDIDATE_POOL = 100


class _ListAnimalsRepo(Protocol):
    async def list_animals(
        self,
        *,
        status: AnimalStatus | None = ...,
        include_non_public: bool = ...,
        limit: int = ...,
        offset: int = ...,
        **kwargs: object,
    ) -> tuple[list[AnimalData], int]: ...


async def select_candidate(
    repo: _ListAnimalsRepo,
    *,
    already_posted_urls: set[str],
) -> AnimalData | None:
    """投稿可能な動物を 1 件返す。なければ None。

    フィルタ:
      - status=SHELTERED + 公開可 (deceased 除外)
      - image_urls が 1 件以上ある
      - source_url が already_posted_urls に含まれていない

    repo は shelter_date.desc() でソート済みを返す前提 (AnimalRepository.list_animals)。
    """
    animals, _ = await repo.list_animals(
        status=AnimalStatus.SHELTERED,
        include_non_public=False,
        limit=_CANDIDATE_POOL,
        offset=0,
    )
    for a in animals:
        if not a.image_urls:
            continue
        if str(a.source_url) in already_posted_urls:
            continue
        return a
    return None
