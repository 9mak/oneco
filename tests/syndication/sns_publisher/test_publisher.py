"""SNS publisher orchestrator TDD

design.md 5.2 のパイプライン全体を 1 関数 (publish_one) で束ねる。

- kill switch THREADS_PUBLISH_ENABLED (default false) は厳格に守る
- dry_run THREADS_PUBLISH_DRY_RUN (default true) は段階的活性化のため
- Threads API クライアント (実投稿) は次 PR。本 PR は client=None で
  「moderate まで通って投稿 URL だけ post_log に記録される」までを実装
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from data_collector.domain.models import AnimalData, AnimalStatus
from syndication_service.sns_publisher.post_log import PostLog
from syndication_service.sns_publisher.publisher import (
    PublishResult,
    publish_one,
)


def _animal(
    *,
    source_url: str = "https://example.jp/animals/1",
    image_urls: list[str] | None = None,
    status: AnimalStatus | None = AnimalStatus.SHELTERED,
) -> AnimalData:
    return AnimalData(
        species="犬",
        shelter_date=date(2026, 6, 1),
        location="高知県",
        source_url=source_url,
        category="adoption",
        image_urls=image_urls if image_urls is not None else ["https://example.jp/img/1.jpg"],
        status=status,
    )


def _repo(animals: list[AnimalData]) -> Any:
    repo = AsyncMock()
    repo.list_animals.return_value = (animals, len(animals))
    return repo


def _gen(text: str = "保護犬さん募集中 #保護犬 #里親募集") -> Any:
    g = MagicMock()
    g.generate.return_value = text
    return g


def _log(tmp_path: Path) -> PostLog:
    return PostLog(path=tmp_path / "sns_posts.yaml")


@pytest.mark.asyncio
class TestKillSwitch:
    async def test_disabled_by_default(self, monkeypatch, tmp_path):
        monkeypatch.delenv("THREADS_PUBLISH_ENABLED", raising=False)
        repo = _repo([_animal()])
        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=_log(tmp_path),
            platform="threads",
            env={},
        )
        assert isinstance(result, PublishResult)
        assert result.posted is False
        assert result.reason == "disabled"
        repo.list_animals.assert_not_called()

    async def test_enabled_proceeds_to_select(self, tmp_path):
        repo = _repo([_animal()])
        await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=_log(tmp_path),
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        repo.list_animals.assert_called_once()


@pytest.mark.asyncio
class TestDryRun:
    async def test_dry_run_default_true(self, tmp_path):
        """有効化されても dry_run=true 既定で実投稿しない (段階リリース)"""
        repo = _repo([_animal()])
        log = _log(tmp_path)
        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=log,
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.dry_run is True
        assert result.posted is False  # dry_run なので実投稿フラグは False
        assert result.reason == "dry_run"
        # post_log には記録される (重複投稿防止のため)
        assert str(_animal().source_url) in log.posted_urls()

    async def test_dry_run_false_without_client_returns_no_client(self, tmp_path):
        """dry_run=false でも Threads client 未注入なら no_api_client で止まる (次 PR の余地)"""
        repo = _repo([_animal()])
        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=_log(tmp_path),
            platform="threads",
            env={
                "THREADS_PUBLISH_ENABLED": "true",
                "THREADS_PUBLISH_DRY_RUN": "false",
            },
        )
        assert result.reason == "no_api_client"
        assert result.posted is False


@pytest.mark.asyncio
class TestModeration:
    async def test_pii_in_text_aborts_publish(self, tmp_path):
        repo = _repo([_animal()])
        log = _log(tmp_path)
        result = await publish_one(
            repo=repo,
            generator=_gen("連絡は 090-1234-5678 まで"),
            post_log=log,
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.posted is False
        assert result.reason is not None
        assert "moderation" in result.reason
        # PII 検出 → 不正テキストを post_log に残さない (= 再選定の余地)
        assert log.posted_urls() == set()

    async def test_deceased_in_pool_skipped_via_status_filter(self, tmp_path):
        """select_candidate が status=SHELTERED で絞るため、ここでは
        repo に SHELTERED のみ返してもらえる前提。moderator が二重防御する。"""
        repo = _repo([_animal()])
        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=_log(tmp_path),
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.reason in {"dry_run", "no_api_client"}


@pytest.mark.asyncio
class TestNoCandidate:
    async def test_no_candidate(self, tmp_path):
        repo = _repo([])
        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=_log(tmp_path),
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.posted is False
        assert result.reason == "no_candidate"
        assert result.candidate is None

    async def test_all_already_posted(self, tmp_path):
        url = "https://example.jp/animals/1"
        repo = _repo([_animal(source_url=url)])
        log = _log(tmp_path)
        log.record(url=url, platform="threads", text="prev", dry_run=True)
        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=log,
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.reason == "no_candidate"


@pytest.mark.asyncio
class TestRecord:
    async def test_dry_run_records_to_log(self, tmp_path):
        log = _log(tmp_path)
        repo = _repo([_animal(source_url="https://example.jp/animals/42")])
        await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=log,
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        urls = log.posted_urls()
        assert "https://example.jp/animals/42" in urls
        # 再ロードでも持続する
        reloaded = PostLog(path=tmp_path / "sns_posts.yaml")
        assert "https://example.jp/animals/42" in reloaded.posted_urls()
