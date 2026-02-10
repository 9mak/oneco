"""
エンドツーエンドテスト

data-collector でデータ収集 → データベース永続化 → API取得の
一連のフローが正しく動作することを検証します。

要件:
- 2.1: データ永続化
- 3.1: データ取得API
- 3.2: ID指定取得
"""

import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import Mock, MagicMock
from pathlib import Path
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.data_collector.infrastructure.database.models import Animal, AnimalStatusHistory, Base
from src.data_collector.domain.models import AnimalStatus
from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.data_collector.infrastructure.api.app import create_app
from src.data_collector.infrastructure.api.dependencies import get_session
from src.data_collector.orchestration.collector_service import CollectorService, CollectionResult
from src.data_collector.domain.models import AnimalData
from src.data_collector.domain.diff_detector import DiffResult


@pytest_asyncio.fixture
async def async_engine():
    """テスト用の非同期エンジンを作成"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """テスト用の非同期セッションを作成"""
    async_session_maker = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture
def sample_animal_data_list():
    """サンプル AnimalData リストを作成"""
    return [
        AnimalData(
            species="犬",
            sex="男の子",
            age_months=24,
            color="茶色",
            size="中型",
            shelter_date=date(2026, 1, 5),
            location="高知県動物愛護センター",
            phone="088-123-4567",
            image_urls=["https://example.com/img1.jpg"],
            source_url="https://example-kochi.jp/animals/001",
            category="adoption"
        ),
        AnimalData(
            species="猫",
            sex="女の子",
            age_months=12,
            color="白",
            size="小型",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            phone="088-999-8888",
            image_urls=["https://example.com/img2.jpg"],
            source_url="https://example-kochi.jp/animals/002",
            category="adoption"
        ),
        AnimalData(
            species="犬",
            sex="女の子",
            age_months=36,
            color="黒",
            size="大型",
            shelter_date=date(2026, 1, 7),
            location="高知市",
            phone="088-111-2222",
            image_urls=[],
            source_url="https://example-kochi.jp/animals/003",
            category="adoption"
        ),
    ]


@pytest_asyncio.fixture
async def repository(async_session):
    """テスト用の AnimalRepository を作成"""
    return AnimalRepository(async_session)


@pytest_asyncio.fixture
async def test_app(async_session):
    """テスト用の FastAPI アプリケーションを作成"""
    app = create_app()

    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session

    return app


class TestE2EDataPersistenceFlow:
    """データ永続化フローのE2Eテスト"""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_via_repository(
        self, repository, sample_animal_data_list
    ):
        """Repository経由でデータを保存し、取得できることを確認"""
        # 1. データを保存
        for animal_data in sample_animal_data_list:
            await repository.save_animal(animal_data)

        # 2. 保存したデータを取得
        animals, total = await repository.list_animals()

        # 3. 検証
        assert total == 3
        assert len(animals) == 3

        # source_url で確認
        source_urls = [str(a.source_url) for a in animals]
        assert "https://example-kochi.jp/animals/001" in source_urls
        assert "https://example-kochi.jp/animals/002" in source_urls
        assert "https://example-kochi.jp/animals/003" in source_urls

    @pytest.mark.asyncio
    async def test_upsert_updates_existing_record(
        self, repository, sample_animal_data_list
    ):
        """同じsource_urlのデータが更新されることを確認（upsert）"""
        # 1. 最初のデータを保存
        original_data = sample_animal_data_list[0]
        await repository.save_animal(original_data)

        # 2. 同じsource_urlで異なる内容を保存
        updated_data = AnimalData(
            species="犬",
            sex="男の子",
            age_months=25,  # 変更
            color="茶色（濃い）",  # 変更
            size="中型",
            shelter_date=date(2026, 1, 5),
            location="高知県動物愛護センター",
            phone="088-123-4567",
            image_urls=["https://example.com/img1.jpg"],
            source_url="https://example-kochi.jp/animals/001",  # 同じURL
            category="adoption"
        )
        await repository.save_animal(updated_data)

        # 3. データを取得
        animals, total = await repository.list_animals()

        # 4. 検証 - 1件のみで、更新されていること
        assert total == 1
        assert animals[0].age_months == 25
        assert animals[0].color == "茶色（濃い）"


class TestE2EAPIFlow:
    """API経由のデータ取得フローのE2Eテスト"""

    @pytest.mark.asyncio
    async def test_e2e_save_and_get_via_api(
        self, repository, test_app, sample_animal_data_list
    ):
        """データを保存し、API経由で取得できることを確認"""
        # 1. Repositoryでデータを保存
        for animal_data in sample_animal_data_list:
            await repository.save_animal(animal_data)

        # 2. API経由でデータを取得
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/animals")

        # 3. 検証
        assert response.status_code == 200
        data = response.json()

        assert data["meta"]["total_count"] == 3
        assert len(data["items"]) == 3

        # 各アイテムに必要なフィールドがあることを確認
        for item in data["items"]:
            assert "id" in item
            assert "species" in item
            assert "source_url" in item
            assert "shelter_date" in item

    @pytest.mark.asyncio
    async def test_e2e_get_by_id_via_api(
        self, repository, test_app, sample_animal_data_list
    ):
        """保存したデータをID指定でAPI経由取得できることを確認"""
        # 1. データを保存
        saved_animal = await repository.save_animal(sample_animal_data_list[0])

        # 2. まずリストで取得してIDを確認
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            list_response = await client.get("/animals")
            items = list_response.json()["items"]

            # source_url で該当のIDを特定
            target_item = next(
                (item for item in items if item["source_url"] == str(saved_animal.source_url)),
                None
            )
            assert target_item is not None

            # 3. ID指定でデータを取得
            animal_id = target_item["id"]
            detail_response = await client.get(f"/animals/{animal_id}")

        # 4. 検証
        assert detail_response.status_code == 200
        data = detail_response.json()

        assert data["id"] == animal_id
        assert data["species"] == "犬"
        assert data["source_url"] == "https://example-kochi.jp/animals/001"

    @pytest.mark.asyncio
    async def test_e2e_filter_via_api(
        self, repository, test_app, sample_animal_data_list
    ):
        """保存したデータをフィルタリングしてAPI経由取得できることを確認"""
        # 1. データを保存
        for animal_data in sample_animal_data_list:
            await repository.save_animal(animal_data)

        # 2. API経由でフィルタリングしてデータを取得
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            # 犬のみを取得
            response = await client.get("/animals?species=犬")

        # 3. 検証
        assert response.status_code == 200
        data = response.json()

        assert data["meta"]["total_count"] == 2
        assert all(item["species"] == "犬" for item in data["items"])

    @pytest.mark.asyncio
    async def test_e2e_pagination_via_api(
        self, repository, test_app, sample_animal_data_list
    ):
        """ページネーションがAPI経由で正しく動作することを確認"""
        # 1. データを保存
        for animal_data in sample_animal_data_list:
            await repository.save_animal(animal_data)

        # 2. API経由でページネーションしてデータを取得
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            # 1件ずつ取得
            response = await client.get("/animals?limit=1&offset=0")

        # 3. 検証
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 1
        assert data["meta"]["total_count"] == 3
        assert data["meta"]["has_next"] is True
        assert data["meta"]["current_page"] == 1
        assert data["meta"]["total_pages"] == 3


class TestE2ECollectorServiceFlow:
    """CollectorService経由のデータ収集フローのE2Eテスト（モック使用）"""

    @pytest.fixture
    def mock_adapter(self, sample_animal_data_list):
        """モック MunicipalityAdapter"""
        adapter = Mock()
        adapter.prefecture_code = "39"
        adapter.municipality_name = "高知県"

        # URL-カテゴリのタプルリストを返す
        adapter.fetch_animal_list.return_value = [
            ("https://example-kochi.jp/animals/001", "adoption"),
            ("https://example-kochi.jp/animals/002", "adoption"),
            ("https://example-kochi.jp/animals/003", "adoption"),
        ]

        # 詳細データを返す
        adapter.extract_animal_details.return_value = Mock()

        # normalize を設定（順番に呼ばれる）
        adapter.normalize.side_effect = sample_animal_data_list

        return adapter

    @pytest.fixture
    def mock_diff_detector(self, sample_animal_data_list):
        """モック DiffDetector"""
        detector = Mock()
        detector.detect_diff.return_value = DiffResult(
            new=sample_animal_data_list,
            updated=[],
            deleted_candidates=[]
        )
        return detector

    @pytest.fixture
    def mock_output_writer(self, tmp_path):
        """モック OutputWriter"""
        writer = Mock()
        writer.write_output.return_value = tmp_path / "animals.json"
        return writer

    @pytest.fixture
    def mock_snapshot_store(self):
        """モック SnapshotStore"""
        store = Mock()
        store.load_snapshot.return_value = []
        return store

    @pytest.fixture
    def mock_notification_client(self):
        """モック NotificationClient"""
        return Mock()

    @pytest.mark.asyncio
    async def test_e2e_collector_saves_to_repository_and_api_retrieves(
        self,
        tmp_path,
        repository,
        test_app,
        mock_adapter,
        mock_diff_detector,
        mock_output_writer,
        mock_snapshot_store,
        mock_notification_client,
        sample_animal_data_list,
    ):
        """CollectorService で収集したデータが Repository に保存され、
        API経由で取得できることを確認（モック使用の統合テスト）"""

        # モックの Repository を設定
        # save_animal が呼ばれたら実際の Repository に保存する
        mock_repository = Mock()

        async def save_to_real_repository(animal_data):
            return await repository.save_animal(animal_data)

        mock_repository.save_animal = MagicMock(side_effect=save_to_real_repository)

        # CollectorService を作成
        service = CollectorService(
            adapter=mock_adapter,
            diff_detector=mock_diff_detector,
            output_writer=mock_output_writer,
            notification_client=mock_notification_client,
            snapshot_store=mock_snapshot_store,
            repository=mock_repository,
        )
        service.LOCK_FILE = tmp_path / ".collector.lock"

        # 収集を実行
        result = service.run_collection()

        # 収集成功を確認
        assert result.success
        assert result.total_collected == 3

        # Repository の save_animal が3回呼ばれたことを確認
        assert mock_repository.save_animal.call_count == 3

        # API 経由でデータを取得
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.get("/animals")

        # 検証
        assert response.status_code == 200
        data = response.json()
        assert data["meta"]["total_count"] == 3

        # source_url が正しく保存されていることを確認
        source_urls = [item["source_url"] for item in data["items"]]
        assert "https://example-kochi.jp/animals/001" in source_urls
        assert "https://example-kochi.jp/animals/002" in source_urls
        assert "https://example-kochi.jp/animals/003" in source_urls


class TestE2EStatusManagementFlow:
    """ステータス管理フローのE2Eテスト"""

    @pytest.mark.asyncio
    async def test_e2e_status_update_via_api(
        self, repository, test_app, sample_animal_data_list
    ):
        """ステータス更新がAPI経由で正しく動作することを確認"""
        # 1. データを保存
        saved_animal = await repository.save_animal(sample_animal_data_list[0])

        # 2. リストで取得してIDを確認
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            list_response = await client.get("/animals")
            items = list_response.json()["items"]
            target_item = next(
                (item for item in items if item["source_url"] == str(saved_animal.source_url)),
                None
            )
            animal_id = target_item["id"]

            # 3. ステータスを更新
            update_response = await client.patch(
                f"/animals/{animal_id}/status",
                json={"status": "adopted"}
            )

        # 4. 検証
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["success"] is True
        assert data["animal"]["status"] == "adopted"

    @pytest.mark.asyncio
    async def test_e2e_status_history_recorded(
        self, repository, test_app, async_session, sample_animal_data_list
    ):
        """ステータス変更履歴が記録されることを確認"""
        # 1. データを保存
        saved_animal = await repository.save_animal(sample_animal_data_list[0])

        # 2. リストで取得してIDを確認
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            list_response = await client.get("/animals")
            items = list_response.json()["items"]
            target_item = next(
                (item for item in items if item["source_url"] == str(saved_animal.source_url)),
                None
            )
            animal_id = target_item["id"]

            # 3. ステータスを複数回更新
            await client.patch(
                f"/animals/{animal_id}/status",
                json={"status": "adopted"}
            )
            await client.patch(
                f"/animals/{animal_id}/status",
                json={"status": "returned"}
            )

        # 4. 履歴が記録されていることを確認
        from sqlalchemy import select, func
        stmt = select(func.count()).select_from(AnimalStatusHistory).where(
            AnimalStatusHistory.animal_id == animal_id
        )
        result = await async_session.execute(stmt)
        count = result.scalar()

        assert count == 2

    @pytest.mark.asyncio
    async def test_e2e_status_filter_via_api(
        self, repository, test_app, sample_animal_data_list
    ):
        """ステータスフィルタリングがAPI経由で正しく動作することを確認"""
        # 1. データを保存
        for animal_data in sample_animal_data_list:
            await repository.save_animal(animal_data)

        # 2. リストで取得してIDを確認し、一部をステータス変更
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            list_response = await client.get("/animals")
            items = list_response.json()["items"]

            # 最初の動物を adopted に変更
            await client.patch(
                f"/animals/{items[0]['id']}/status",
                json={"status": "adopted"}
            )

            # 3. ステータスでフィルタリング
            sheltered_response = await client.get("/animals?status=sheltered")
            adopted_response = await client.get("/animals?status=adopted")

        # 4. 検証
        sheltered_data = sheltered_response.json()
        adopted_data = adopted_response.json()

        assert sheltered_data["meta"]["total_count"] == 2
        assert adopted_data["meta"]["total_count"] == 1
        assert all(item["status"] == "sheltered" for item in sheltered_data["items"])
        assert all(item["status"] == "adopted" for item in adopted_data["items"])

    @pytest.mark.asyncio
    async def test_e2e_invalid_status_transition_rejected(
        self, repository, test_app, sample_animal_data_list
    ):
        """不正なステータス遷移がAPI経由で拒否されることを確認"""
        # 1. データを保存
        saved_animal = await repository.save_animal(sample_animal_data_list[0])

        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            # 2. リストで取得してIDを確認
            list_response = await client.get("/animals")
            items = list_response.json()["items"]
            target_item = next(
                (item for item in items if item["source_url"] == str(saved_animal.source_url)),
                None
            )
            animal_id = target_item["id"]

            # 3. deceased に変更
            await client.patch(
                f"/animals/{animal_id}/status",
                json={"status": "deceased"}
            )

            # 4. deceased から sheltered への不正な遷移を試行
            invalid_response = await client.patch(
                f"/animals/{animal_id}/status",
                json={"status": "sheltered"}
            )

        # 5. 検証 - 422 エラーが返される
        assert invalid_response.status_code == 422
