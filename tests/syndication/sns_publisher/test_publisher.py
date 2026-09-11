"""SNS digest publisher orchestrator TDD (T151 設計 / T160)

前日 (JST) の新着まとめを 1 投稿する publish_daily_digest() を検証する。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from data_collector.domain.models import AnimalData
from syndication_service.sns_publisher.digest import DigestStats
from syndication_service.sns_publisher.post_log import DigestLog
from syndication_service.sns_publisher.publisher import (
    DigestPublishResult,
    publish_daily_digest,
)
from syndication_service.sns_publisher.threads_client import ThreadsPostError

_TARGET_DATE = date(2026, 9, 10)


def _animal(*, prefecture: str | None = "高知県") -> AnimalData:
    return AnimalData(
        species="犬",
        shelter_date=date(2026, 6, 1),
        location=prefecture or "不明",
        prefecture=prefecture,
        source_url="https://example.jp/animals/1",
        category="adoption",
    )


def _repo(animals: list[AnimalData] | None = None) -> Any:
    repo = AsyncMock()
    repo.list_animals_first_seen_between.return_value = (
        animals if animals is not None else [_animal()]
    )
    return repo


def _log(tmp_path: Path) -> DigestLog:
    return DigestLog(path=tmp_path / "sns_digest_log.yaml")


@pytest.mark.asyncio
class TestKillSwitch:
    async def test_disabled_by_default(self, tmp_path):
        repo = _repo()
        result = await publish_daily_digest(
            repo=repo,
            digest_log=_log(tmp_path),
            target_date_jst=_TARGET_DATE,
            env={},
        )
        assert isinstance(result, DigestPublishResult)
        assert result.posted is False
        assert result.reason == "disabled"
        repo.list_animals_first_seen_between.assert_not_called()

    async def test_enabled_proceeds_to_collect(self, tmp_path):
        repo = _repo()
        await publish_daily_digest(
            repo=repo,
            digest_log=_log(tmp_path),
            target_date_jst=_TARGET_DATE,
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        repo.list_animals_first_seen_between.assert_called_once()


@pytest.mark.asyncio
class TestAlreadyPosted:
    async def test_already_posted_date_skips_collection(self, tmp_path):
        log = _log(tmp_path)
        log.record(date_str=_TARGET_DATE.isoformat(), post_id="1", posted_at="x")
        repo = _repo()
        result = await publish_daily_digest(
            repo=repo,
            digest_log=log,
            target_date_jst=_TARGET_DATE,
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.reason == "already_posted"
        repo.list_animals_first_seen_between.assert_not_called()


@pytest.mark.asyncio
class TestNoNewAnimals:
    async def test_zero_animals_skips_posting(self, tmp_path):
        repo = _repo([])
        result = await publish_daily_digest(
            repo=repo,
            digest_log=_log(tmp_path),
            target_date_jst=_TARGET_DATE,
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.posted is False
        assert result.reason == "no_new_animals"
        assert result.stats is None


@pytest.mark.asyncio
class TestDryRun:
    async def test_dry_run_default_true_does_not_record(self, tmp_path):
        repo = _repo()
        log = _log(tmp_path)
        result = await publish_daily_digest(
            repo=repo,
            digest_log=log,
            target_date_jst=_TARGET_DATE,
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        assert result.dry_run is True
        assert result.posted is False
        assert result.reason == "dry_run"
        assert isinstance(result.stats, DigestStats)
        assert result.text is not None
        # dry_run はログに記録しない (実運用の判断に影響を与えないため)
        assert log.is_posted(_TARGET_DATE.isoformat()) is False

    async def test_dry_run_false_without_client_returns_no_api_client(self, tmp_path):
        repo = _repo()
        result = await publish_daily_digest(
            repo=repo,
            digest_log=_log(tmp_path),
            target_date_jst=_TARGET_DATE,
            env={"THREADS_PUBLISH_ENABLED": "true", "THREADS_PUBLISH_DRY_RUN": "false"},
        )
        assert result.reason == "no_api_client"
        assert result.posted is False


def _wet_env() -> dict[str, str]:
    return {"THREADS_PUBLISH_ENABLED": "true", "THREADS_PUBLISH_DRY_RUN": "false"}


@pytest.mark.asyncio
class TestWetModePublish:
    async def test_wet_success_posts_and_records(self, tmp_path):
        repo = _repo()
        log = _log(tmp_path)
        client = MagicMock()
        client.post.return_value = "published_thread_id"

        result = await publish_daily_digest(
            repo=repo,
            digest_log=log,
            target_date_jst=_TARGET_DATE,
            env=_wet_env(),
            threads_client=client,
        )

        assert result.posted is True
        assert result.dry_run is False
        assert result.reason is None
        client.post.assert_called_once()
        # 画像なし固定で呼ぶ
        assert client.post.call_args.kwargs.get("image_url") is None
        assert log.is_posted(_TARGET_DATE.isoformat()) is True
        # 再ロードでも持続
        assert DigestLog(path=tmp_path / "sns_digest_log.yaml").is_posted(_TARGET_DATE.isoformat())

    async def test_wet_post_failure_does_not_pollute_log(self, tmp_path):
        repo = _repo()
        log = _log(tmp_path)
        client = MagicMock()
        client.post.side_effect = ThreadsPostError("publish failed: 500 Server Error")

        result = await publish_daily_digest(
            repo=repo,
            digest_log=log,
            target_date_jst=_TARGET_DATE,
            env=_wet_env(),
            threads_client=client,
        )

        assert result.posted is False
        assert result.reason == "publish_error:ThreadsPostError"
        assert log.is_posted(_TARGET_DATE.isoformat()) is False

    async def test_wet_post_failure_does_not_leak_token_to_logs(self, tmp_path, caplog):
        import logging

        repo = _repo()
        log = _log(tmp_path)
        client = MagicMock()
        client.post.side_effect = ThreadsPostError(
            "container creation failed: 403 Client Error: Forbidden for url: "
            "https://graph.threads.net/v1.0/1/threads?access_token=<redacted>&text=hi"
        )

        with caplog.at_level(logging.ERROR):
            result = await publish_daily_digest(
                repo=repo,
                digest_log=log,
                target_date_jst=_TARGET_DATE,
                env=_wet_env(),
                threads_client=client,
            )

        assert result.posted is False
        assert "access_token=<redacted>" in caplog.text or "<redacted>" in caplog.text
        assert "access_token=test" not in caplog.text
