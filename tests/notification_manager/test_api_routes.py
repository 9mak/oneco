"""
notification-manager API層のテスト

Task 6.1-6.3: Webhookエンドポイント、ヘルスチェックのテスト
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import date, datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.notification_manager.infrastructure.api.routes import (
    create_notification_router,
    NotificationWebhookDeps,
)
from src.notification_manager.infrastructure.api.schemas import (
    NewAnimalWebhookRequest,
    HealthResponse,
    AnimalDataSchema,
)
from src.notification_manager.domain.models import NotificationResult


class TestNotificationWebhook:
    """data-collector Webhookエンドポイントのテスト (Task 6.1)"""

    @pytest.fixture
    def deps(self):
        """依存関係"""
        return NotificationWebhookDeps(
            notification_service=Mock(),
            api_key="test_api_key_12345",
        )

    @pytest.fixture
    def app(self, deps):
        """テスト用FastAPIアプリ"""
        app = FastAPI()
        router = create_notification_router(deps)
        app.include_router(router)
        app.state.deps = deps
        return app

    @pytest.fixture
    def client(self, app):
        """テストクライアント"""
        return TestClient(app)

    def test_webhook_success(self, client, deps):
        """Webhookリクエストが成功する"""
        # モック設定
        deps._notification_service.process_new_animals = AsyncMock(
            return_value=NotificationResult(
                total_animals=1,
                total_matches=2,
                sent_count=2,
                skipped_count=0,
                failed_count=0,
                processing_time_seconds=0.5,
            )
        )

        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [
                    {
                        "species": "犬",
                        "sex": "男の子",
                        "age_months": 24,
                        "shelter_date": "2026-01-15",
                        "location": "高知県",
                        "source_url": "https://example.com/animals/1",
                        "category": "adoption",
                    }
                ],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
            headers={"X-API-Key": "test_api_key_12345"},
        )

        assert response.status_code == 202

    def test_webhook_missing_api_key(self, client):
        """APIキーがない場合は401エラー"""
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
        )

        assert response.status_code == 401
        assert "API key required" in response.json()["detail"]

    def test_webhook_invalid_api_key(self, client):
        """無効なAPIキーの場合は401エラー"""
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
            headers={"X-API-Key": "invalid_key"},
        )

        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_webhook_validation_error(self, client):
        """リクエストバリデーションエラー"""
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [
                    {
                        "species": "無効な種別",  # バリデーションエラー
                        "shelter_date": "2026-01-15",
                        "location": "高知県",
                        "source_url": "https://example.com/animals/1",
                        "category": "adoption",
                    }
                ],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
            headers={"X-API-Key": "test_api_key_12345"},
        )

        assert response.status_code == 422


class TestLineWebhook:
    """LINE Webhookエンドポイントのテスト (Task 6.2)"""

    @pytest.fixture
    def deps(self):
        """依存関係"""
        return NotificationWebhookDeps(
            notification_service=Mock(),
            user_service=Mock(),
            line_adapter=Mock(),
            api_key="test_api_key_12345",
        )

    @pytest.fixture
    def app(self, deps):
        """テスト用FastAPIアプリ"""
        app = FastAPI()
        router = create_notification_router(deps)
        app.include_router(router)
        app.state.deps = deps
        return app

    @pytest.fixture
    def client(self, app):
        """テストクライアント"""
        return TestClient(app)

    def test_line_webhook_follow_event(self, client, deps):
        """友だち追加イベントの処理"""
        # モック設定
        deps._line_adapter.verify_signature = Mock(return_value=True)
        deps._user_service.register_user = Mock()

        response = client.post(
            "/api/v1/line/webhook",
            json={
                "events": [
                    {
                        "type": "follow",
                        "source": {"type": "user", "userId": "U1234567890"},
                        "timestamp": 1704067200000,
                        "replyToken": "reply_token_123",
                    }
                ]
            },
            headers={"X-Line-Signature": "valid_signature"},
        )

        assert response.status_code == 200

    def test_line_webhook_unfollow_event(self, client, deps):
        """ブロック/削除イベントの処理"""
        deps._line_adapter.verify_signature = Mock(return_value=True)
        deps._user_service.deactivate_user = Mock()

        response = client.post(
            "/api/v1/line/webhook",
            json={
                "events": [
                    {
                        "type": "unfollow",
                        "source": {"type": "user", "userId": "U1234567890"},
                        "timestamp": 1704067200000,
                    }
                ]
            },
            headers={"X-Line-Signature": "valid_signature"},
        )

        assert response.status_code == 200

    def test_line_webhook_invalid_signature(self, client, deps):
        """署名検証失敗時は400エラー"""
        deps._line_adapter.verify_signature = Mock(return_value=False)

        response = client.post(
            "/api/v1/line/webhook",
            json={"events": []},
            headers={"X-Line-Signature": "invalid_signature"},
        )

        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]

    def test_line_webhook_missing_signature(self, client):
        """署名がない場合は400エラー"""
        response = client.post(
            "/api/v1/line/webhook",
            json={"events": []},
        )

        assert response.status_code == 400
        assert "Signature required" in response.json()["detail"]


class TestHealthCheck:
    """ヘルスチェックエンドポイントのテスト (Task 6.3)"""

    @pytest.fixture
    def deps(self):
        """依存関係"""
        return NotificationWebhookDeps(
            notification_service=Mock(),
            api_key="test_api_key_12345",
            db_check_func=Mock(return_value=True),
            line_api_check_func=Mock(return_value=True),
        )

    @pytest.fixture
    def app(self, deps):
        """テスト用FastAPIアプリ"""
        app = FastAPI()
        router = create_notification_router(deps)
        app.include_router(router)
        app.state.deps = deps
        return app

    @pytest.fixture
    def client(self, app):
        """テストクライアント"""
        return TestClient(app)

    def test_health_check_healthy(self, client, deps):
        """すべて正常な場合はhealthy"""
        deps._db_check_func = Mock(return_value=True)
        deps._line_api_check_func = Mock(return_value=True)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] is True
        assert data["line_api"] is True

    def test_health_check_degraded(self, client, deps):
        """LINE APIのみ異常の場合はdegraded"""
        deps._db_check_func = Mock(return_value=True)
        deps._line_api_check_func = Mock(return_value=False)

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] is True
        assert data["line_api"] is False

    def test_health_check_unhealthy(self, client, deps):
        """DBが異常の場合はunhealthy"""
        deps._db_check_func = Mock(return_value=False)
        deps._line_api_check_func = Mock(return_value=True)

        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] is False


class TestAnimalDataSchema:
    """AnimalDataSchemaのテスト"""

    def test_valid_animal_data(self):
        """有効な動物データ"""
        data = AnimalDataSchema(
            species="犬",
            sex="男の子",
            age_months=24,
            shelter_date=date(2026, 1, 15),
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )
        assert data.species == "犬"
        assert data.sex == "男の子"

    def test_invalid_species(self):
        """無効な種別"""
        with pytest.raises(ValueError):
            AnimalDataSchema(
                species="無効",
                shelter_date=date(2026, 1, 15),
                location="高知県",
                source_url="https://example.com/animals/1",
                category="adoption",
            )

    def test_invalid_category(self):
        """無効なカテゴリ"""
        with pytest.raises(ValueError):
            AnimalDataSchema(
                species="犬",
                shelter_date=date(2026, 1, 15),
                location="高知県",
                source_url="https://example.com/animals/1",
                category="invalid",
            )
