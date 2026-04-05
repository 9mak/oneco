"""
ArchiveService のテスト

アーカイブ処理のオーケストレーション機能をテストします。
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.database.models import Animal, AnimalArchive, Base


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
        await session.rollback()


@pytest_asyncio.fixture
async def animal_repository(async_session):
    """テスト用の AnimalRepository を作成"""
    from src.data_collector.infrastructure.database.repository import AnimalRepository

    return AnimalRepository(async_session)


@pytest_asyncio.fixture
async def archive_repository(async_session):
    """テスト用の ArchiveRepository を作成"""
    from src.data_collector.infrastructure.database.archive_repository import ArchiveRepository

    return ArchiveRepository(async_session)


@pytest_asyncio.fixture
def mock_image_storage_service():
    """モック ImageStorageService を作成"""
    mock = MagicMock()
    mock.move_to_archive = AsyncMock(return_value=[])
    return mock


@pytest_asyncio.fixture
async def archive_service(animal_repository, archive_repository, mock_image_storage_service):
    """テスト用の ArchiveService を作成"""
    from src.data_collector.services.archive_service import ArchiveService

    return ArchiveService(
        animal_repository=animal_repository,
        archive_repository=archive_repository,
        image_storage_service=mock_image_storage_service,
        retention_days=180,
    )


class TestArchiveServiceInitialization:
    """ArchiveService 初期化テスト"""

    @pytest.mark.asyncio
    async def test_initialization(
        self, animal_repository, archive_repository, mock_image_storage_service
    ):
        """ArchiveService が正しく初期化されるか"""
        from src.data_collector.services.archive_service import ArchiveService

        service = ArchiveService(
            animal_repository=animal_repository,
            archive_repository=archive_repository,
            image_storage_service=mock_image_storage_service,
            retention_days=90,
        )
        assert service.retention_days == 90
        assert service.batch_size == 1000  # デフォルト値

    @pytest.mark.asyncio
    async def test_initialization_with_defaults(
        self, animal_repository, archive_repository, mock_image_storage_service
    ):
        """ArchiveService がデフォルト値で初期化されるか"""
        from src.data_collector.services.archive_service import ArchiveService

        service = ArchiveService(
            animal_repository=animal_repository,
            archive_repository=archive_repository,
            image_storage_service=mock_image_storage_service,
        )
        assert service.retention_days == 180  # デフォルト
        assert service.batch_size == 1000  # デフォルト


class TestRunArchiveJob:
    """run_archive_job メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_run_archive_job_moves_old_animals(self, archive_service, async_session):
        """run_archive_job() が保持期間を超えた動物をアーカイブに移動するか"""
        # 200日前に譲渡された動物を挿入
        old_outcome_date = date.today() - timedelta(days=200)
        old_status_changed_at = datetime(
            old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
        )
        animal = Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/archive_test1",
            category="adoption",
            status="adopted",
            status_changed_at=old_status_changed_at,
            outcome_date=old_outcome_date,
            local_image_paths=["a1/b2/hash1.jpg"],
        )
        async_session.add(animal)
        await async_session.commit()
        await async_session.refresh(animal)

        result = await archive_service.run_archive_job()

        # 処理結果を確認
        assert result.processed_count == 1
        assert result.success_count == 1
        assert result.error_count == 0

        # アーカイブに移動されていることを確認
        from sqlalchemy import select

        archive_stmt = select(AnimalArchive).where(
            AnimalArchive.source_url == "https://example.com/archive_test1"
        )
        archive_result = await async_session.execute(archive_stmt)
        archived = archive_result.scalar_one_or_none()
        assert archived is not None
        assert archived.species == "犬"

        # 元のテーブルから削除されていることを確認
        animal_stmt = select(Animal).where(Animal.source_url == "https://example.com/archive_test1")
        animal_result = await async_session.execute(animal_stmt)
        assert animal_result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_run_archive_job_skips_recent_animals(self, archive_service, async_session):
        """run_archive_job() が保持期間内の動物をスキップするか"""
        # 100日前に譲渡された動物（まだ保持期間内）
        recent_outcome_date = date.today() - timedelta(days=100)
        recent_status_changed_at = datetime(
            recent_outcome_date.year, recent_outcome_date.month, recent_outcome_date.day, tzinfo=UTC
        )
        animal = Animal(
            species="猫",
            shelter_date=date(2025, 3, 1),
            location="高知県",
            source_url="https://example.com/recent_test",
            category="adoption",
            status="adopted",
            status_changed_at=recent_status_changed_at,
            outcome_date=recent_outcome_date,
        )
        async_session.add(animal)
        await async_session.commit()

        result = await archive_service.run_archive_job()

        assert result.processed_count == 0
        assert result.success_count == 0

    @pytest.mark.asyncio
    async def test_run_archive_job_moves_images(
        self, archive_service, async_session, mock_image_storage_service
    ):
        """run_archive_job() が画像ファイルも移動するか"""
        old_outcome_date = date.today() - timedelta(days=200)
        old_status_changed_at = datetime(
            old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
        )
        animal = Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/image_move_test",
            category="adoption",
            status="adopted",
            status_changed_at=old_status_changed_at,
            outcome_date=old_outcome_date,
            local_image_paths=["a1/b2/hash1.jpg", "c3/d4/hash2.png"],
        )
        async_session.add(animal)
        await async_session.commit()

        mock_image_storage_service.move_to_archive.return_value = [
            "archive/a1/b2/hash1.jpg",
            "archive/c3/d4/hash2.png",
        ]

        await archive_service.run_archive_job()

        # 画像移動が呼ばれたことを確認
        mock_image_storage_service.move_to_archive.assert_called_once()
        call_args = mock_image_storage_service.move_to_archive.call_args[0][0]
        assert "a1/b2/hash1.jpg" in call_args
        assert "c3/d4/hash2.png" in call_args

    @pytest.mark.asyncio
    async def test_run_archive_job_batch_processing(self, archive_service, async_session):
        """run_archive_job() がバッチ処理を正しく実行するか"""
        # アーカイブサービスのバッチサイズを小さく設定
        archive_service.batch_size = 2

        # 5件のアーカイブ対象動物を作成
        old_outcome_date = date.today() - timedelta(days=200)
        old_status_changed_at = datetime(
            old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
        )
        for i in range(5):
            animal = Animal(
                species="犬",
                shelter_date=date(2025, 1, 1),
                location="高知県",
                source_url=f"https://example.com/batch_test{i}",
                category="adoption",
                status="adopted",
                status_changed_at=old_status_changed_at,
                outcome_date=old_outcome_date,
            )
            async_session.add(animal)
        await async_session.commit()

        result = await archive_service.run_archive_job()

        # 5件全てが処理されたことを確認
        assert result.processed_count == 5
        assert result.success_count == 5

    @pytest.mark.asyncio
    async def test_run_archive_job_returns_result(self, archive_service, async_session):
        """run_archive_job() が ArchiveJobResult を返すか"""
        from src.data_collector.services.archive_service import ArchiveJobResult

        result = await archive_service.run_archive_job()

        assert isinstance(result, ArchiveJobResult)
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.started_at <= result.completed_at


class TestGetArchivableCount:
    """get_archivable_count メソッドのテスト"""

    @pytest.mark.asyncio
    async def test_get_archivable_count_returns_count(self, archive_service, async_session):
        """get_archivable_count() がアーカイブ対象件数を返すか"""
        # アーカイブ対象動物を3件作成
        old_outcome_date = date.today() - timedelta(days=200)
        old_status_changed_at = datetime(
            old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
        )
        for i in range(3):
            animal = Animal(
                species="犬",
                shelter_date=date(2025, 1, 1),
                location="高知県",
                source_url=f"https://example.com/count_test{i}",
                category="adoption",
                status="adopted",
                status_changed_at=old_status_changed_at,
                outcome_date=old_outcome_date,
            )
            async_session.add(animal)

        # 保持期間内の動物を1件作成
        recent_outcome_date = date.today() - timedelta(days=100)
        recent_status_changed_at = datetime(
            recent_outcome_date.year, recent_outcome_date.month, recent_outcome_date.day, tzinfo=UTC
        )
        recent_animal = Animal(
            species="猫",
            shelter_date=date(2025, 3, 1),
            location="高知県",
            source_url="https://example.com/recent_count",
            category="adoption",
            status="adopted",
            status_changed_at=recent_status_changed_at,
            outcome_date=recent_outcome_date,
        )
        async_session.add(recent_animal)
        await async_session.commit()

        count = await archive_service.get_archivable_count()

        assert count == 3


class TestErrorHandling:
    """エラーハンドリングのテスト"""

    @pytest.mark.asyncio
    async def test_run_archive_job_continues_on_error(
        self, archive_service, async_session, mock_image_storage_service
    ):
        """run_archive_job() がエラー発生時に次の動物へ継続するか"""
        # アーカイブ対象動物を2件作成（画像パスありでエラーを発生させる）
        old_outcome_date = date.today() - timedelta(days=200)
        old_status_changed_at = datetime(
            old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
        )
        for i in range(2):
            animal = Animal(
                species="犬",
                shelter_date=date(2025, 1, 1),
                location="高知県",
                source_url=f"https://example.com/error_test{i}",
                category="adoption",
                status="adopted",
                status_changed_at=old_status_changed_at,
                outcome_date=old_outcome_date,
                local_image_paths=[f"a{i}/b{i}/hash{i}.jpg"],  # 画像パスを設定
            )
            async_session.add(animal)
        await async_session.commit()

        # 1回目の呼び出しでエラー、2回目は成功
        mock_image_storage_service.move_to_archive.side_effect = [
            Exception("Image move failed"),
            [],
        ]
        # batch_size は大きくして1回で両方取得
        archive_service.batch_size = 100

        result = await archive_service.run_archive_job()

        # 2件処理、1件成功、1件エラー
        assert result.processed_count == 2
        assert result.success_count == 1
        assert result.error_count == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_run_archive_job_records_error_message(
        self, archive_service, async_session, mock_image_storage_service
    ):
        """run_archive_job() がエラーメッセージを記録するか"""
        old_outcome_date = date.today() - timedelta(days=200)
        old_status_changed_at = datetime(
            old_outcome_date.year, old_outcome_date.month, old_outcome_date.day, tzinfo=UTC
        )
        animal = Animal(
            species="犬",
            shelter_date=date(2025, 1, 1),
            location="高知県",
            source_url="https://example.com/error_msg_test",
            category="adoption",
            status="adopted",
            status_changed_at=old_status_changed_at,
            outcome_date=old_outcome_date,
            local_image_paths=["a1/b2/hash1.jpg"],  # 画像パスを設定してエラーを発生させる
        )
        async_session.add(animal)
        await async_session.commit()

        mock_image_storage_service.move_to_archive.side_effect = Exception("Test error message")

        result = await archive_service.run_archive_job()

        assert "Test error message" in result.errors[0]
