"""
AnimalRepository - データアクセス層

Repository パターンによる動物データのCRUD操作を提供します。
Pydantic AnimalData と SQLAlchemy Animal モデルの変換を担当します。
"""

from typing import List, Optional, Tuple
from datetime import date
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from src.data_collector.domain.models import AnimalData
from src.data_collector.infrastructure.database.models import Animal


class AnimalRepository:
    """
    動物データリポジトリ

    データアクセスロジックをカプセル化し、
    Pydantic モデルと SQLAlchemy モデルの変換を提供します。
    """

    def __init__(self, session: AsyncSession):
        """
        AnimalRepository を初期化

        Args:
            session: データベースセッション
        """
        self.session = session

    def _to_orm(self, animal_data: AnimalData) -> Animal:
        """
        Pydantic AnimalData を SQLAlchemy Animal に変換

        Args:
            animal_data: Pydantic 動物データ

        Returns:
            Animal: SQLAlchemy ORM モデル
        """
        return Animal(
            species=animal_data.species,
            sex=animal_data.sex,
            age_months=animal_data.age_months,
            color=animal_data.color,
            size=animal_data.size,
            shelter_date=animal_data.shelter_date,
            location=animal_data.location,
            phone=animal_data.phone,
            image_urls=[str(url) for url in animal_data.image_urls],
            source_url=str(animal_data.source_url),
        )

    def _to_pydantic(self, orm_animal: Animal) -> AnimalData:
        """
        SQLAlchemy Animal を Pydantic AnimalData に変換

        Args:
            orm_animal: SQLAlchemy ORM モデル

        Returns:
            AnimalData: Pydantic 動物データ
        """
        return AnimalData(
            species=orm_animal.species,
            sex=orm_animal.sex,
            age_months=orm_animal.age_months,
            color=orm_animal.color,
            size=orm_animal.size,
            shelter_date=orm_animal.shelter_date,
            location=orm_animal.location,
            phone=orm_animal.phone,
            image_urls=orm_animal.image_urls or [],
            source_url=orm_animal.source_url,
        )

    async def save_animal(self, animal_data: AnimalData) -> AnimalData:
        """
        動物データを保存（upsert）

        source_url が既存の場合は更新、新規の場合は挿入します。

        Args:
            animal_data: 保存する動物データ

        Returns:
            AnimalData: 保存後のデータ（IDを含む）

        Raises:
            DatabaseError: データベース接続エラー
            ValidationError: バリデーションエラー
        """
        # 既存レコードを検索
        stmt = select(Animal).where(Animal.source_url == str(animal_data.source_url))
        result = await self.session.execute(stmt)
        existing_animal = result.scalar_one_or_none()

        if existing_animal:
            # 既存レコードを更新
            existing_animal.species = animal_data.species
            existing_animal.sex = animal_data.sex
            existing_animal.age_months = animal_data.age_months
            existing_animal.color = animal_data.color
            existing_animal.size = animal_data.size
            existing_animal.shelter_date = animal_data.shelter_date
            existing_animal.location = animal_data.location
            existing_animal.phone = animal_data.phone
            existing_animal.image_urls = [str(url) for url in animal_data.image_urls]
            orm_animal = existing_animal
        else:
            # 新規レコードを挿入
            orm_animal = self._to_orm(animal_data)
            self.session.add(orm_animal)

        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def get_animal_by_id(self, animal_id: int) -> Optional[AnimalData]:
        """
        IDで動物データを取得

        Args:
            animal_id: 動物ID

        Returns:
            Optional[AnimalData]: 動物データ、存在しない場合は None
        """
        stmt = select(Animal).where(Animal.id == animal_id)
        result = await self.session.execute(stmt)
        orm_animal = result.scalar_one_or_none()

        if orm_animal:
            return self._to_pydantic(orm_animal)
        return None

    async def list_animals(
        self,
        species: Optional[str] = None,
        sex: Optional[str] = None,
        location: Optional[str] = None,
        shelter_date_from: Optional[date] = None,
        shelter_date_to: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[AnimalData], int]:
        """
        動物データをフィルタリング・ページネーションして取得

        Args:
            species: 動物種別フィルタ
            sex: 性別フィルタ
            location: 場所フィルタ（部分一致）
            shelter_date_from: 収容日開始
            shelter_date_to: 収容日終了
            limit: 取得件数（最大1000、デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[AnimalData], int]: (動物データリスト, 総件数)
        """
        # クエリベースを作成
        stmt = select(Animal)

        # フィルタ適用
        filters = []
        if species:
            filters.append(Animal.species == species)
        if sex:
            filters.append(Animal.sex == sex)
        if location:
            filters.append(Animal.location.like(f"%{location}%"))
        if shelter_date_from:
            filters.append(Animal.shelter_date >= shelter_date_from)
        if shelter_date_to:
            filters.append(Animal.shelter_date <= shelter_date_to)

        if filters:
            stmt = stmt.where(*filters)

        # 総件数を取得
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # ソートとページネーション適用
        stmt = stmt.order_by(Animal.shelter_date.desc())
        stmt = stmt.limit(limit).offset(offset)

        # データ取得
        result = await self.session.execute(stmt)
        orm_animals = result.scalars().all()

        # Pydantic モデルに変換
        animal_data_list = [self._to_pydantic(a) for a in orm_animals]

        return animal_data_list, total_count

    async def list_animals_orm(
        self,
        species: Optional[str] = None,
        sex: Optional[str] = None,
        location: Optional[str] = None,
        shelter_date_from: Optional[date] = None,
        shelter_date_to: Optional[date] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Animal], int]:
        """
        動物データをフィルタリング・ページネーションして取得（ORMモデルとして）

        Args:
            species: 動物種別フィルタ
            sex: 性別フィルタ
            location: 場所フィルタ（部分一致）
            shelter_date_from: 収容日開始
            shelter_date_to: 収容日終了
            limit: 取得件数（最大1000、デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[Animal], int]: (動物ORMモデルリスト, 総件数)
        """
        # クエリベースを作成
        stmt = select(Animal)

        # フィルタ適用
        filters = []
        if species:
            filters.append(Animal.species == species)
        if sex:
            filters.append(Animal.sex == sex)
        if location:
            filters.append(Animal.location.like(f"%{location}%"))
        if shelter_date_from:
            filters.append(Animal.shelter_date >= shelter_date_from)
        if shelter_date_to:
            filters.append(Animal.shelter_date <= shelter_date_to)

        if filters:
            stmt = stmt.where(*filters)

        # 総件数を取得
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # ソートとページネーション適用
        stmt = stmt.order_by(Animal.shelter_date.desc())
        stmt = stmt.limit(limit).offset(offset)

        # データ取得
        result = await self.session.execute(stmt)
        orm_animals = result.scalars().all()

        return orm_animals, total_count

    async def get_animal_by_id_orm(self, animal_id: int) -> Optional[Animal]:
        """
        IDで動物データを取得（ORMモデルとして）

        Args:
            animal_id: 動物ID

        Returns:
            Optional[Animal]: 動物ORMモデル、存在しない場合は None
        """
        stmt = select(Animal).where(Animal.id == animal_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
