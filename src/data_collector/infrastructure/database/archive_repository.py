"""
ArchiveRepository - アーカイブデータアクセス層

アーカイブされた動物データの読み取り専用アクセスを提供します。
更新・削除機能は意図的に提供しません（読み取り専用）。
"""

from typing import List, Optional, Tuple
from datetime import date, datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from src.data_collector.domain.models import AnimalData, AnimalStatus
from src.data_collector.infrastructure.database.models import Animal, AnimalArchive


class ArchiveRepository:
    """
    アーカイブリポジトリ（読み取り専用）

    アーカイブテーブルへのデータアクセスを提供します。
    insert_archive() は ArchiveService からのみ呼び出されます。
    """

    def __init__(self, session: AsyncSession):
        """
        ArchiveRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    def _to_pydantic(self, archived: AnimalArchive) -> AnimalData:
        """
        SQLAlchemy AnimalArchive を Pydantic AnimalData に変換

        Args:
            archived: SQLAlchemy アーカイブモデル

        Returns:
            AnimalData: Pydantic 動物データ
        """
        return AnimalData(
            species=archived.species,
            sex=archived.sex,
            age_months=archived.age_months,
            color=archived.color,
            size=archived.size,
            shelter_date=archived.shelter_date,
            location=archived.location,
            phone=archived.phone,
            image_urls=archived.image_urls or [],
            source_url=archived.source_url,
            category=archived.category,
            status=AnimalStatus(archived.status) if archived.status else None,
            status_changed_at=archived.status_changed_at,
            outcome_date=archived.outcome_date,
            local_image_paths=archived.local_image_paths or None,
        )

    async def get_archived_by_id(
        self,
        archive_id: int,
    ) -> Optional[AnimalData]:
        """
        アーカイブから動物データを取得

        Args:
            archive_id: アーカイブID

        Returns:
            Optional[AnimalData]: 動物データ、存在しない場合は None
        """
        stmt = select(AnimalArchive).where(AnimalArchive.id == archive_id)
        result = await self.session.execute(stmt)
        archived = result.scalar_one_or_none()

        if archived:
            return self._to_pydantic(archived)
        return None

    async def get_archived_by_original_id(
        self,
        original_id: int,
    ) -> Optional[AnimalData]:
        """
        元の動物IDからアーカイブデータを取得

        Args:
            original_id: 元の動物ID

        Returns:
            Optional[AnimalData]: 動物データ、存在しない場合は None
        """
        stmt = select(AnimalArchive).where(AnimalArchive.original_id == original_id)
        result = await self.session.execute(stmt)
        archived = result.scalar_one_or_none()

        if archived:
            return self._to_pydantic(archived)
        return None

    async def list_archived(
        self,
        species: Optional[str] = None,
        archived_from: Optional[date] = None,
        archived_to: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[AnimalData], int]:
        """
        アーカイブデータをリスト取得

        Args:
            species: 動物種別フィルタ
            archived_from: アーカイブ日開始
            archived_to: アーカイブ日終了
            limit: 取得件数（デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[AnimalData], int]: (動物データリスト, 総件数)
        """
        # クエリベースを作成
        stmt = select(AnimalArchive)

        # フィルタ適用
        filters = []
        if species:
            filters.append(AnimalArchive.species == species)
        if archived_from:
            # date を datetime に変換（その日の開始時刻）
            archived_from_dt = datetime.combine(archived_from, datetime.min.time())
            filters.append(AnimalArchive.archived_at >= archived_from_dt)
        if archived_to:
            # date を datetime に変換（その日の終了時刻）
            archived_to_dt = datetime.combine(archived_to, datetime.max.time())
            filters.append(AnimalArchive.archived_at <= archived_to_dt)

        if filters:
            stmt = stmt.where(*filters)

        # 総件数を取得
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # ソートとページネーション適用
        stmt = stmt.order_by(AnimalArchive.archived_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        # データ取得
        result = await self.session.execute(stmt)
        archived_animals = result.scalars().all()

        # Pydantic モデルに変換
        animal_data_list = [self._to_pydantic(a) for a in archived_animals]

        return animal_data_list, total_count

    async def insert_archive(
        self,
        animal: Animal,
    ) -> None:
        """
        アーカイブにデータを挿入

        ArchiveService からのみ呼び出されることを想定しています。

        Args:
            animal: アーカイブ対象の動物 ORM モデル
        """
        archived = AnimalArchive(
            original_id=animal.id,
            species=animal.species,
            sex=animal.sex,
            age_months=animal.age_months,
            color=animal.color,
            size=animal.size,
            shelter_date=animal.shelter_date,
            location=animal.location,
            phone=animal.phone,
            image_urls=animal.image_urls or [],
            local_image_paths=animal.local_image_paths or [],
            source_url=animal.source_url,
            category=animal.category,
            status=animal.status,
            status_changed_at=animal.status_changed_at,
            outcome_date=animal.outcome_date,
            archived_at=datetime.now(timezone.utc),
        )
        self.session.add(archived)
        await self.session.flush()
