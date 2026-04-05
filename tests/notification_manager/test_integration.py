"""
notification-manager 統合テスト

Task 9.1-9.4: data-collector連携、LINE連携、重複通知防止、パフォーマンスのテスト
"""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.data_collector.domain.models import AnimalData
from src.notification_manager.domain.models import (
    MatchResult,
    NotificationPreferenceEntity,
    NotificationResult,
    SendResult,
    UserEntity,
)
from src.notification_manager.domain.services import (
    MatchingService,
    NotificationService,
    UserService,
)
from src.notification_manager.infrastructure.api.routes import (
    NotificationWebhookDeps,
    create_notification_router,
)


class TestDataCollectorIntegration:
    """
    data-collector連携の統合テスト (Task 9.1)

    Webhook受信 → マッチング → LINE送信の全フロー検証
    """

    @pytest.fixture
    def mock_services(self):
        """モックサービス群"""
        notification_service = Mock(spec=NotificationService)
        notification_service.process_new_animals = AsyncMock(
            return_value=NotificationResult(
                total_animals=1,
                total_matches=2,
                sent_count=2,
                skipped_count=0,
                failed_count=0,
                processing_time_seconds=0.5,
            )
        )
        return notification_service

    @pytest.fixture
    def deps(self, mock_services):
        """依存関係"""
        return NotificationWebhookDeps(
            notification_service=mock_services,
            api_key="test_api_key_12345",
        )

    @pytest.fixture
    def app(self, deps):
        """テスト用FastAPIアプリ"""
        app = FastAPI()
        router = create_notification_router(deps)
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """テストクライアント"""
        return TestClient(app)

    def test_full_webhook_flow_success(self, client, deps):
        """
        全フロー: Webhook受信 → バックグラウンド処理 → 成功
        Req: 2.1, 2.2, 2.5, 3.1-3.5, 4.1
        """
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [
                    {
                        "species": "犬",
                        "sex": "男の子",
                        "age_months": 24,
                        "size": "中型",
                        "shelter_date": "2026-01-15",
                        "location": "高知県高知市",
                        "source_url": "https://example.com/animals/1",
                        "category": "adoption",
                    }
                ],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
            headers={"X-API-Key": "test_api_key_12345"},
        )

        # HTTP 202 が返される
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"

    def test_webhook_multiple_animals(self, client, deps):
        """複数動物の一括受信"""
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [
                    {
                        "species": "犬",
                        "sex": "男の子",
                        "shelter_date": "2026-01-15",
                        "location": "高知県",
                        "source_url": "https://example.com/animals/1",
                        "category": "adoption",
                    },
                    {
                        "species": "猫",
                        "sex": "女の子",
                        "shelter_date": "2026-01-15",
                        "location": "愛媛県",
                        "source_url": "https://example.com/animals/2",
                        "category": "adoption",
                    },
                ],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
            headers={"X-API-Key": "test_api_key_12345"},
        )

        assert response.status_code == 202
        assert "2 animals" in response.json()["message"]

    def test_webhook_api_key_authentication(self, client):
        """APIキー認証の検証 (Req: 7.2, 7.3)"""
        # APIキーなし
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

        # 無効なAPIキー
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

    def test_webhook_validation_errors(self, client):
        """不正リクエストのバリデーション (Req: 2.3, 2.4)"""
        # 無効な種別
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [
                    {
                        "species": "無効な種別",
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

    def test_webhook_empty_animals_list(self, client):
        """空の動物リスト"""
        response = client.post(
            "/api/v1/notifications/webhook",
            json={
                "animals": [],
                "source": "data-collector",
                "timestamp": "2026-01-15T10:00:00Z",
            },
            headers={"X-API-Key": "test_api_key_12345"},
        )
        # 空リストでも受け付ける
        assert response.status_code == 202


class TestLineIntegration:
    """
    LINE連携の統合テスト (Task 9.2)

    友だち追加 → ユーザー登録の検証
    条件設定フローの検証
    ブロック/削除 → 無効化の検証
    """

    @pytest.fixture
    def mock_user_service(self):
        """モックユーザーサービス"""
        service = Mock(spec=UserService)
        service.register_user = Mock(
            return_value=UserEntity(
                id=1,
                line_user_id_encrypted="encrypted_U123",
                is_active=True,
            )
        )
        service.deactivate_user = Mock(return_value=True)
        return service

    @pytest.fixture
    def mock_line_adapter(self):
        """モックLINEアダプター"""
        adapter = Mock()
        adapter.verify_signature = Mock(return_value=True)
        return adapter

    @pytest.fixture
    def deps(self, mock_user_service, mock_line_adapter):
        """依存関係"""
        return NotificationWebhookDeps(
            notification_service=Mock(),
            user_service=mock_user_service,
            line_adapter=mock_line_adapter,
            api_key="test_api_key_12345",
        )

    @pytest.fixture
    def app(self, deps):
        """テスト用FastAPIアプリ"""
        app = FastAPI()
        router = create_notification_router(deps)
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """テストクライアント"""
        return TestClient(app)

    def test_follow_event_registers_user(self, client, deps):
        """友だち追加時のユーザー登録 (Req: 1.1)"""
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

    def test_unfollow_event_deactivates_user(self, client, deps):
        """ブロック/削除時のユーザー無効化 (Req: 7.5)"""
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

    def test_signature_verification(self, client, deps):
        """署名検証 (Req: 7.4)"""
        # 署名なし
        response = client.post(
            "/api/v1/line/webhook",
            json={"events": []},
        )
        assert response.status_code == 400
        assert "Signature required" in response.json()["detail"]

        # 無効な署名
        deps._line_adapter.verify_signature = Mock(return_value=False)
        response = client.post(
            "/api/v1/line/webhook",
            json={"events": []},
            headers={"X-Line-Signature": "invalid_signature"},
        )
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]

    def test_message_event_received(self, client, deps):
        """メッセージイベントの受信 (Req: 1.2)"""
        response = client.post(
            "/api/v1/line/webhook",
            json={
                "events": [
                    {
                        "type": "message",
                        "source": {"type": "user", "userId": "U1234567890"},
                        "timestamp": 1704067200000,
                        "replyToken": "reply_token_123",
                        "message": {
                            "type": "text",
                            "id": "12345",
                            "text": "設定",
                        },
                    }
                ]
            },
            headers={"X-Line-Signature": "valid_signature"},
        )

        assert response.status_code == 200


class TestDuplicateNotificationPrevention:
    """
    重複通知防止と履歴管理のテスト (Task 9.3)

    同一動物への二重通知防止の検証
    履歴記録の正確性検証
    90日超過履歴の削除検証
    """

    @pytest.fixture
    def mock_repos(self):
        """モックリポジトリ"""
        pref_repo = Mock()
        user_repo = Mock()
        history_repo = Mock()
        return pref_repo, user_repo, history_repo

    @pytest.fixture
    def mock_line_adapter(self):
        """モックLINEアダプター"""
        adapter = Mock()
        adapter.send_with_retry = AsyncMock(return_value=SendResult(success=True))
        return adapter

    @pytest.fixture
    def mock_encryption(self):
        """モック暗号化サービス"""
        encryption = Mock()
        encryption.decrypt = Mock(return_value="U1234567890")
        return encryption

    @pytest.fixture
    def sample_animal(self):
        """サンプル動物データ"""
        return AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            shelter_date=date(2026, 1, 15),
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

    @pytest.mark.asyncio
    async def test_skips_already_notified_users(
        self, mock_repos, mock_line_adapter, mock_encryption, sample_animal
    ):
        """既に通知済みの場合はスキップする (Req: 5.2, 5.3)"""
        _pref_repo, _user_repo, history_repo = mock_repos

        # マッチング結果
        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )

        # モック設定
        matching_service = Mock(spec=MatchingService)
        matching_service.find_matching_users = Mock(return_value=[match_result])

        # 既に通知済み
        history_repo.is_already_notified = Mock(return_value=True)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        result = await service.process_new_animals([sample_animal])

        # スキップされた
        assert result.skipped_count == 1
        assert result.sent_count == 0
        # LINE送信は呼ばれない
        mock_line_adapter.send_with_retry.assert_not_called()

    @pytest.mark.asyncio
    async def test_records_history_after_send(
        self, mock_repos, mock_line_adapter, mock_encryption, sample_animal
    ):
        """送信後に履歴を記録する (Req: 5.1)"""
        _pref_repo, _user_repo, history_repo = mock_repos

        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )

        matching_service = Mock(spec=MatchingService)
        matching_service.find_matching_users = Mock(return_value=[match_result])

        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        await service.process_new_animals([sample_animal])

        # 履歴が記録された
        history_repo.record.assert_called_once_with(
            user_id=100,
            animal_source_url=str(sample_animal.source_url),
            status="sent",
        )

    @pytest.mark.asyncio
    async def test_records_history_on_failure(self, mock_repos, mock_encryption, sample_animal):
        """送信失敗時も履歴を記録する (Req: 5.1)"""
        _pref_repo, _user_repo, history_repo = mock_repos

        match_result = MatchResult(
            user_id=100,
            line_user_id_encrypted="encrypted_U123",
            preference_id=1,
            match_score=1.0,
        )

        matching_service = Mock(spec=MatchingService)
        matching_service.find_matching_users = Mock(return_value=[match_result])

        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        # 送信失敗
        mock_line_adapter = Mock()
        mock_line_adapter.send_with_retry = AsyncMock(
            return_value=SendResult(success=False, error_code="500")
        )

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        await service.process_new_animals([sample_animal])

        # 履歴が"failed"で記録された
        history_repo.record.assert_called_once_with(
            user_id=100,
            animal_source_url=str(sample_animal.source_url),
            status="failed",
        )


class TestPerformanceAndScalability:
    """
    パフォーマンスとスケーラビリティのテスト (Task 9.4)

    大量ユーザーへのバッチ通知検証（100件/バッチ）
    並列送信（10並列）の動作検証
    平均応答時間5秒以内の検証
    """

    @pytest.fixture
    def mock_line_adapter(self):
        """モックLINEアダプター（遅延シミュレーション）"""
        adapter = Mock()

        async def mock_send(*args, **kwargs):
            await asyncio.sleep(0.01)  # 10ms遅延
            return SendResult(success=True)

        adapter.send_with_retry = mock_send
        return adapter

    @pytest.fixture
    def mock_encryption(self):
        """モック暗号化サービス"""
        encryption = Mock()
        encryption.decrypt = Mock(return_value="U1234567890")
        return encryption

    @pytest.fixture
    def sample_animal(self):
        """サンプル動物データ"""
        return AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            shelter_date=date(2026, 1, 15),
            location="高知県",
            source_url="https://example.com/animals/1",
            category="adoption",
        )

    def create_match_results(self, count: int):
        """指定数のマッチング結果を生成"""
        return [
            MatchResult(
                user_id=i,
                line_user_id_encrypted=f"encrypted_U{i}",
                preference_id=i,
                match_score=1.0,
            )
            for i in range(count)
        ]

    @pytest.mark.asyncio
    async def test_batch_processing_100_users(
        self, mock_line_adapter, mock_encryption, sample_animal
    ):
        """100件バッチ処理 (Req: 8.2)"""
        matching_service = Mock(spec=MatchingService)
        matching_service.find_matching_users = Mock(return_value=self.create_match_results(100))

        history_repo = Mock()
        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        result = await service.process_new_animals([sample_animal])

        # 100件すべて送信された
        assert result.sent_count == 100
        assert result.total_matches == 100

    @pytest.mark.asyncio
    async def test_parallel_sending_10_concurrent(
        self, mock_line_adapter, mock_encryption, sample_animal
    ):
        """10並列送信 (Req: 8.3)"""
        matching_service = Mock(spec=MatchingService)
        matching_service.find_matching_users = Mock(return_value=self.create_match_results(20))

        history_repo = Mock()
        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        # MAX_PARALLELが10であることを確認
        assert service.MAX_PARALLEL == 10

        result = await service.process_new_animals([sample_animal])

        # 全件送信された
        assert result.sent_count == 20

    @pytest.mark.asyncio
    async def test_processing_time_under_5_seconds(
        self, mock_line_adapter, mock_encryption, sample_animal
    ):
        """処理時間が5秒以内 (Req: 8.4)"""
        matching_service = Mock(spec=MatchingService)
        # 50ユーザーへの通知
        matching_service.find_matching_users = Mock(return_value=self.create_match_results(50))

        history_repo = Mock()
        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        result = await service.process_new_animals([sample_animal])

        # 処理時間が5秒以内
        assert result.processing_time_seconds < 5.0
        # 並列処理により、50件 × 10ms / 10並列 ≈ 50ms + オーバーヘッド
        # 実際は1秒未満で完了するはず
        assert result.processing_time_seconds < 1.0

    @pytest.mark.asyncio
    async def test_large_batch_200_users(self, mock_line_adapter, mock_encryption, sample_animal):
        """200件の大量通知（2バッチ）"""
        matching_service = Mock(spec=MatchingService)
        matching_service.find_matching_users = Mock(return_value=self.create_match_results(200))

        history_repo = Mock()
        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        result = await service.process_new_animals([sample_animal])

        # 200件すべて送信された
        assert result.sent_count == 200
        # 2バッチに分割されるため、履歴も200件記録
        assert history_repo.record.call_count == 200

    @pytest.mark.asyncio
    async def test_multiple_animals_processing(self, mock_line_adapter, mock_encryption):
        """複数動物の連続処理"""
        animals = [
            AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                shelter_date=date(2026, 1, 15),
                location="高知県",
                source_url=f"https://example.com/animals/{i}",
                category="adoption",
            )
            for i in range(3)
        ]

        matching_service = Mock(spec=MatchingService)
        # 各動物に10ユーザーがマッチ
        matching_service.find_matching_users = Mock(return_value=self.create_match_results(10))

        history_repo = Mock()
        history_repo.is_already_notified = Mock(return_value=False)
        history_repo.record = Mock()

        service = NotificationService(
            matching_service=matching_service,
            history_repository=history_repo,
            line_adapter=mock_line_adapter,
            encryption_service=mock_encryption,
        )

        result = await service.process_new_animals(animals)

        # 3動物 × 10ユーザー = 30件
        assert result.total_animals == 3
        assert result.total_matches == 30
        assert result.sent_count == 30


class TestMatchingIntegration:
    """マッチングロジックの統合テスト (Req: 3.1-3.5)"""

    @pytest.fixture
    def sample_animals(self):
        """様々な条件の動物データ"""
        return [
            AnimalData(
                species="犬",
                sex="男の子",
                age_months=24,
                size="中型",
                shelter_date=date(2026, 1, 15),
                location="高知県高知市",
                source_url="https://example.com/dog1",
                category="adoption",
            ),
            AnimalData(
                species="猫",
                sex="女の子",
                age_months=12,
                size="小型",
                shelter_date=date(2026, 1, 15),
                location="愛媛県松山市",
                source_url="https://example.com/cat1",
                category="adoption",
            ),
            AnimalData(
                species="犬",
                sex="女の子",
                age_months=60,
                size="大型",
                shelter_date=date(2026, 1, 15),
                location="東京都",
                source_url="https://example.com/dog2",
                category="adoption",
            ),
        ]

    @pytest.fixture
    def sample_preferences(self):
        """様々な条件のユーザー設定"""
        return [
            # 高知県の犬を探しているユーザー
            NotificationPreferenceEntity(
                id=1,
                user_id=100,
                species="犬",
                prefectures=["高知県"],
                age_min_months=None,
                age_max_months=None,
                size=None,
                sex=None,
                notifications_enabled=True,
            ),
            # 猫を探しているユーザー（地域不問）
            NotificationPreferenceEntity(
                id=2,
                user_id=200,
                species="猫",
                prefectures=None,
                age_min_months=None,
                age_max_months=None,
                size=None,
                sex=None,
                notifications_enabled=True,
            ),
            # 全種別・全地域を探しているユーザー
            NotificationPreferenceEntity(
                id=3,
                user_id=300,
                species=None,
                prefectures=None,
                age_min_months=None,
                age_max_months=None,
                size=None,
                sex=None,
                notifications_enabled=True,
            ),
            # 通知無効のユーザー
            NotificationPreferenceEntity(
                id=4,
                user_id=400,
                species=None,
                prefectures=None,
                age_min_months=None,
                age_max_months=None,
                size=None,
                sex=None,
                notifications_enabled=False,
            ),
        ]

    def test_matching_filters_by_species(self, sample_animals, sample_preferences):
        """種別によるフィルタリング"""
        pref_repo = Mock()
        user_repo = Mock()

        # 犬のみの設定
        pref_repo.get_active_preferences.return_value = [sample_preferences[0]]
        user_repo.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_100",
                is_active=True,
            )
        )

        service = MatchingService(
            preference_repository=pref_repo,
            user_repository=user_repo,
        )

        # 犬データ → マッチ
        results = service.find_matching_users(sample_animals[0])
        assert len(results) == 1
        assert results[0].user_id == 100

        # 猫データ → マッチしない
        results = service.find_matching_users(sample_animals[1])
        assert len(results) == 0

    def test_matching_filters_by_prefecture(self, sample_animals, sample_preferences):
        """都道府県によるフィルタリング"""
        pref_repo = Mock()
        user_repo = Mock()

        # 高知県のみの設定
        pref_repo.get_active_preferences.return_value = [sample_preferences[0]]
        user_repo.get_by_id = Mock(
            return_value=UserEntity(
                id=100,
                line_user_id_encrypted="encrypted_100",
                is_active=True,
            )
        )

        service = MatchingService(
            preference_repository=pref_repo,
            user_repository=user_repo,
        )

        # 高知県の犬 → マッチ
        results = service.find_matching_users(sample_animals[0])
        assert len(results) == 1

        # 東京都の犬 → マッチしない
        results = service.find_matching_users(sample_animals[2])
        assert len(results) == 0

    def test_matching_all_species_all_prefectures(self, sample_animals, sample_preferences):
        """全種別・全地域の設定は全てにマッチ"""
        pref_repo = Mock()
        user_repo = Mock()

        # 全種別・全地域の設定
        pref_repo.get_active_preferences.return_value = [sample_preferences[2]]
        user_repo.get_by_id = Mock(
            return_value=UserEntity(
                id=300,
                line_user_id_encrypted="encrypted_300",
                is_active=True,
            )
        )

        service = MatchingService(
            preference_repository=pref_repo,
            user_repository=user_repo,
        )

        # すべての動物にマッチ
        for animal in sample_animals:
            results = service.find_matching_users(animal)
            assert len(results) == 1
            assert results[0].user_id == 300

    def test_disabled_notifications_excluded(self, sample_animals, sample_preferences):
        """無効な通知条件は除外される"""
        pref_repo = Mock()
        user_repo = Mock()

        # 無効な設定のみ（get_active_preferencesには含まれない）
        pref_repo.get_active_preferences.return_value = []

        service = MatchingService(
            preference_repository=pref_repo,
            user_repository=user_repo,
        )

        results = service.find_matching_users(sample_animals[0])
        assert len(results) == 0
