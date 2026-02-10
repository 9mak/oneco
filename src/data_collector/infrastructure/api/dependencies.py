"""
FastAPI 依存性注入

データベースセッションなどの依存性を提供します。
テスト用にオーバーライド可能な設計になっています。
"""

from typing import AsyncGenerator, Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
import src.data_collector.infrastructure.api.app as app_module


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    データベースセッションを取得する依存性

    FastAPIの依存性注入システムで使用されます。
    各リクエストごとに新しいセッションを作成し、レスポンス後に自動クローズします。

    Yields:
        AsyncSession: データベースセッション

    Raises:
        DatabaseError: データベース接続エラー
    """
    async with app_module.db_connection.get_session() as session:
        yield session


# SessionDep タイプエイリアス
# FastAPI ルートで使用する際の型ヒント
SessionDep = Annotated[AsyncSession, Depends(get_session)]
