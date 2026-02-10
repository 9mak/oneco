"""
StatusHistoryRepository - ステータス履歴リポジトリ

動物のステータス変更履歴の記録と取得を担当するリポジトリ層です。
"""

from typing import List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.data_collector.domain.models import AnimalStatus
from src.data_collector.infrastructure.database.models import AnimalStatusHistory


@dataclass
class StatusHistoryEntry:
    """
    ステータス履歴エントリ

    ステータス変更の1レコードを表すデータクラス。
    """

    id: int
    animal_id: int
    old_status: AnimalStatus
    new_status: AnimalStatus
    changed_at: datetime
    changed_by: Optional[str] = None


class StatusHistoryRepository:
    """
    ステータス履歴リポジトリ

    動物のステータス変更履歴を記録・取得するためのリポジトリ。
    AnimalRepository からトランザクション内で呼び出されることを想定しています。
    """

    def __init__(self, session: AsyncSession):
        """
        StatusHistoryRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    def _to_entry(self, orm_history: AnimalStatusHistory) -> StatusHistoryEntry:
        """
        SQLAlchemy ORM モデルを StatusHistoryEntry に変換

        Args:
            orm_history: SQLAlchemy ORM モデル

        Returns:
            StatusHistoryEntry: データクラス
        """
        return StatusHistoryEntry(
            id=orm_history.id,
            animal_id=orm_history.animal_id,
            old_status=AnimalStatus(orm_history.old_status),
            new_status=AnimalStatus(orm_history.new_status),
            changed_at=orm_history.changed_at,
            changed_by=orm_history.changed_by,
        )

    async def record_transition(
        self,
        animal_id: int,
        old_status: AnimalStatus,
        new_status: AnimalStatus,
        changed_by: Optional[str] = None,
    ) -> StatusHistoryEntry:
        """
        ステータス遷移を記録

        Args:
            animal_id: 動物ID
            old_status: 現在のステータス
            new_status: 新しいステータス
            changed_by: 変更者（オプション）

        Returns:
            StatusHistoryEntry: 作成された履歴エントリ
        """
        orm_history = AnimalStatusHistory(
            animal_id=animal_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_at=datetime.now(timezone.utc),
            changed_by=changed_by,
        )

        self.session.add(orm_history)
        await self.session.commit()
        await self.session.refresh(orm_history)

        return self._to_entry(orm_history)

    async def get_history(
        self,
        animal_id: int,
    ) -> List[StatusHistoryEntry]:
        """
        動物のステータス履歴を取得

        Args:
            animal_id: 動物ID

        Returns:
            List[StatusHistoryEntry]: ステータス履歴エントリのリスト（時系列順）
        """
        stmt = (
            select(AnimalStatusHistory)
            .where(AnimalStatusHistory.animal_id == animal_id)
            .order_by(AnimalStatusHistory.changed_at.asc())
        )

        result = await self.session.execute(stmt)
        orm_histories = result.scalars().all()

        return [self._to_entry(h) for h in orm_histories]
