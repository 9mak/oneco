"""SNS 日次まとめの集計 (T151 設計 / T160)

前日 (JST 00:00〜23:59) に first_seen_at が入り、status が公開中 (sheltered)
の個体を集計する。shelter_date は使わない (T151 設計「なぜ現行を捨てるか」参照)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from data_collector.domain.models import AnimalData

_JST = ZoneInfo("Asia/Tokyo")

# 集計に不明な都道府県として扱うプレースホルダ (文面組み立て側とも共有する)
UNKNOWN_PREFECTURE = "不明"


class _FirstSeenRepo(Protocol):
    async def list_animals_first_seen_between(
        self, *, start: datetime, end: datetime
    ) -> list[AnimalData]: ...


@dataclass(frozen=True)
class DigestStats:
    """前日新着の集計結果。

    Attributes:
        target_date: 集計対象日 (JST の日付)
        total: 総数
        dog: 犬の頭数
        cat: 猫の頭数
        other: その他の頭数
        prefecture_counts: (都道府県名, 件数) の降順リスト。
            都道府県不明 (None) の個体は "不明" として末尾に集約される。
            同数の場合は先に出現した都道府県を優先する安定ソート。
    """

    target_date: date
    total: int
    dog: int
    cat: int
    other: int
    prefecture_counts: list[tuple[str, int]] = field(default_factory=list)


def _jst_day_bounds_utc(target_date_jst: date) -> tuple[datetime, datetime]:
    """JST の対象日 [00:00, 24:00) を UTC の datetime 範囲に変換する。"""
    start_jst = datetime.combine(target_date_jst, datetime.min.time(), tzinfo=_JST)
    end_jst = start_jst + timedelta(days=1)
    return start_jst.astimezone(ZoneInfo("UTC")), end_jst.astimezone(ZoneInfo("UTC"))


def _species_bucket(species: str) -> str:
    if species == "犬":
        return "dog"
    if species == "猫":
        return "cat"
    return "other"


async def collect_daily_digest(
    repo: _FirstSeenRepo,
    *,
    target_date_jst: date,
) -> DigestStats | None:
    """target_date_jst (JST) の新着を集計する。0 件なら None を返す。

    Args:
        repo: first_seen_at 範囲検索を提供する repository
        target_date_jst: 集計対象日 (JST の暦日)

    Returns:
        DigestStats | None: 0 件の日は None (投稿スキップ)
    """
    start_utc, end_utc = _jst_day_bounds_utc(target_date_jst)
    animals = await repo.list_animals_first_seen_between(start=start_utc, end=end_utc)

    if not animals:
        return None

    counts = {"dog": 0, "cat": 0, "other": 0}
    pref_counts: dict[str, int] = {}

    for animal in animals:
        counts[_species_bucket(animal.species)] += 1
        pref = animal.prefecture or UNKNOWN_PREFECTURE
        pref_counts[pref] = pref_counts.get(pref, 0) + 1

    # 件数降順。同数は初出順を保つ安定ソート。"不明" は常に末尾へ回す
    # (設計書: 「都道府県が None の個体は不明として末尾に回す」)。
    known_prefs = [(p, n) for p, n in pref_counts.items() if p != UNKNOWN_PREFECTURE]
    known_prefs.sort(key=lambda item: -item[1])
    prefecture_counts = known_prefs
    if UNKNOWN_PREFECTURE in pref_counts:
        prefecture_counts = [*known_prefs, (UNKNOWN_PREFECTURE, pref_counts[UNKNOWN_PREFECTURE])]

    return DigestStats(
        target_date=target_date_jst,
        total=len(animals),
        dog=counts["dog"],
        cat=counts["cat"],
        other=counts["other"],
        prefecture_counts=prefecture_counts,
    )
