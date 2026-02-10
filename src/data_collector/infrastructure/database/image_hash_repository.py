"""
ImageHashRepository - 画像ハッシュのデータアクセス層

画像の重複検出とハッシュ管理のためのリポジトリを提供します。
"""

from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.data_collector.infrastructure.database.models import ImageHash


class ImageHashRepository:
    """
    画像ハッシュリポジトリ

    画像の SHA-256 ハッシュと保存パスの対応を管理します。
    重複検出により、同一画像の二重保存を防止します。
    """

    def __init__(self, session: AsyncSession):
        """
        ImageHashRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    async def find_by_hash(self, hash: str) -> Optional[ImageHash]:
        """
        ハッシュで画像情報を検索

        Args:
            hash: SHA-256 ハッシュ値

        Returns:
            Optional[ImageHash]: 画像ハッシュレコード、存在しない場合は None
        """
        stmt = select(ImageHash).where(ImageHash.hash == hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def register(
        self,
        hash: str,
        local_path: str,
        file_size: int,
    ) -> ImageHash:
        """
        新しい画像ハッシュを登録

        既に同じハッシュが存在する場合は既存のレコードを返します。

        Args:
            hash: SHA-256 ハッシュ値
            local_path: ローカル保存パス
            file_size: ファイルサイズ（バイト）

        Returns:
            ImageHash: 登録されたまたは既存のレコード
        """
        # 既存のハッシュをチェック
        existing = await self.find_by_hash(hash)
        if existing:
            return existing

        # 新規レコードを作成
        image_hash = ImageHash(
            hash=hash,
            local_path=local_path,
            file_size=file_size,
        )
        self.session.add(image_hash)
        await self.session.flush()
        return image_hash

    async def check_duplicate(self, hash: str) -> Optional[str]:
        """
        重複チェック

        Args:
            hash: SHA-256 ハッシュ値

        Returns:
            Optional[str]: 既存のローカルパス（重複の場合）、None（新規の場合）
        """
        existing = await self.find_by_hash(hash)
        if existing:
            return existing.local_path
        return None

    async def delete(self, hash: str) -> bool:
        """
        ハッシュレコードを削除

        Args:
            hash: SHA-256 ハッシュ値

        Returns:
            bool: 削除成功した場合は True、存在しない場合は False
        """
        existing = await self.find_by_hash(hash)
        if existing:
            await self.session.delete(existing)
            return True
        return False

    async def count(self) -> int:
        """
        登録されているハッシュの件数を取得

        Returns:
            int: レコード件数
        """
        stmt = select(func.count()).select_from(ImageHash)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def total_size(self) -> int:
        """
        登録されている画像の合計サイズを取得

        Returns:
            int: 合計サイズ（バイト）
        """
        stmt = select(func.sum(ImageHash.file_size))
        result = await self.session.execute(stmt)
        return result.scalar() or 0
