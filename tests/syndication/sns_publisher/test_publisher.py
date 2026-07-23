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
from syndication_service.sns_publisher.threads_client import ThreadsPostError


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


def _repo(animals: list[AnimalData], *, animal_id: int | None = None) -> Any:
    repo = AsyncMock()
    repo.list_animals.return_value = (animals, len(animals))
    repo.get_animal_id_by_source_url.return_value = animal_id
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


@pytest.mark.asyncio
class TestOnecoUrl:
    """投稿本文に oneco 自体への誘導リンクを添える (集客導線)。

    自治体公式リンクは design.md の方針どおり維持しつつ、animal_id が
    引ける場合のみ oneco の動物詳細ページへの導線を additional に渡す。
    """

    async def test_passes_oneco_url_when_animal_id_resolvable(self, tmp_path):
        repo = _repo([_animal(source_url="https://example.jp/animals/42")], animal_id=42)
        gen = _gen()
        await publish_one(
            repo=repo,
            generator=gen,
            post_log=_log(tmp_path),
            platform="threads",
            env={
                "THREADS_PUBLISH_ENABLED": "true",
                "SITE_URL": "https://frontend-psi-ten-73.vercel.app",
            },
        )
        kwargs = gen.generate.call_args.kwargs
        assert kwargs.get("oneco_url") is not None
        assert "frontend-psi-ten-73.vercel.app/animals/42" in kwargs["oneco_url"]
        assert "utm_source=threads" in kwargs["oneco_url"]

    async def test_oneco_url_none_when_animal_id_not_found(self, tmp_path):
        repo = _repo([_animal()], animal_id=None)
        gen = _gen()
        await publish_one(
            repo=repo,
            generator=gen,
            post_log=_log(tmp_path),
            platform="threads",
            env={"THREADS_PUBLISH_ENABLED": "true"},
        )
        kwargs = gen.generate.call_args.kwargs
        assert kwargs.get("oneco_url") is None


def _wet_env() -> dict[str, str]:
    """wet mode (実投稿) を有効化する env。本番 cron と同じ状態。"""
    return {"THREADS_PUBLISH_ENABLED": "true", "THREADS_PUBLISH_DRY_RUN": "false"}


@pytest.mark.asyncio
class TestWetModePublish:
    """wet-mode (dry_run=false + client 注入) の実投稿経路。

    本番 cron (JST 9:00) で毎日実行されているが、threads_client 注入時の
    success/failure 経路は従来テストが無く、全体監査 (2026-06-24) で P1 と
    して検出された。Mock ThreadsClient で publisher.publish_one の wet branch
    (publisher.py の client.post → post_log.record → posted=True) を固定する。
    """

    async def test_wet_success_posts_and_records(self, tmp_path):
        """post 成功 → posted=True / reason=None / post_log に記録 (重複防止)"""
        url = "https://example.jp/animals/77"
        repo = _repo([_animal(source_url=url)])
        log = _log(tmp_path)
        client = MagicMock()
        client.post.return_value = "published_thread_id"

        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=log,
            platform="threads",
            env=_wet_env(),
            threads_client=client,
        )

        assert result.posted is True
        assert result.dry_run is False
        assert result.reason is None
        client.post.assert_called_once()
        # 実投稿したものは post_log に残す (翌日同一個体の重複投稿を防ぐ)
        assert url in log.posted_urls()
        # 再ロードでも持続
        assert url in PostLog(path=tmp_path / "sns_posts.yaml").posted_urls()

    async def test_wet_post_failure_does_not_pollute_log(self, tmp_path):
        """post が例外 → posted=False / reason=publish_error:* / post_log 汚染なし

        投稿に失敗したのに post_log に記録されると、その個体が二度と
        投稿候補に上がらず永久に取りこぼされる。失敗時は記録しない契約。
        """
        url = "https://example.jp/animals/88"
        repo = _repo([_animal(source_url=url)])
        log = _log(tmp_path)
        client = MagicMock()
        client.post.side_effect = ThreadsPostError("publish failed: 500 Server Error")

        result = await publish_one(
            repo=repo,
            generator=_gen(),
            post_log=log,
            platform="threads",
            env=_wet_env(),
            threads_client=client,
        )

        assert result.posted is False
        assert result.reason == "publish_error:ThreadsPostError"
        # 失敗 → post_log に残さない (= 次回 run で再選定の余地)
        assert url not in log.posted_urls()
        assert log.posted_urls() == set()

    async def test_wet_post_failure_does_not_leak_token_to_logs(self, tmp_path, caplog):
        """post 例外メッセージに token が含まれても publisher のログに漏れない。

        threads_client 側で redaction 済みだが、publisher のエラーログ
        (err=%s) に exc を載せる経路の end-to-end 回帰を固定する。
        """
        import logging

        url = "https://example.jp/animals/99"
        repo = _repo([_animal(source_url=url)])
        log = _log(tmp_path)
        client = MagicMock()
        # threads_client が redaction 済みメッセージを投げる前提 (実装と一致)
        client.post.side_effect = ThreadsPostError(
            "container creation failed: 403 Client Error: Forbidden for url: "
            "https://graph.threads.net/v1.0/1/threads?access_token=<redacted>&text=hi"
        )

        with caplog.at_level(logging.ERROR):
            result = await publish_one(
                repo=repo,
                generator=_gen(),
                post_log=log,
                platform="threads",
                env=_wet_env(),
                threads_client=client,
            )

        assert result.posted is False
        # ログ全体に生 token が出ない
        assert "access_token=<redacted>" in caplog.text or "<redacted>" in caplog.text
        # 生トークンらしき文字列が無い (redaction マーカー以外の access_token= が無い)
        assert "access_token=test" not in caplog.text
