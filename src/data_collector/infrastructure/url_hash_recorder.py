"""画像URLハッシュ記録ヘルパー（Phase 1 MVP）

画像本体のダウンロードはせず、URL文字列のSHA-256ハッシュを image_hashes
テーブルに蓄積する。複数自治体での同一URL掲載を後段で発見するための足場。

Phase 2 で実画像のダウンロード + Supabase Storage 連携に拡張する。
"""

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from src.data_collector.infrastructure.database.image_hash_repository import (
    ImageHashRepository,
)


class URLHashRecorder:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ImageHashRepository(session)

    @staticmethod
    def compute_url_hash(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    async def record_urls(self, urls: list[str]) -> dict[str, bool]:
        """URLのリストを image_hashes に登録する。

        Returns:
            url -> is_new のマップ。is_new=True は新規登録、False は既存。
        """
        seen: set[str] = set()
        result: dict[str, bool] = {}
        for url in urls:
            if not url or url in seen:
                continue
            seen.add(url)
            url_hash = self.compute_url_hash(url)
            existing = await self._repo.find_by_hash(url_hash)
            if existing:
                result[url] = False
            else:
                # Phase 1 MVP: file_size=0 はファイル未取得を示す。
                # Phase 2 でダウンロード成功時に local_path と file_size を更新する。
                await self._repo.register(url_hash, local_path=url, file_size=0)
                result[url] = True
        return result
