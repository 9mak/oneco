"""budget-alert Cloud Function のユニットテスト。

infra/budget-alert は独立デプロイ単位（GCP依存のrequirements.txtを別に持つ）のため、
テスト実行時だけ sys.path に追加してimportする。
"""

from __future__ import annotations

import base64
import datetime
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import PreconditionFailed

_BUDGET_ALERT_DIR = Path(__file__).resolve().parents[2] / "infra" / "budget-alert"
if str(_BUDGET_ALERT_DIR) not in sys.path:
    sys.path.insert(0, str(_BUDGET_ALERT_DIR))

import main as budget_alert_main  # noqa: E402


def _cloud_event(payload: dict) -> MagicMock:
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    event = MagicMock()
    event.data = {"message": {"data": encoded}}
    return event


class TestParseAndRatio:
    def test_parse_message_decodes_base64_json(self):
        event = _cloud_event({"costAmount": 450, "budgetAmount": 500})
        assert budget_alert_main._parse_message(event) == {
            "costAmount": 450,
            "budgetAmount": 500,
        }

    def test_compute_ratio_normal(self):
        assert budget_alert_main._compute_ratio(
            {"costAmount": 450, "budgetAmount": 500}
        ) == pytest.approx(0.9)

    def test_compute_ratio_zero_budget_returns_none(self):
        assert budget_alert_main._compute_ratio({"costAmount": 10, "budgetAmount": 0}) is None

    def test_compute_ratio_missing_fields_returns_none(self):
        assert budget_alert_main._compute_ratio({"costAmount": 10}) is None
        assert budget_alert_main._compute_ratio({}) is None

    def test_compute_ratio_ignores_alert_threshold_exceeded_field(self):
        """alertThresholdExceededは信用せず、costAmount/budgetAmountだけで計算する"""
        data = {"costAmount": 100, "budgetAmount": 500, "alertThresholdExceeded": 0.9}
        assert budget_alert_main._compute_ratio(data) == pytest.approx(0.2)


class TestMonthKey:
    def test_uses_cost_interval_start_not_processing_time(self):
        """処理時刻でなく costIntervalStart 由来の月を使う（F-01）"""
        data = {"costAmount": 450, "budgetAmount": 500, "costIntervalStart": "2026-08-01T00:00:00Z"}
        assert budget_alert_main._month_key(data) == "2026-08"

    def test_delayed_delivery_across_month_boundary_uses_original_period(self):
        """8月分の通知が9月にずれ込んで処理されても、キーは8月のまま
        （処理時刻基準だと9月のマーカーを誤って消費し、本物の9月90%通知が
        抑止されてしまう。F-01のシナリオそのもの。costIntervalStartが有効な限り
        処理時刻（今が9月であること）はキー算出に一切影響しない）"""
        data = {
            "costAmount": 495,
            "budgetAmount": 500,
            "costIntervalStart": "2026-08-28T00:00:00Z",
        }
        assert budget_alert_main._month_key(data) == "2026-08"

    def test_missing_cost_interval_start_falls_back_to_now_with_error_log(self, caplog):
        data = {"costAmount": 450, "budgetAmount": 500}
        with caplog.at_level("ERROR"):
            key = budget_alert_main._month_key(data)
        assert key == datetime.datetime.now(datetime.UTC).strftime("%Y-%m")
        assert any("フォールバック" in record.message for record in caplog.records)

    def test_malformed_cost_interval_start_falls_back_to_now_with_error_log(self, caplog):
        data = {"costAmount": 450, "budgetAmount": 500, "costIntervalStart": "not-a-date"}
        with caplog.at_level("ERROR"):
            key = budget_alert_main._month_key(data)
        assert key == datetime.datetime.now(datetime.UTC).strftime("%Y-%m")
        assert any("フォールバック" in record.message for record in caplog.records)


class TestMarkNotified:
    def test_first_call_creates_marker_and_returns_true(self):
        bucket = MagicMock()
        blob = MagicMock()
        bucket.blob.return_value = blob

        result = budget_alert_main._mark_notified(bucket, "2026-09", 0.9)

        assert result is True
        blob.upload_from_string.assert_called_once()
        _, kwargs = blob.upload_from_string.call_args
        assert kwargs["if_generation_match"] == 0
        bucket.blob.assert_called_once_with("2026-09/0.9")

    def test_second_call_precondition_failed_returns_false(self):
        bucket = MagicMock()
        blob = MagicMock()
        blob.upload_from_string.side_effect = PreconditionFailed("already exists")
        bucket.blob.return_value = blob

        result = budget_alert_main._mark_notified(bucket, "2026-09", 0.9)

        assert result is False


class TestSendDiscord:
    def test_success_does_not_raise(self):
        with patch.object(budget_alert_main, "requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=204)
            budget_alert_main._send_discord(
                "https://discord.example/webhook",
                ":warning: test",
                {"costAmount": 450, "budgetAmount": 500},
                0.9,
            )
            mock_requests.post.assert_called_once()

    def test_429_is_swallowed_not_raised(self):
        with patch.object(budget_alert_main, "requests") as mock_requests:
            mock_requests.post.return_value = MagicMock(status_code=429, text="rate limited")
            # 例外を投げないことだけを確認する
            budget_alert_main._send_discord(
                "https://discord.example/webhook",
                ":warning: test",
                {"costAmount": 450, "budgetAmount": 500},
                0.9,
            )

    def test_request_exception_is_swallowed(self):
        import requests as real_requests

        with patch.object(budget_alert_main, "requests") as mock_requests:
            mock_requests.RequestException = real_requests.RequestException
            mock_requests.post.side_effect = real_requests.RequestException("boom")
            budget_alert_main._send_discord(
                "https://discord.example/webhook",
                ":warning: test",
                {"costAmount": 450, "budgetAmount": 500},
                0.9,
            )


class TestBudgetAlertEntrypoint:
    def _make_env(
        self, monkeypatch, webhook="https://discord.example/webhook", bucket="test-bucket"
    ):
        if webhook is not None:
            monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook)
        else:
            monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        if bucket is not None:
            monkeypatch.setenv("BUDGET_ALERT_BUCKET", bucket)
        else:
            monkeypatch.delenv("BUDGET_ALERT_BUCKET", raising=False)

    def test_below_90_percent_does_nothing(self, monkeypatch):
        self._make_env(monkeypatch)
        event = _cloud_event({"costAmount": 100, "budgetAmount": 500})

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
        ):
            budget_alert_main.budget_alert(event)

        mock_storage.Client.assert_not_called()
        mock_requests.post.assert_not_called()

    def test_90_percent_marks_and_sends_discord(self, monkeypatch):
        self._make_env(monkeypatch)
        event = _cloud_event({"costAmount": 450, "budgetAmount": 500})

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
        ):
            mock_storage.Client.return_value = mock_client
            mock_requests.post.return_value = MagicMock(status_code=204)

            budget_alert_main.budget_alert(event)

        mock_blob.upload_from_string.assert_called_once()
        mock_requests.post.assert_called_once()

    def test_100_percent_crosses_both_thresholds_two_markers_two_messages(self, monkeypatch):
        self._make_env(monkeypatch)
        event = _cloud_event({"costAmount": 500, "budgetAmount": 500})

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
        ):
            mock_storage.Client.return_value = mock_client
            mock_requests.post.return_value = MagicMock(status_code=204)

            budget_alert_main.budget_alert(event)

        assert mock_blob.upload_from_string.call_count == 2
        assert mock_requests.post.call_count == 2

    def test_already_notified_skips_discord(self, monkeypatch):
        """マーカー作成がPreconditionFailedなら（今月既に通知済み）Discordは送らない"""
        self._make_env(monkeypatch)
        event = _cloud_event({"costAmount": 450, "budgetAmount": 500})

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string.side_effect = PreconditionFailed("exists")
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
        ):
            mock_storage.Client.return_value = mock_client

            budget_alert_main.budget_alert(event)

        mock_requests.post.assert_not_called()

    def test_missing_bucket_env_skips_without_error(self, monkeypatch):
        self._make_env(monkeypatch, bucket=None)
        event = _cloud_event({"costAmount": 450, "budgetAmount": 500})

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
        ):
            budget_alert_main.budget_alert(event)

        mock_storage.Client.assert_not_called()
        mock_requests.post.assert_not_called()

    def test_missing_webhook_still_marks_but_skips_discord(self, monkeypatch):
        self._make_env(monkeypatch, webhook=None)
        event = _cloud_event({"costAmount": 450, "budgetAmount": 500})

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
        ):
            mock_storage.Client.return_value = mock_client

            budget_alert_main.budget_alert(event)

        mock_blob.upload_from_string.assert_called_once()
        mock_requests.post.assert_not_called()

    def test_malformed_payload_is_swallowed_with_error_log_not_raised(self, monkeypatch, caplog):
        """不正base64/JSONはPub/Subへ非2xxを返さず正常終了する（F-02）"""
        self._make_env(monkeypatch)
        event = MagicMock()
        event.data = {"message": {"data": "not-valid-base64-json!!!"}}

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
            caplog.at_level("ERROR"),
        ):
            budget_alert_main.budget_alert(event)  # 例外を投げないことを確認

        mock_storage.Client.assert_not_called()
        mock_requests.post.assert_not_called()
        assert any("握りつぶして正常終了" in record.message for record in caplog.records)

    def test_gcs_non_precondition_error_is_swallowed_with_error_log(self, monkeypatch, caplog):
        """PreconditionFailed以外のGCS例外（権限エラー等）も再配信を招かず正常終了する（F-02）"""
        from google.api_core.exceptions import Forbidden

        self._make_env(monkeypatch)
        event = _cloud_event({"costAmount": 450, "budgetAmount": 500})

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string.side_effect = Forbidden("no permission")
        mock_bucket.blob.return_value = mock_blob
        mock_client = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        with (
            patch.object(budget_alert_main, "storage") as mock_storage,
            patch.object(budget_alert_main, "requests") as mock_requests,
            caplog.at_level("ERROR"),
        ):
            mock_storage.Client.return_value = mock_client

            budget_alert_main.budget_alert(event)  # 例外を投げないことを確認

        mock_requests.post.assert_not_called()
        assert any("握りつぶして正常終了" in record.message for record in caplog.records)
