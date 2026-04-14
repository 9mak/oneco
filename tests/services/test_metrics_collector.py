"""
AnimalMetricsCollector テスト

メトリクス収集機能とアラート機能をテストします。
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.database.models import Animal, Base
from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.data_collector.services.metrics_collector import (
    AlertManager,
    AnimalMetrics,
    AnimalMetricsCollector,
    AuditLogger,
)


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
async def populated_session(async_session):
    """テストデータが投入されたセッションを返す"""
    animals = [
        Animal(
            species="犬",
            sex="男の子",
            shelter_date=date(2026, 1, 5),
            location="高知県",
            source_url="https://example.com/animal/1",
            category="adoption",
            status="sheltered",
        ),
        Animal(
            species="猫",
            sex="女の子",
            shelter_date=date(2026, 1, 6),
            location="高知県",
            source_url="https://example.com/animal/2",
            category="adoption",
            status="adopted",
        ),
        Animal(
            species="犬",
            sex="女の子",
            shelter_date=date(2026, 1, 7),
            location="高知県",
            source_url="https://example.com/animal/3",
            category="lost",
            status="sheltered",
        ),
        Animal(
            species="猫",
            sex="男の子",
            shelter_date=date(2026, 1, 8),
            location="高知県",
            source_url="https://example.com/animal/4",
            category="lost",
            status="returned",
        ),
    ]

    for animal in animals:
        async_session.add(animal)
    await async_session.commit()

    return async_session


# === AnimalMetricsCollector Tests ===


@pytest.mark.asyncio
async def test_get_status_counts(populated_session):
    """ステータス別件数を取得できるか"""
    repository = AnimalRepository(populated_session)
    collector = AnimalMetricsCollector(repository)

    counts = await collector.get_status_counts()

    assert counts["sheltered"] == 2
    assert counts["adopted"] == 1
    assert counts["returned"] == 1
    assert counts.get("deceased", 0) == 0


@pytest.mark.asyncio
async def test_get_category_counts(populated_session):
    """カテゴリ別件数を取得できるか"""
    repository = AnimalRepository(populated_session)
    collector = AnimalMetricsCollector(repository)

    counts = await collector.get_category_counts()

    assert counts["adoption"] == 2
    assert counts["lost"] == 2


@pytest.mark.asyncio
async def test_collect_metrics_without_services(populated_session):
    """ArchiveService と ImageStorageService なしでもメトリクス収集できるか"""
    repository = AnimalRepository(populated_session)
    collector = AnimalMetricsCollector(repository)

    metrics = await collector.collect()

    assert isinstance(metrics, AnimalMetrics)
    assert metrics.total_count == 4
    assert metrics.status_counts["sheltered"] == 2
    assert metrics.category_counts["adoption"] == 2
    assert metrics.archivable_count == 0  # archive_service なし
    assert metrics.image_download_failure_rate == 0.0
    assert metrics.storage_usage_bytes == 0


@pytest.mark.asyncio
async def test_collect_metrics_with_archive_service(populated_session):
    """ArchiveService を使用してアーカイブ対象件数を取得できるか"""
    repository = AnimalRepository(populated_session)

    # モックの ArchiveService
    mock_archive_service = AsyncMock()
    mock_archive_service.get_archivable_count = AsyncMock(return_value=10)

    collector = AnimalMetricsCollector(
        repository,
        archive_service=mock_archive_service,
    )

    metrics = await collector.collect()

    assert metrics.archivable_count == 10
    mock_archive_service.get_archivable_count.assert_called_once()


@pytest.mark.asyncio
async def test_collect_metrics_with_image_storage_service(populated_session):
    """ImageStorageService を使用してストレージ情報を取得できるか"""
    repository = AnimalRepository(populated_session)

    # モックの ImageStorageService
    mock_image_service = MagicMock()
    mock_image_service.get_failure_rate.return_value = 0.05
    mock_image_service.get_storage_usage_bytes.return_value = 1024 * 1024 * 100  # 100MB

    collector = AnimalMetricsCollector(
        repository,
        image_storage_service=mock_image_service,
    )

    metrics = await collector.collect()

    assert metrics.image_download_failure_rate == 0.05
    assert metrics.storage_usage_bytes == 100 * 1024 * 1024
    mock_image_service.get_failure_rate.assert_called_once()
    mock_image_service.get_storage_usage_bytes.assert_called_once()


# === AlertManager Tests ===


@pytest.mark.asyncio
async def test_alert_manager_no_alert_when_below_threshold():
    """閾値以下の場合はアラートが発生しないか"""
    manager = AlertManager(
        failure_rate_threshold=0.1, storage_threshold_bytes=10 * 1024 * 1024 * 1024
    )

    metrics = AnimalMetrics(
        total_count=100,
        status_counts={"sheltered": 50, "adopted": 50},
        category_counts={"adoption": 100},
        archivable_count=0,
        image_download_failure_rate=0.05,  # 5% < 10%
        storage_usage_bytes=5 * 1024 * 1024 * 1024,  # 5GB < 10GB
    )

    alerts = await manager.check_and_alert(metrics)

    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_alert_manager_alerts_on_high_failure_rate():
    """失敗率が閾値を超えた場合にアラートが発生するか"""
    manager = AlertManager(failure_rate_threshold=0.1)

    metrics = AnimalMetrics(
        total_count=100,
        status_counts={"sheltered": 100},
        category_counts={"adoption": 100},
        archivable_count=0,
        image_download_failure_rate=0.15,  # 15% > 10%
        storage_usage_bytes=0,
    )

    alerts = await manager.check_and_alert(metrics)

    assert len(alerts) == 1
    assert alerts[0]["type"] == "image_download_failure_rate"
    assert alerts[0]["level"] == "warning"
    assert "15.0%" in alerts[0]["message"]


@pytest.mark.asyncio
async def test_alert_manager_alerts_on_high_storage_usage():
    """ストレージ使用量が閾値を超えた場合にアラートが発生するか"""
    manager = AlertManager(storage_threshold_bytes=10 * 1024 * 1024 * 1024)

    metrics = AnimalMetrics(
        total_count=100,
        status_counts={"sheltered": 100},
        category_counts={"adoption": 100},
        archivable_count=0,
        image_download_failure_rate=0.0,
        storage_usage_bytes=15 * 1024 * 1024 * 1024,  # 15GB > 10GB
    )

    alerts = await manager.check_and_alert(metrics)

    assert len(alerts) == 1
    assert alerts[0]["type"] == "storage_usage"
    assert alerts[0]["level"] == "warning"
    assert "15.0GB" in alerts[0]["message"]


@pytest.mark.asyncio
async def test_alert_manager_multiple_alerts():
    """複数のアラートが同時に発生できるか"""
    manager = AlertManager(
        failure_rate_threshold=0.1,
        storage_threshold_bytes=10 * 1024 * 1024 * 1024,
    )

    metrics = AnimalMetrics(
        total_count=100,
        status_counts={"sheltered": 100},
        category_counts={"adoption": 100},
        archivable_count=0,
        image_download_failure_rate=0.2,  # 20% > 10%
        storage_usage_bytes=20 * 1024 * 1024 * 1024,  # 20GB > 10GB
    )

    alerts = await manager.check_and_alert(metrics)

    assert len(alerts) == 2
    alert_types = {alert["type"] for alert in alerts}
    assert "image_download_failure_rate" in alert_types
    assert "storage_usage" in alert_types


@pytest.mark.asyncio
async def test_alert_manager_sends_notification():
    """通知クライアントが設定されている場合に通知を送信するか"""
    mock_client = AsyncMock()
    mock_client.send_alert = AsyncMock(return_value=True)

    manager = AlertManager(
        notification_client=mock_client,
        failure_rate_threshold=0.1,
    )

    metrics = AnimalMetrics(
        total_count=100,
        status_counts={"sheltered": 100},
        category_counts={"adoption": 100},
        archivable_count=0,
        image_download_failure_rate=0.15,
        storage_usage_bytes=0,
    )

    alerts = await manager.check_and_alert(metrics)

    assert len(alerts) == 1
    mock_client.send_alert.assert_called_once()
    call_args = mock_client.send_alert.call_args
    assert "アラート発生" in call_args[0][0]
    assert call_args[1]["level"] == "warning"


# === AuditLogger Tests ===


def test_audit_logger_log_status_change():
    """ステータス変更を監査ログに記録できるか"""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        audit_logger = AuditLogger()
        audit_logger.log_status_change(
            animal_id=123,
            old_status="sheltered",
            new_status="adopted",
            changed_by="admin",
        )

        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args[0][0]
        assert "STATUS_CHANGE" in call_args
        assert "animal_id=123" in call_args
        assert "old_status=sheltered" in call_args
        assert "new_status=adopted" in call_args
        assert "changed_by=admin" in call_args


def test_audit_logger_log_status_change_default_changed_by():
    """changed_by が未指定の場合に 'system' が設定されるか"""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        audit_logger = AuditLogger()
        audit_logger.log_status_change(
            animal_id=123,
            old_status="sheltered",
            new_status="adopted",
        )

        call_args = mock_logger.info.call_args[0][0]
        assert "changed_by=system" in call_args


def test_audit_logger_log_archive():
    """アーカイブ操作を監査ログに記録できるか"""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        audit_logger = AuditLogger()
        audit_logger.log_archive(animal_id=456, original_id=123)

        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args[0][0]
        assert "ARCHIVE" in call_args
        assert "animal_id=456" in call_args
        assert "original_id=123" in call_args


def test_audit_logger_log_image_download_success():
    """画像ダウンロード成功を監査ログに記録できるか"""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        audit_logger = AuditLogger()
        audit_logger.log_image_download(
            animal_id=123,
            url="https://example.com/image.jpg",
            success=True,
        )

        mock_logger.info.assert_called()
        call_args = mock_logger.info.call_args[0][0]
        assert "IMAGE_DOWNLOAD" in call_args
        assert "success=True" in call_args


def test_audit_logger_log_image_download_failure():
    """画像ダウンロード失敗を監査ログに記録できるか"""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        audit_logger = AuditLogger()
        audit_logger.log_image_download(
            animal_id=123,
            url="https://example.com/image.jpg",
            success=False,
            error="Connection timeout",
        )

        mock_logger.warning.assert_called()
        call_args = mock_logger.warning.call_args[0][0]
        assert "IMAGE_DOWNLOAD" in call_args
        assert "success=False" in call_args
        assert "error=Connection timeout" in call_args
