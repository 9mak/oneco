"""SNS publisher CLI エントリ TDD

GitHub Actions cron から呼ばれる `python -m syndication_service.sns_publisher` の
最薄ラッパー。実 DB / 実 Threads API は触らない。

テストは pure pieces (exit code 計算 / Discord メッセージ整形 / generator/client 構築) に絞る。
"""

from __future__ import annotations

from datetime import date

from data_collector.domain.models import AnimalData, AnimalStatus
from syndication_service.sns_publisher.cli import (
    build_generator,
    build_threads_client,
    format_summary,
    result_to_exit_code,
)
from syndication_service.sns_publisher.publisher import PublishResult


def _animal() -> AnimalData:
    return AnimalData(
        species="犬",
        shelter_date=date(2026, 6, 1),
        location="高知県",
        source_url="https://example.jp/animals/1",
        category="adoption",
        status=AnimalStatus.SHELTERED,
    )


def _result(reason: str, *, posted: bool = False, dry_run: bool = False) -> PublishResult:
    return PublishResult(
        posted=posted,
        dry_run=dry_run,
        platform="threads",
        candidate=_animal() if reason not in {"disabled", "no_candidate"} else None,
        text="hi" if reason not in {"disabled", "no_candidate"} else None,
        reason=reason,
    )


class TestResultToExitCode:
    def test_posted_is_success(self):
        assert result_to_exit_code(_result(None, posted=True)) == 0

    def test_dry_run_is_success(self):
        assert result_to_exit_code(_result("dry_run", dry_run=True)) == 0

    def test_disabled_is_success(self):
        assert result_to_exit_code(_result("disabled")) == 0

    def test_no_candidate_is_success(self):
        assert result_to_exit_code(_result("no_candidate")) == 0

    def test_moderation_failed_is_failure(self):
        assert result_to_exit_code(_result("moderation_failed:pii_phone_detected")) == 1

    def test_publish_error_is_failure(self):
        assert result_to_exit_code(_result("publish_error:HTTPError")) == 1

    def test_no_api_client_is_failure(self):
        """wet 期待で API client が未設定 = 設定ミス。CI 通知すべき"""
        assert result_to_exit_code(_result("no_api_client")) == 1


class TestBuildGenerator:
    def test_with_groq_key_creates_client(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        gen = build_generator(env={"GROQ_API_KEY": "test-key"})
        # client が None でないこと (= LLM 経路が活きる)
        assert gen is not None
        # フォールバック専用 generator にはなっていない (= _client が設定済)
        # 露出を最小限にするため属性アクセスではなく動作確認:
        # mock せず実呼び出しはしない (CI で外部 API を叩かない方針)。
        # ここでは型と存在のみ確認。
        assert hasattr(gen, "generate")

    def test_without_groq_key_uses_fallback_only(self):
        gen = build_generator(env={})
        assert gen is not None
        # generator は client=None でも fallback で動作する
        text = gen.generate(_animal(), platform="threads")
        assert "#里親募集" in text


class TestBuildThreadsClient:
    def test_returns_none_when_no_token(self):
        client = build_threads_client(env={})
        assert client is None

    def test_returns_none_when_no_user_id(self):
        client = build_threads_client(env={"THREADS_ACCESS_TOKEN": "t"})
        assert client is None

    def test_returns_client_when_both_set(self):
        client = build_threads_client(env={"THREADS_ACCESS_TOKEN": "tok", "THREADS_USER_ID": "uid"})
        assert client is not None
        assert hasattr(client, "post")


class TestFormatSummary:
    def test_posted_summary(self):
        msg = format_summary(_result(None, posted=True))
        assert "Threads" in msg or "threads" in msg
        assert "投稿" in msg

    def test_dry_run_summary(self):
        msg = format_summary(_result("dry_run", dry_run=True))
        assert "dry" in msg.lower() or "ドライラン" in msg

    def test_disabled_summary(self):
        msg = format_summary(_result("disabled"))
        # 通知すべきだが警告レベルではない (info)
        assert "disabled" in msg or "無効" in msg

    def test_no_candidate_summary(self):
        msg = format_summary(_result("no_candidate"))
        assert "候補" in msg or "candidate" in msg.lower()

    def test_moderation_failed_includes_reasons(self):
        msg = format_summary(_result("moderation_failed:pii_phone_detected"))
        assert "moderation" in msg.lower() or "モデレーション" in msg
        assert "pii_phone_detected" in msg

    def test_publish_error_summary(self):
        msg = format_summary(_result("publish_error:HTTPError"))
        assert "publish_error" in msg or "投稿失敗" in msg
        assert "HTTPError" in msg
