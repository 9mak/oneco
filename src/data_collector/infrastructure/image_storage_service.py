"""
ImageStorageService - 画像ダウンロード・保存サービス

外部 URL から画像をダウンロードし、ローカルストレージに保存する機能を提供します。
SHA-256 ハッシュによる重複検出と、失敗率監視機能を含みます。
"""

import hashlib
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.data_collector.infrastructure.image_storage import LocalImageStorage
from src.data_collector.infrastructure.database.image_hash_repository import ImageHashRepository

logger = logging.getLogger(__name__)


@dataclass
class ImageDownloadResult:
    """
    画像ダウンロード結果

    各画像のダウンロード・保存処理の結果を表現します。
    """

    url: str
    success: bool
    local_path: Optional[str] = None
    hash: Optional[str] = None
    error: Optional[str] = None
    is_duplicate: bool = False


class ImageStorageService:
    """
    画像ストレージサービス

    外部画像のダウンロード、ローカル保存、重複検出を提供します。
    """

    # サポートする画像形式と対応する MIME タイプ
    SUPPORTED_FORMATS: Set[str] = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    }

    # MIME タイプから拡張子へのマッピング
    MIME_TO_EXTENSION: dict[str, str] = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
    }

    # タイムアウト設定
    CONNECT_TIMEOUT: float = 5.0
    READ_TIMEOUT: float = 30.0

    # リトライ設定
    MAX_RETRIES: int = 3

    def __init__(
        self,
        storage: LocalImageStorage,
        hash_repository: ImageHashRepository,
        session: AsyncSession,
    ):
        """
        ImageStorageService を初期化

        Args:
            storage: ローカル画像ストレージ
            hash_repository: 画像ハッシュリポジトリ
            session: データベースセッション
        """
        self.storage = storage
        self.hash_repository = hash_repository
        self.session = session

        # 失敗率カウンター
        self._total_attempts = 0
        self._failed_attempts = 0

    def calculate_hash(self, content: bytes) -> str:
        """
        SHA-256 ハッシュを計算

        Args:
            content: 画像バイナリデータ

        Returns:
            str: SHA-256 ハッシュ値（16進数文字列）
        """
        return hashlib.sha256(content).hexdigest()

    def validate_image_format(self, content_type: str) -> bool:
        """
        画像形式を検証

        Args:
            content_type: MIME タイプ

        Returns:
            bool: サポートされる形式の場合は True
        """
        return content_type in self.SUPPORTED_FORMATS

    def get_extension_from_content_type(self, content_type: str) -> Optional[str]:
        """
        MIME タイプから拡張子を取得

        Args:
            content_type: MIME タイプ

        Returns:
            Optional[str]: 拡張子、未対応の場合は None
        """
        return self.MIME_TO_EXTENSION.get(content_type)

    async def check_duplicate(self, hash: str) -> Optional[str]:
        """
        重複チェック

        Args:
            hash: SHA-256 ハッシュ値

        Returns:
            Optional[str]: 既存のローカルパス（重複の場合）、None（新規の場合）
        """
        return await self.hash_repository.check_duplicate(hash)

    async def save_image(
        self,
        content: bytes,
        extension: str,
    ) -> ImageDownloadResult:
        """
        画像を保存

        重複検出を行い、新規の場合のみ保存します。

        Args:
            content: 画像バイナリデータ
            extension: ファイル拡張子

        Returns:
            ImageDownloadResult: 保存結果
        """
        # ハッシュを計算
        hash_value = self.calculate_hash(content)

        # 重複チェック
        existing_path = await self.check_duplicate(hash_value)
        if existing_path:
            return ImageDownloadResult(
                url="",
                success=True,
                local_path=existing_path,
                hash=hash_value,
                is_duplicate=True,
            )

        # ストレージに保存
        local_path = self.storage.save(hash_value, content, extension)

        # ハッシュを登録
        await self.hash_repository.register(
            hash=hash_value,
            local_path=local_path,
            file_size=len(content),
        )

        return ImageDownloadResult(
            url="",
            success=True,
            local_path=local_path,
            hash=hash_value,
            is_duplicate=False,
        )

    async def download_image(self, url: str) -> tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        画像をダウンロード

        Args:
            url: 画像 URL

        Returns:
            tuple: (コンテンツ, content_type, エラーメッセージ)
        """
        timeout = httpx.Timeout(
            connect=self.CONNECT_TIMEOUT,
            read=self.READ_TIMEOUT,
            write=None,
            pool=None,
        )

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                    content_type = response.headers.get("content-type", "").split(";")[0]

                    return response.content, content_type, None

            except httpx.TimeoutException:
                if attempt == self.MAX_RETRIES - 1:
                    return None, None, f"タイムアウト: {url}"
                # リトライ

            except httpx.HTTPStatusError as e:
                return None, None, f"HTTPエラー {e.response.status_code}: {url}"

            except httpx.RequestError as e:
                if attempt == self.MAX_RETRIES - 1:
                    return None, None, f"リクエストエラー: {str(e)}"
                # リトライ

        return None, None, f"最大リトライ回数超過: {url}"

    async def download_and_store(
        self,
        image_urls: List[str],
    ) -> List[ImageDownloadResult]:
        """
        複数画像をダウンロードして保存

        Args:
            image_urls: 画像 URL リスト

        Returns:
            List[ImageDownloadResult]: 各画像の処理結果
        """
        results = []

        for url in image_urls:
            self._total_attempts += 1

            # ダウンロード
            content, content_type, error = await self.download_image(url)

            if error:
                self._failed_attempts += 1
                logger.warning(f"画像ダウンロード失敗: {error}")
                results.append(ImageDownloadResult(
                    url=url,
                    success=False,
                    error=error,
                ))
                continue

            # 形式検証
            if not self.validate_image_format(content_type):
                self._failed_attempts += 1
                error_msg = f"非対応の画像形式: {content_type}"
                logger.warning(f"{error_msg} - {url}")
                results.append(ImageDownloadResult(
                    url=url,
                    success=False,
                    error=error_msg,
                ))
                continue

            # 拡張子を取得
            extension = self.get_extension_from_content_type(content_type)
            if not extension:
                self._failed_attempts += 1
                error_msg = f"拡張子取得失敗: {content_type}"
                results.append(ImageDownloadResult(
                    url=url,
                    success=False,
                    error=error_msg,
                ))
                continue

            # 保存
            try:
                save_result = await self.save_image(content, extension)
                save_result.url = url
                results.append(save_result)
            except Exception as e:
                self._failed_attempts += 1
                error_msg = f"保存エラー: {str(e)}"
                logger.exception(f"画像保存中にエラー発生: {url}")
                results.append(ImageDownloadResult(
                    url=url,
                    success=False,
                    error=error_msg,
                ))

        return results

    async def move_to_archive(
        self,
        local_paths: List[str],
    ) -> List[str]:
        """
        画像をアーカイブストレージに移動

        Args:
            local_paths: ローカルパスリスト

        Returns:
            List[str]: 新しいアーカイブパスリスト
        """
        new_paths = []
        for path in local_paths:
            new_path = self.storage.move(path, "archive")
            new_paths.append(new_path)
        return new_paths

    def get_failure_rate(self) -> float:
        """
        失敗率を取得

        Returns:
            float: 失敗率（0.0 〜 1.0）
        """
        if self._total_attempts == 0:
            return 0.0
        return self._failed_attempts / self._total_attempts

    def get_storage_usage_bytes(self) -> int:
        """
        ストレージ使用量を取得

        Returns:
            int: 使用量（バイト）
        """
        return self.storage.get_usage_bytes()

    def reset_counters(self) -> None:
        """
        失敗率カウンターをリセット
        """
        self._total_attempts = 0
        self._failed_attempts = 0
