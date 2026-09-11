"""SNS digest publisher CLI エントリ TDD (T160)

GitHub Actions cron から呼ばれる `python -m syndication_service.sns_publisher` の
最薄ラッパー。実 DB / 実 Threads API は触らない。

テストは pure pieces (exit code 計算 / Discord メッセージ整形 / client 構築 /
--dry-run フラグの扱い) に絞る。
"""

from __future__ import annotations

from datetime import date

from syndication_service.sns_publisher.cli import (
    build_threads_client,
    format_summary,
    main,
    result_to_exit_code,
)
from syndication_service.sns_publisher.digest import DigestStats
from syndication_service.sns_publisher.publisher import DigestPublishResult

_STATS = DigestStats(
    target_date=date(2026, 9, 10),
    total=3,
    dog=2,
    cat=1,
    other=0,
    prefecture_counts=[("高知県", 3)],
)


def _result(
    reason: str | None, *, posted: bool = False, dry_run: bool = False
) -> DigestPublishResult:
    has_stats = reason not in {"disabled", "no_database", "already_posted", "no_new_animals"}
    return DigestPublishResult(
        posted=posted,
        dry_run=dry_run,
        stats=_STATS if has_stats else None,
        text="内訳: 高知県 3。" if has_stats else None,
        reason=reason,
    )


class TestResultToExitCode:
    def test_posted_is_success(self):
        assert result_to_exit_code(_result(None, posted=True)) == 0

    def test_dry_run_is_success(self):
        assert result_to_exit_code(_result("dry_run", dry_run=True)) == 0

    def test_disabled_is_success(self):
        assert result_to_exit_code(_result("disabled")) == 0

    def test_no_new_animals_is_success(self):
        assert result_to_exit_code(_result("no_new_animals")) == 0

    def test_already_posted_is_success(self):
        assert result_to_exit_code(_result("already_posted")) == 0

    def test_publish_error_is_failure(self):
        assert result_to_exit_code(_result("publish_error:HTTPError")) == 1

    def test_no_api_client_is_failure(self):
        """wet 期待で API client が未設定 = 設定ミス。CI 通知すべき"""
        assert result_to_exit_code(_result("no_api_client")) == 1

    def test_no_database_is_failure(self):
        assert result_to_exit_code(_result("no_database")) == 1


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

    def test_dry_run_summary_includes_text(self):
        msg = format_summary(_result("dry_run", dry_run=True))
        assert "dry" in msg.lower() or "ドライラン" in msg
        assert "高知県 3" in msg

    def test_disabled_summary(self):
        msg = format_summary(_result("disabled"))
        assert "disabled" in msg or "無効" in msg

    def test_no_new_animals_summary(self):
        msg = format_summary(_result("no_new_animals"))
        assert "新着" in msg

    def test_already_posted_summary(self):
        msg = format_summary(_result("already_posted"))
        assert "投稿済み" in msg

    def test_no_api_client_summary(self):
        msg = format_summary(_result("no_api_client"))
        assert "no_api_client" in msg

    def test_publish_error_summary(self):
        msg = format_summary(_result("publish_error:HTTPError"))
        assert "publish_error" in msg or "投稿失敗" in msg
        assert "HTTPError" in msg


class TestMainDryRunFlag:
    """--dry-run は集計・文面表示のみで DB 接続を要求しない経路を通る。

    実 DB 接続まではテストしない (DATABASE_URL 未設定なら no_database で
    早期リターンする既存経路を再利用する) が、フラグが解析されエラーに
    ならないことを確認する。
    """

    def test_dry_run_flag_does_not_require_database_url(self, monkeypatch, capsys):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        exit_code = main(["--dry-run"])
        # DATABASE_URL 未設定なら no_database (failure) だが、フラグ解析自体は
        # 例外を出さずに完走する
        assert exit_code == 1
