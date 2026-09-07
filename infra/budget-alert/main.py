"""GCP予算が90%到達したときにDiscordへ通知するCloud Function。

stop-billing (infra/stop-billing) と同じ Pub/Sub topic (budget-alerts) を
独立したサブスクリプションで購読する。stop-billing のコード・デプロイには
一切手を入れない（このFunctionは通知のみで、課金操作は一切行わない）。

閾値判定は Pub/Sub メッセージの `alertThresholdExceeded` を信用せず、
`costAmount / budgetAmount` を自前で計算する（GCP Budget通知は閾値に関係なく
1日に複数回届き、しかも `alertThresholdExceeded` が実際のcost比と一致しない
ケースがあるため、実測比率で判定する）。

月1回だけ通知するため、GCS上に `{bucket}/{YYYY-MM}/{threshold}` というマーカー
オブジェクトを `if_generation_match=0` で作成する。既に存在すれば
PreconditionFailed になるので「今月は既に通知済み」と判定してスキップする。
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os

import functions_framework
import requests
from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("budget-alert")

_DISCORD_TIMEOUT_SEC = 10

# (閾値, 通知メッセージの見出し)
# 100%は「stop-billingが発火しているはず」の情報通知。90%が主目的。
_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.9, ":warning: 予算90%到達"),
    (1.0, ":rotating_light: 予算100%到達（stop-billingが課金解除しているはず）"),
)


def _parse_message(cloud_event) -> dict:
    """Pub/Sub CloudEvent から budget notification の JSON payload を取り出す。"""
    data = json.loads(base64.b64decode(cloud_event.data["message"]["data"]).decode("utf-8"))
    return data


def _compute_ratio(data: dict) -> float | None:
    """costAmount / budgetAmount を自前で計算する。budgetAmountが0/欠損ならNone。"""
    cost = data.get("costAmount")
    budget = data.get("budgetAmount")
    if not isinstance(cost, (int, float)) or not isinstance(budget, (int, float)):
        return None
    if budget <= 0:
        return None
    return cost / budget


def _month_key(now: datetime.datetime | None = None) -> str:
    now = now or datetime.datetime.now(datetime.UTC)
    return now.strftime("%Y-%m")


def _mark_notified(bucket: storage.Bucket, month_key: str, threshold: float) -> bool:
    """マーカーオブジェクトを作成する。既に存在すれば False（今回は通知しない）。

    if_generation_match=0 は「オブジェクトが存在しない場合のみ作成」を意味する
    GCSの条件付き書き込み。複数回の同時実行でも1回しか成功しない（race-safe）。
    """
    blob_name = f"{month_key}/{threshold}"
    blob = bucket.blob(blob_name)
    try:
        blob.upload_from_string(
            f"notified at {datetime.datetime.now(datetime.UTC).isoformat()}",
            if_generation_match=0,
        )
        return True
    except PreconditionFailed:
        logger.info("既に通知済み（マーカー存在）: %s", blob_name)
        return False


def _send_discord(webhook_url: str, message: str, data: dict, ratio: float) -> None:
    """Discordへbest-effortで送信する。429/5xx等は握りつぶしてログのみ。"""
    content = (
        f"{message}\n"
        f"cost={data.get('costAmount')} budget={data.get('budgetAmount')} "
        f"ratio={ratio:.1%}\n"
        f"予算名: {data.get('budgetDisplayName', '(不明)')}"
    )
    try:
        response = requests.post(
            webhook_url, json={"content": content}, timeout=_DISCORD_TIMEOUT_SEC
        )
        if response.status_code >= 400:
            logger.warning(
                "Discord通知が失敗（status=%s）本文=%s", response.status_code, response.text[:200]
            )
    except requests.RequestException as exc:
        logger.warning("Discord通知が例外で失敗: %s", exc)


@functions_framework.cloud_event
def budget_alert(cloud_event) -> None:
    data = _parse_message(cloud_event)
    ratio = _compute_ratio(data)
    if ratio is None:
        logger.info("costAmount/budgetAmount が不正なためスキップ: %s", data)
        return

    logger.info(
        "予算比率: ratio=%.4f cost=%s budget=%s",
        ratio,
        data.get("costAmount"),
        data.get("budgetAmount"),
    )

    crossed = [(threshold, message) for threshold, message in _THRESHOLDS if ratio >= threshold]
    if not crossed:
        return

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    bucket_name = os.environ.get("BUDGET_ALERT_BUCKET")
    if not bucket_name:
        logger.error("BUDGET_ALERT_BUCKET が未設定のため通知をスキップ")
        return

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    month_key = _month_key()

    for threshold, message in crossed:
        if not _mark_notified(bucket, month_key, threshold):
            continue
        if not webhook_url:
            logger.warning(
                "DISCORD_WEBHOOK_URL 未設定のためDiscord送信はスキップ（マーカーは作成済み）"
            )
            continue
        _send_discord(webhook_url, message, data, ratio)
