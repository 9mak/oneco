"""
notification-manager APIルート定義

このモジュールはnotification-managerのAPIエンドポイントを定義します:
- POST /api/v1/notifications/webhook: data-collectorからの新着通知
- POST /api/v1/line/webhook: LINEプラットフォームからのWebhook
- GET /health: ヘルスチェック

Requirements: 2.1-2.5, 6.6, 7.2-7.4
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from src.data_collector.domain.models import AnimalData
from src.notification_manager.adapters.line_adapter import LineNotificationAdapter
from src.notification_manager.domain.services import NotificationService, UserService
from src.notification_manager.infrastructure.api.schemas import (
    HealthResponse,
    LineWebhookRequest,
    NewAnimalWebhookRequest,
    WebhookResponse,
)

logger = logging.getLogger(__name__)


class NotificationWebhookDeps:
    """
    Webhookエンドポイントの依存関係

    依存性注入のためのコンテナクラス
    """

    def __init__(
        self,
        notification_service: NotificationService = None,
        user_service: UserService = None,
        line_adapter: LineNotificationAdapter = None,
        api_key: str | None = None,
        db_check_func: Callable[[], bool] | None = None,
        line_api_check_func: Callable[[], bool] | None = None,
    ):
        self._notification_service = notification_service
        self._user_service = user_service
        self._line_adapter = line_adapter
        self._api_key = api_key
        self._db_check_func = db_check_func or (lambda: True)
        self._line_api_check_func = line_api_check_func or (lambda: True)


def create_notification_router(deps: NotificationWebhookDeps) -> APIRouter:
    """
    通知管理用ルーターを作成

    Args:
        deps: 依存関係コンテナ

    Returns:
        APIRouter: 設定済みルーター
    """
    router = APIRouter()
    # depsをルーターに保持（テスト用）
    router.deps = deps

    @router.post(
        "/api/v1/notifications/webhook",
        response_model=WebhookResponse,
        status_code=202,
        summary="新着動物Webhook",
        description="data-collectorからの新着動物通知を受信",
    )
    async def receive_notification_webhook(
        request: NewAnimalWebhookRequest,
        background_tasks: BackgroundTasks,
        x_api_key: str | None = Header(None, alias="X-API-Key"),
    ):
        """
        data-collectorからの新着動物Webhookを受信

        Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 7.2, 7.3
        """
        # APIキー認証
        if not x_api_key:
            logger.warning("Webhook request without API key")
            raise HTTPException(status_code=401, detail="API key required")

        if x_api_key != deps._api_key:
            logger.warning("Webhook request with invalid API key")
            raise HTTPException(status_code=401, detail="Invalid API key")

        # AnimalDataに変換
        animals = []
        for animal_schema in request.animals:
            animal = AnimalData(
                species=animal_schema.species,
                sex=animal_schema.sex,
                age_months=animal_schema.age_months,
                color=animal_schema.color,
                size=animal_schema.size,
                shelter_date=animal_schema.shelter_date,
                location=animal_schema.location,
                phone=animal_schema.phone,
                image_urls=animal_schema.image_urls,
                source_url=animal_schema.source_url,
                category=animal_schema.category,
            )
            animals.append(animal)

        # バックグラウンドで通知処理を実行
        background_tasks.add_task(
            process_notifications_background,
            deps._notification_service,
            animals,
        )

        logger.info(f"Webhook received: {len(animals)} animals from {request.source}")

        return WebhookResponse(
            status="accepted",
            message=f"Processing {len(animals)} animals",
        )

    @router.post(
        "/api/v1/line/webhook",
        status_code=200,
        summary="LINE Webhook",
        description="LINEプラットフォームからのイベントを受信",
    )
    async def receive_line_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        x_line_signature: str | None = Header(None, alias="X-Line-Signature"),
    ):
        """
        LINEプラットフォームからのWebhookを受信

        Requirements: 1.1, 7.4, 7.5
        """
        # 署名検証
        if not x_line_signature:
            logger.warning("LINE webhook request without signature")
            raise HTTPException(status_code=400, detail="Signature required")

        body = await request.body()

        if deps._line_adapter and not deps._line_adapter.verify_signature(body, x_line_signature):
            logger.warning("LINE webhook signature verification failed")
            raise HTTPException(status_code=400, detail="Invalid signature")

        # リクエストパース
        try:
            json_body = await request.json()
            webhook_request = LineWebhookRequest(**json_body)
        except Exception as e:
            logger.error(f"Failed to parse LINE webhook request: {e}")
            raise HTTPException(status_code=400, detail="Invalid request body")

        # イベント処理
        for event in webhook_request.events:
            if event.type == "follow":
                # 友だち追加
                user_id = event.source.get("userId")
                if user_id and deps._user_service:
                    background_tasks.add_task(deps._user_service.register_user, user_id)
                    logger.info(f"Follow event received: {user_id[:8]}...")

            elif event.type == "unfollow":
                # ブロック/削除
                user_id = event.source.get("userId")
                if user_id and deps._user_service:
                    background_tasks.add_task(deps._user_service.deactivate_user, user_id)
                    logger.info(f"Unfollow event received: {user_id[:8]}...")

            elif event.type == "message":
                # メッセージ受信（条件設定コマンド用）
                user_id = event.source.get("userId")
                message = event.message
                if user_id and message:
                    logger.info(
                        f"Message event received from {user_id[:8]}...: "
                        f"{message.get('type', 'unknown')}"
                    )
                    # Task 7で実装予定のコマンド処理

        return {"status": "ok"}

    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="ヘルスチェック",
        description="サービスの状態を確認",
    )
    async def health_check():
        """
        ヘルスチェックエンドポイント

        Requirement 6.6
        """
        db_ok = deps._db_check_func()
        line_api_ok = deps._line_api_check_func()

        # ステータス判定
        if not db_ok:
            status = "unhealthy"
            status_code = 503
        elif not line_api_ok:
            status = "degraded"
            status_code = 200
        else:
            status = "healthy"
            status_code = 200

        response = HealthResponse(
            status=status,
            database=db_ok,
            line_api=line_api_ok,
            timestamp=datetime.now(UTC),
        )

        if status_code != 200:
            return JSONResponse(
                status_code=status_code,
                content=response.model_dump(mode="json"),
            )

        return response

    return router


async def process_notifications_background(
    notification_service: NotificationService,
    animals: list,
):
    """
    バックグラウンドで通知処理を実行

    Args:
        notification_service: 通知サービス
        animals: 動物データのリスト
    """
    try:
        result = await notification_service.process_new_animals(animals)
        logger.info(
            f"Background notification processing completed: "
            f"sent={result.sent_count}, failed={result.failed_count}"
        )
    except Exception as e:
        logger.error(f"Background notification processing failed: {e}")
