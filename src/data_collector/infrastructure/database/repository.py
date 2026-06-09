"""
AnimalRepository - データアクセス層

Repository パターンによる動物データのCRUD操作を提供します。
Pydantic AnimalData と SQLAlchemy Animal モデルの変換を担当します。
"""

from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data_collector.domain.models import AnimalData, AnimalStatus
from src.data_collector.domain.status_transition import (
    StatusTransitionValidator,
)
from src.data_collector.infrastructure.database.models import Animal, AnimalStatusHistory


def _escape_like(value: str) -> str:
    r"""LIKE/ILIKE のワイルドカード (\\ % _) をエスケープし、ユーザー入力を
    リテラルな部分一致として扱う。``escape="\\"`` と併用する。

    これが無いと ``location=%`` で全件マッチ、``q=A_B`` の ``_`` が任意 1 文字
    に化ける。SQLi は SQLAlchemy のバインド変数で防御されているため、
    本関数は意味論的正しさ (部分一致のリテラル化) を担う。
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class NotFoundError(Exception):
    """リソースが見つからない場合のエラー"""

    def __init__(self, resource: str, resource_id: int):
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} with id {resource_id} not found")


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
            prefecture=animal_data.prefecture,
            phone=animal_data.phone,
            image_urls=[str(url) for url in animal_data.image_urls],
            source_url=str(animal_data.source_url),
            category=animal_data.category,
            # 個体識別フィールド
            breed=animal_data.breed,
            name=animal_data.name,
            management_number=animal_data.management_number,
            description=animal_data.description,
            # 拡張フィールド
            status=animal_data.status.value if animal_data.status else "sheltered",
            status_changed_at=animal_data.status_changed_at,
            outcome_date=animal_data.outcome_date,
            local_image_paths=animal_data.local_image_paths or [],
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
            prefecture=orm_animal.prefecture,
            phone=orm_animal.phone,
            image_urls=orm_animal.image_urls or [],
            source_url=orm_animal.source_url,
            category=orm_animal.category,
            # 個体識別フィールド
            breed=orm_animal.breed,
            name=orm_animal.name,
            management_number=orm_animal.management_number,
            description=orm_animal.description,
            # 拡張フィールド
            status=AnimalStatus(orm_animal.status) if orm_animal.status else None,
            status_changed_at=orm_animal.status_changed_at,
            outcome_date=orm_animal.outcome_date,
            local_image_paths=orm_animal.local_image_paths or None,
        )

    async def save_animal(
        self, animal_data: AnimalData, source_site: str | None = None
    ) -> AnimalData:
        """
        動物データを保存（upsert）

        source_url が既存の場合は更新、新規の場合は挿入します。

        Args:
            animal_data: 保存する動物データ
            source_site: 収集元サイト識別名 (SiteConfig.name)。消滅同期削除のスコープ
                に使う。収集経路から渡す。None のときは既存値を変更しない。

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
            existing_animal.prefecture = animal_data.prefecture
            existing_animal.phone = animal_data.phone
            existing_animal.image_urls = [str(url) for url in animal_data.image_urls]
            existing_animal.category = animal_data.category
            # 個体識別フィールドは category 同様に無条件上書き
            # (ソースから値が消えたら None で上書きし、古い値を残留させない)
            existing_animal.breed = animal_data.breed
            existing_animal.name = animal_data.name
            existing_animal.management_number = animal_data.management_number
            existing_animal.description = animal_data.description
            # 拡張フィールドは明示的に設定された場合のみ更新
            if animal_data.status is not None:
                existing_animal.status = animal_data.status.value
            if animal_data.status_changed_at is not None:
                existing_animal.status_changed_at = animal_data.status_changed_at
            if animal_data.outcome_date is not None:
                existing_animal.outcome_date = animal_data.outcome_date
            if animal_data.local_image_paths is not None:
                existing_animal.local_image_paths = animal_data.local_image_paths
            orm_animal = existing_animal
        else:
            # 新規レコードを挿入
            orm_animal = self._to_orm(animal_data)
            self.session.add(orm_animal)

        # 収集経路から渡されたサイト識別名を記録（消滅同期削除のスコープ用）
        if source_site is not None:
            orm_animal.source_site = source_site

        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def prune_disappeared(self, source_site: str, seen_source_urls: set[str]) -> int:
        """指定サイトで今回の収集に出てこなかった動物（= ソースから消えた）を削除する。

        ソースに掲載が無い＝もういない、とみなしてライブから外し、ポータルを
        ソースと同期させる。

        Args:
            source_site: 対象サイトの識別名 (SiteConfig.name)
            seen_source_urls: 今回の収集で確認できた source_url の集合

        Returns:
            削除した件数

        安全策:
        - seen_source_urls が空（収集0件 / adapter 破損の可能性）のときは、サイト
          全体を誤って消さないよう **何もしない**。
        - source_site でスコープするため、他サイトや未タグ(NULL)の行は消さない。
        - 万一まだ在籍する子を誤って消しても、次回収集で再登録されるため復旧可能。
        """
        if not seen_source_urls:
            return 0
        stmt = (
            delete(Animal)
            .where(Animal.source_site == source_site)
            .where(Animal.source_url.notin_(seen_source_urls))
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount or 0

    async def get_animal_by_id(self, animal_id: int) -> AnimalData | None:
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
        species: str | None = None,
        sex: str | None = None,
        location: str | None = None,
        prefecture: str | None = None,
        category: str | None = None,
        shelter_date_from: date | None = None,
        shelter_date_to: date | None = None,
        status: AnimalStatus | None = None,
        q: str | None = None,
        include_non_public: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AnimalData], int]:
        """
        動物データをフィルタリング・ページネーションして取得

        Args:
            species: 動物種別フィルタ
            sex: 性別フィルタ
            location: 場所フィルタ（部分一致）
            category: カテゴリフィルタ ('adoption' または 'lost')
            shelter_date_from: 収容日開始
            shelter_date_to: 収容日終了
            status: ステータスフィルタ
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
            filters.append(Animal.location.like(f"%{_escape_like(location)}%", escape="\\"))
        if prefecture:
            filters.append(Animal.prefecture == prefecture)
        if category:
            filters.append(Animal.category == category)
        if shelter_date_from:
            filters.append(Animal.shelter_date >= shelter_date_from)
        if shelter_date_to:
            filters.append(Animal.shelter_date <= shelter_date_to)
        if status:
            filters.append(Animal.status == status.value)
        if not include_non_public:
            # 死亡(deceased)個体は公開対象から除外する（データ境界での強制）。
            # NULL status の行を誤って落とさないよう is_distinct_from で null-safe に比較。
            filters.append(Animal.status.is_distinct_from(AnimalStatus.DECEASED.value))
        if q:
            # キーワード検索: 複数フィールドを OR で部分一致（ILIKE）
            # 「茶白」「人懐っこい」「子犬」など自由テキストで
            # species/color/size/location/prefecture を横断検索
            from sqlalchemy import or_

            keyword = f"%{_escape_like(q)}%"
            filters.append(
                or_(
                    Animal.species.ilike(keyword, escape="\\"),
                    Animal.color.ilike(keyword, escape="\\"),
                    Animal.size.ilike(keyword, escape="\\"),
                    Animal.location.ilike(keyword, escape="\\"),
                    Animal.prefecture.ilike(keyword, escape="\\"),
                )
            )

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
        species: str | None = None,
        sex: str | None = None,
        location: str | None = None,
        prefecture: str | None = None,
        category: str | None = None,
        shelter_date_from: date | None = None,
        shelter_date_to: date | None = None,
        status: AnimalStatus | None = None,
        q: str | None = None,
        include_non_public: bool = False,
        sort: str = "newest",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Animal], int]:
        """
        動物データをフィルタリング・ページネーションして取得（ORMモデルとして）

        Args:
            species: 動物種別フィルタ
            sex: 性別フィルタ
            location: 場所フィルタ（部分一致）
            category: カテゴリフィルタ ('adoption' または 'lost')
            shelter_date_from: 収容日開始
            shelter_date_to: 収容日終了
            status: ステータスフィルタ
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
            filters.append(Animal.location.like(f"%{_escape_like(location)}%", escape="\\"))
        if prefecture:
            filters.append(Animal.prefecture == prefecture)
        if category:
            filters.append(Animal.category == category)
        if shelter_date_from:
            filters.append(Animal.shelter_date >= shelter_date_from)
        if shelter_date_to:
            filters.append(Animal.shelter_date <= shelter_date_to)
        if status:
            filters.append(Animal.status == status.value)
        if not include_non_public:
            # 死亡(deceased)個体は公開対象から除外する（データ境界での強制）。
            # NULL status の行を誤って落とさないよう is_distinct_from で null-safe に比較。
            filters.append(Animal.status.is_distinct_from(AnimalStatus.DECEASED.value))
        if q:
            from sqlalchemy import or_

            keyword = f"%{_escape_like(q)}%"
            filters.append(
                or_(
                    Animal.species.ilike(keyword, escape="\\"),
                    Animal.color.ilike(keyword, escape="\\"),
                    Animal.size.ilike(keyword, escape="\\"),
                    Animal.location.ilike(keyword, escape="\\"),
                    Animal.prefecture.ilike(keyword, escape="\\"),
                )
            )

        if filters:
            stmt = stmt.where(*filters)

        # 総件数を取得
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.session.execute(count_stmt)
        total_count = count_result.scalar()

        # ソートとページネーション適用（id を tie-breaker にして安定化）
        if sort == "oldest":
            stmt = stmt.order_by(Animal.shelter_date.asc(), Animal.id.asc())
        else:
            stmt = stmt.order_by(Animal.shelter_date.desc(), Animal.id.desc())
        stmt = stmt.limit(limit).offset(offset)

        # データ取得
        result = await self.session.execute(stmt)
        orm_animals = result.scalars().all()

        return orm_animals, total_count

    async def get_animal_by_id_orm(
        self, animal_id: int, include_non_public: bool = False
    ) -> Animal | None:
        """
        IDで動物データを取得（ORMモデルとして）

        Args:
            animal_id: 動物ID
            include_non_public: True なら死亡(deceased)個体も返す（内部の status 更新・
                画像パス更新・削除フロー用）。False（既定/公開）は deceased を None 扱いに
                して、ルート層で 404 を返させる。

        Returns:
            Optional[Animal]: 動物ORMモデル、存在しない/非公開の場合は None
        """
        stmt = select(Animal).where(Animal.id == animal_id)
        if not include_non_public:
            stmt = stmt.where(Animal.status.is_distinct_from(AnimalStatus.DECEASED.value))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        animal_id: int,
        new_status: AnimalStatus,
        outcome_date: date | None = None,
        changed_by: str | None = None,
    ) -> AnimalData:
        """
        動物のステータスを更新

        トランザクション内でステータス更新とステータス履歴の記録を原子的に実行します。

        Args:
            animal_id: 動物ID
            new_status: 新しいステータス
            outcome_date: 成果日（adopted/returned の場合）
            changed_by: 変更者（オプション）

        Returns:
            AnimalData: 更新後のデータ

        Raises:
            StatusTransitionError: 不正なステータス遷移
            NotFoundError: 動物が存在しない
        """
        # 動物を取得
        # 内部管理フロー（status 更新・画像パス更新・削除）は deceased も対象にする。
        orm_animal = await self.get_animal_by_id_orm(animal_id, include_non_public=True)
        if orm_animal is None:
            raise NotFoundError("Animal", animal_id)

        # 現在のステータスを取得
        old_status = AnimalStatus(orm_animal.status)

        # ステータス遷移を検証
        validator = StatusTransitionValidator()
        validator.validate_transition(old_status, new_status)

        # ステータスを更新
        orm_animal.status = new_status.value
        orm_animal.status_changed_at = datetime.now(UTC)

        # outcome_date の設定（adopted/returned の場合）
        if outcome_date is not None:
            orm_animal.outcome_date = outcome_date
        elif new_status in (AnimalStatus.ADOPTED, AnimalStatus.RETURNED):
            # outcome_date が未指定の場合はステータス変更日を使用
            orm_animal.outcome_date = orm_animal.status_changed_at.date()

        # ステータス履歴を記録
        history = AnimalStatusHistory(
            animal_id=animal_id,
            old_status=old_status.value,
            new_status=new_status.value,
            changed_at=orm_animal.status_changed_at,
            changed_by=changed_by,
        )
        self.session.add(history)

        # コミット
        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def list_animals_by_status(
        self,
        status: AnimalStatus,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AnimalData], int]:
        """
        ステータスで動物をフィルタリング

        Args:
            status: フィルタするステータス
            limit: 取得件数（デフォルト50）
            offset: オフセット（デフォルト0）

        Returns:
            Tuple[List[AnimalData], int]: (動物データリスト, 総件数)
        """
        return await self.list_animals(status=status, limit=limit, offset=offset)

    async def update_local_image_paths(
        self,
        animal_id: int,
        local_paths: list[str],
    ) -> AnimalData:
        """
        ローカル画像パスを更新

        Args:
            animal_id: 動物ID
            local_paths: ローカル画像パスのリスト

        Returns:
            AnimalData: 更新後のデータ

        Raises:
            NotFoundError: 動物が存在しない
        """
        # 動物を取得
        # 内部管理フロー（status 更新・画像パス更新・削除）は deceased も対象にする。
        orm_animal = await self.get_animal_by_id_orm(animal_id, include_non_public=True)
        if orm_animal is None:
            raise NotFoundError("Animal", animal_id)

        # ローカル画像パスを更新
        orm_animal.local_image_paths = local_paths

        # コミット
        await self.session.commit()
        await self.session.refresh(orm_animal)

        return self._to_pydantic(orm_animal)

    async def find_archivable_animals(
        self,
        retention_days: int = 180,
        limit: int = 1000,
    ) -> list[Animal]:
        """
        アーカイブ対象の動物を検索

        保持期間（デフォルト180日）を経過した adopted または returned ステータスの
        動物を返します。deceased はアーカイブ対象外です。

        Args:
            retention_days: 保持期間（日数、デフォルト180）
            limit: 取得件数（デフォルト1000）

        Returns:
            List[Animal]: アーカイブ対象の動物 ORM モデルリスト
        """
        from datetime import timedelta

        # 保持期限の計算
        cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

        # アーカイブ対象: adopted または returned で、status_changed_at が cutoff_date より前
        stmt = (
            select(Animal)
            .where(
                Animal.status.in_(["adopted", "returned"]),
                Animal.status_changed_at <= cutoff_date,
            )
            .order_by(Animal.status_changed_at)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_animal(self, animal_id: int) -> None:
        """
        動物レコードを削除

        Args:
            animal_id: 動物ID

        Raises:
            NotFoundError: 動物が存在しない
        """
        # 内部管理フロー（status 更新・画像パス更新・削除）は deceased も対象にする。
        orm_animal = await self.get_animal_by_id_orm(animal_id, include_non_public=True)
        if orm_animal is None:
            raise NotFoundError("Animal", animal_id)

        await self.session.delete(orm_animal)
        await self.session.commit()

    async def get_status_counts(self) -> dict:
        """
        ステータス別の動物件数を取得

        Returns:
            dict: {status: count} 形式のステータス別件数
        """
        stmt = select(Animal.status, func.count()).group_by(Animal.status)
        result = await self.session.execute(stmt)
        counts = {row[0]: row[1] for row in result.all()}
        return counts
