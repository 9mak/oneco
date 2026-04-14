"""ImageStorageService のユニットテスト"""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.data_collector.infrastructure.database.image_hash_repository import ImageHashRepository
from src.data_collector.infrastructure.database.models import Base
from src.data_collector.infrastructure.image_storage import LocalImageStorage
from src.data_collector.infrastructure.image_storage_service import (
    ImageDownloadResult,
    ImageStorageService,
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


@pytest.fixture
def tmp_storage(tmp_path: Path) -> LocalImageStorage:
    """テスト用の LocalImageStorage を作成"""
    return LocalImageStorage(base_path=tmp_path / "images")


@pytest_asyncio.fixture
async def image_hash_repo(async_session) -> ImageHashRepository:
    """テスト用の ImageHashRepository を作成"""
    return ImageHashRepository(async_session)


@pytest_asyncio.fixture
async def service(tmp_storage, image_hash_repo, async_session) -> ImageStorageService:
    """テスト用の ImageStorageService を作成"""
    return ImageStorageService(
        storage=tmp_storage,
        hash_repository=image_hash_repo,
        session=async_session,
    )


class TestImageStorageServiceBasics:
    """ImageStorageService の基本機能テスト"""

    @pytest.fixture
    def sample_jpeg_content(self) -> bytes:
        """サンプル JPEG コンテンツ"""
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100

    @pytest.fixture
    def sample_png_content(self) -> bytes:
        """サンプル PNG コンテンツ"""
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    # === calculate_hash() のテスト ===

    def test_calculate_hash_returns_sha256(self, service: ImageStorageService):
        """calculate_hash() が SHA-256 ハッシュを返すことを確認"""
        content = b"test content"

        result = service.calculate_hash(content)

        expected = hashlib.sha256(content).hexdigest()
        assert result == expected
        assert len(result) == 64  # SHA-256 は 64 文字

    def test_calculate_hash_different_content(self, service: ImageStorageService):
        """calculate_hash() が異なるコンテンツに異なるハッシュを返すことを確認"""
        content1 = b"content 1"
        content2 = b"content 2"

        hash1 = service.calculate_hash(content1)
        hash2 = service.calculate_hash(content2)

        assert hash1 != hash2

    def test_calculate_hash_same_content(self, service: ImageStorageService):
        """calculate_hash() が同じコンテンツに同じハッシュを返すことを確認"""
        content = b"same content"

        hash1 = service.calculate_hash(content)
        hash2 = service.calculate_hash(content)

        assert hash1 == hash2

    # === validate_image_format() のテスト ===

    def test_validate_image_format_accepts_jpeg(self, service: ImageStorageService):
        """validate_image_format() が JPEG を受け入れることを確認"""
        assert service.validate_image_format("image/jpeg") is True

    def test_validate_image_format_accepts_png(self, service: ImageStorageService):
        """validate_image_format() が PNG を受け入れることを確認"""
        assert service.validate_image_format("image/png") is True

    def test_validate_image_format_accepts_gif(self, service: ImageStorageService):
        """validate_image_format() が GIF を受け入れることを確認"""
        assert service.validate_image_format("image/gif") is True

    def test_validate_image_format_accepts_webp(self, service: ImageStorageService):
        """validate_image_format() が WebP を受け入れることを確認"""
        assert service.validate_image_format("image/webp") is True

    def test_validate_image_format_rejects_text(self, service: ImageStorageService):
        """validate_image_format() が text/plain を拒否することを確認"""
        assert service.validate_image_format("text/plain") is False

    def test_validate_image_format_rejects_html(self, service: ImageStorageService):
        """validate_image_format() が text/html を拒否することを確認"""
        assert service.validate_image_format("text/html") is False

    def test_validate_image_format_rejects_pdf(self, service: ImageStorageService):
        """validate_image_format() が application/pdf を拒否することを確認"""
        assert service.validate_image_format("application/pdf") is False

    # === get_extension_from_content_type() のテスト ===

    def test_get_extension_from_content_type_jpeg(self, service: ImageStorageService):
        """get_extension_from_content_type() が JPEG の拡張子を返すことを確認"""
        result = service.get_extension_from_content_type("image/jpeg")
        assert result == "jpg"

    def test_get_extension_from_content_type_png(self, service: ImageStorageService):
        """get_extension_from_content_type() が PNG の拡張子を返すことを確認"""
        result = service.get_extension_from_content_type("image/png")
        assert result == "png"

    def test_get_extension_from_content_type_gif(self, service: ImageStorageService):
        """get_extension_from_content_type() が GIF の拡張子を返すことを確認"""
        result = service.get_extension_from_content_type("image/gif")
        assert result == "gif"

    def test_get_extension_from_content_type_webp(self, service: ImageStorageService):
        """get_extension_from_content_type() が WebP の拡張子を返すことを確認"""
        result = service.get_extension_from_content_type("image/webp")
        assert result == "webp"

    def test_get_extension_from_content_type_unknown(self, service: ImageStorageService):
        """get_extension_from_content_type() が未知の形式に None を返すことを確認"""
        result = service.get_extension_from_content_type("image/unknown")
        assert result is None

    # === save_image() のテスト ===

    @pytest.mark.asyncio
    async def test_save_image_stores_file(
        self, service: ImageStorageService, sample_jpeg_content: bytes
    ):
        """save_image() がファイルを保存することを確認"""
        result = await service.save_image(sample_jpeg_content, "jpg")

        assert result.success is True
        assert result.local_path is not None
        assert result.hash is not None
        assert result.is_duplicate is False

    @pytest.mark.asyncio
    async def test_save_image_detects_duplicate(
        self, service: ImageStorageService, sample_jpeg_content: bytes, async_session
    ):
        """save_image() が重複を検出することを確認"""
        # 1回目の保存
        first = await service.save_image(sample_jpeg_content, "jpg")
        await async_session.commit()

        # 2回目の保存（同じコンテンツ）
        second = await service.save_image(sample_jpeg_content, "jpg")

        assert second.success is True
        assert second.is_duplicate is True
        assert second.local_path == first.local_path

    @pytest.mark.asyncio
    async def test_save_image_registers_hash(
        self,
        service: ImageStorageService,
        sample_jpeg_content: bytes,
        image_hash_repo,
        async_session,
    ):
        """save_image() がハッシュを登録することを確認"""
        result = await service.save_image(sample_jpeg_content, "jpg")
        await async_session.commit()

        # ハッシュが登録されていることを確認
        hash_record = await image_hash_repo.find_by_hash(result.hash)
        assert hash_record is not None
        assert hash_record.local_path == result.local_path


class TestImageStorageServiceDownload:
    """ImageStorageService のダウンロード機能テスト"""

    @pytest.fixture
    def mock_jpeg_response(self):
        """モック JPEG レスポンス"""
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100

    @pytest.mark.asyncio
    async def test_download_and_store_success(
        self, service: ImageStorageService, mock_jpeg_response: bytes
    ):
        """download_and_store() が正常にダウンロード・保存することを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (mock_jpeg_response, "image/jpeg", None)

            results = await service.download_and_store(["https://example.com/image.jpg"])

            assert len(results) == 1
            assert results[0].success is True
            assert results[0].url == "https://example.com/image.jpg"
            assert results[0].local_path is not None

    @pytest.mark.asyncio
    async def test_download_and_store_multiple_images(
        self, service: ImageStorageService, mock_jpeg_response: bytes
    ):
        """download_and_store() が複数画像を処理することを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (mock_jpeg_response, "image/jpeg", None)

            urls = [
                "https://example.com/image1.jpg",
                "https://example.com/image2.jpg",
                "https://example.com/image3.jpg",
            ]
            results = await service.download_and_store(urls)

            assert len(results) == 3
            assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_download_and_store_handles_failure(self, service: ImageStorageService):
        """download_and_store() がダウンロード失敗を処理することを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (None, None, "タイムアウト")

            results = await service.download_and_store(["https://example.com/fail.jpg"])

            assert len(results) == 1
            assert results[0].success is False
            assert "タイムアウト" in results[0].error

    @pytest.mark.asyncio
    async def test_download_and_store_rejects_unsupported_format(
        self, service: ImageStorageService
    ):
        """download_and_store() が非対応形式を拒否することを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (b"not an image", "text/html", None)

            results = await service.download_and_store(["https://example.com/page.html"])

            assert len(results) == 1
            assert results[0].success is False
            assert "非対応" in results[0].error

    @pytest.mark.asyncio
    async def test_download_and_store_mixed_results(
        self, service: ImageStorageService, mock_jpeg_response: bytes
    ):
        """download_and_store() が成功と失敗の混在を処理することを確認"""
        call_count = 0

        async def mock_download(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (mock_jpeg_response, "image/jpeg", None)
            else:
                return (None, None, "エラー")

        with patch.object(service, "download_image", side_effect=mock_download):
            results = await service.download_and_store(
                [
                    "https://example.com/success.jpg",
                    "https://example.com/fail.jpg",
                ]
            )

            assert len(results) == 2
            assert results[0].success is True
            assert results[1].success is False

    @pytest.mark.asyncio
    async def test_download_and_store_updates_failure_counter(self, service: ImageStorageService):
        """download_and_store() が失敗カウンターを更新することを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (None, None, "エラー")

            await service.download_and_store(["https://example.com/fail.jpg"])

            assert service._total_attempts == 1
            assert service._failed_attempts == 1

    @pytest.mark.asyncio
    async def test_download_and_store_empty_list(self, service: ImageStorageService):
        """download_and_store() が空リストを処理することを確認"""
        results = await service.download_and_store([])

        assert results == []


class TestImageStorageServiceMonitoring:
    """ImageStorageService の監視機能テスト"""

    @pytest.fixture
    def mock_jpeg_response(self):
        """モック JPEG レスポンス"""
        return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100

    def test_get_failure_rate_zero_initial(self, service: ImageStorageService):
        """get_failure_rate() が初期状態で 0 を返すことを確認"""
        assert service.get_failure_rate() == 0.0

    @pytest.mark.asyncio
    async def test_get_failure_rate_after_failures(self, service: ImageStorageService):
        """get_failure_rate() が正しい失敗率を返すことを確認"""
        with patch.object(service, "download_image") as mock_download:
            # 2回成功、3回失敗
            call_count = 0

            async def mock_download_fn(url):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    return (b"\xff\xd8\xff\xe0" + b"\x00" * 100, "image/jpeg", None)
                else:
                    return (None, None, "エラー")

            mock_download.side_effect = mock_download_fn

            await service.download_and_store(
                [
                    "https://example.com/1.jpg",
                    "https://example.com/2.jpg",
                    "https://example.com/3.jpg",
                    "https://example.com/4.jpg",
                    "https://example.com/5.jpg",
                ]
            )

            # 3/5 = 0.6
            assert service.get_failure_rate() == 0.6

    @pytest.mark.asyncio
    async def test_get_failure_rate_all_success(
        self, service: ImageStorageService, mock_jpeg_response: bytes
    ):
        """get_failure_rate() が全成功時に 0 を返すことを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (mock_jpeg_response, "image/jpeg", None)

            await service.download_and_store(["https://example.com/1.jpg"])

            assert service.get_failure_rate() == 0.0

    def test_get_storage_usage_bytes_initial(self, service: ImageStorageService):
        """get_storage_usage_bytes() が初期状態で 0 を返すことを確認"""
        # storage に何もないので 0
        assert service.get_storage_usage_bytes() == 0

    @pytest.mark.asyncio
    async def test_get_storage_usage_bytes_after_save(
        self, service: ImageStorageService, mock_jpeg_response: bytes
    ):
        """get_storage_usage_bytes() が保存後に正しいサイズを返すことを確認"""
        with patch.object(service, "download_image") as mock_download:
            mock_download.return_value = (mock_jpeg_response, "image/jpeg", None)

            await service.download_and_store(["https://example.com/1.jpg"])

            usage = service.get_storage_usage_bytes()
            assert usage == len(mock_jpeg_response)

    def test_reset_counters(self, service: ImageStorageService):
        """reset_counters() がカウンターをリセットすることを確認"""
        service._total_attempts = 10
        service._failed_attempts = 5

        service.reset_counters()

        assert service._total_attempts == 0
        assert service._failed_attempts == 0


class TestImageDownloadResult:
    """ImageDownloadResult のテスト"""

    def test_success_result(self):
        """成功結果を作成できることを確認"""
        result = ImageDownloadResult(
            url="https://example.com/image.jpg",
            success=True,
            local_path="a1/b2/hash.jpg",
            hash="hash123",
            is_duplicate=False,
        )

        assert result.url == "https://example.com/image.jpg"
        assert result.success is True
        assert result.local_path == "a1/b2/hash.jpg"
        assert result.error is None

    def test_failure_result(self):
        """失敗結果を作成できることを確認"""
        result = ImageDownloadResult(
            url="https://example.com/image.jpg",
            success=False,
            error="Connection timeout",
        )

        assert result.url == "https://example.com/image.jpg"
        assert result.success is False
        assert result.local_path is None
        assert result.error == "Connection timeout"

    def test_duplicate_result(self):
        """重複結果を作成できることを確認"""
        result = ImageDownloadResult(
            url="https://example.com/image.jpg",
            success=True,
            local_path="existing/path.jpg",
            hash="existing_hash",
            is_duplicate=True,
        )

        assert result.is_duplicate is True
