"""
API ルート定義

動物データ取得のためのREST APIエンドポイントを提供します。
"""

import os
import secrets
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query

from src.data_collector.domain.models import AnimalStatus
from src.data_collector.domain.status_transition import StatusTransitionError
from src.data_collector.infrastructure.api.dependencies import SessionDep
from src.data_collector.infrastructure.api.schemas import (
    AnimalPublic,
    ArchivedAnimalPublic,
    PaginatedResponse,
    PaginationMeta,
    StatusUpdateRequest,
    StatusUpdateResponse,
)
from src.data_collector.infrastructure.database.archive_repository import ArchiveRepository
from src.data_collector.infrastructure.database.repository import (
    AnimalRepository,
    NotFoundError,
)
from src.data_collector.infrastructure.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["animals"])
archive_router = APIRouter(prefix="/archive", tags=["archive"])


def require_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> None:
    """
    内部 API のトークン認証

    ステータス更新等の書き込み系エンドポイントで使う。
    INTERNAL_API_TOKEN 環境変数（Cloud Run シークレット）と一致しない要求は 401。
    secrets.compare_digest でタイミング攻撃を防止。
    """
    expected = os.getenv("INTERNAL_API_TOKEN", "").strip()
    if not expected:
        # トークン未設定時は本番設定ミスとして 503（誰も認証通せない）
        logger.error("INTERNAL_API_TOKEN is not configured")
        raise HTTPException(status_code=503, detail="Server misconfigured")
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/animals", response_model=PaginatedResponse[AnimalPublic])
async def list_animals(
    session: SessionDep,
    species: str | None = Query(None, description="動物種別フィルタ"),
    sex: str | None = Query(None, description="性別フィルタ"),
    location: str | None = Query(None, description="場所フィルタ（部分一致）"),
    prefecture: str | None = Query(None, description="都道府県フィルタ (完全一致, 例: '高知県')"),
    category: str | None = Query(None, description="カテゴリフィルタ ('adoption' または 'lost')"),
    shelter_date_from: date | None = Query(None, description="収容日開始"),
    shelter_date_to: date | None = Query(None, description="収容日終了"),
    status: str | None = Query(
        None, description="ステータスフィルタ ('sheltered', 'adopted', 'returned', 'deceased')"
    ),
    q: str | None = Query(
        None,
        description="キーワード検索（species/color/size/location/prefecture を OR 部分一致）",
        max_length=100,
    ),
    limit: Annotated[int, Query(le=1000, ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[AnimalPublic]:
    """
    動物データリストを取得

    フィルタリング、ソート、ページネーション機能を提供します。
    """
    # カテゴリバリデーション
    if category is not None and category not in ["adoption", "lost", "sheltered"]:
        raise HTTPException(
            status_code=400,
            detail=f"無効なカテゴリ: {category}。'adoption', 'lost', 'sheltered' のいずれかを指定してください",
        )

    # ステータスバリデーション
    status_enum: AnimalStatus | None = None
    if status is not None:
        valid_statuses = ["sheltered", "adopted", "returned", "deceased"]
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"無効なステータス: {status}。{', '.join(valid_statuses)} のいずれかを指定してください",
            )
        status_enum = AnimalStatus(status)

    logger.info(
        f"GET /animals - species={species}, sex={sex}, location={location}, "
        f"prefecture={prefecture}, category={category}, status={status}, "
        f"shelter_date_from={shelter_date_from}, shelter_date_to={shelter_date_to}, "
        f"limit={limit}, offset={offset}"
    )
    repository = AnimalRepository(session)

    # データ取得（ORMモデルとして取得）
    orm_animals, total_count = await repository.list_animals_orm(
        species=species,
        sex=sex,
        location=location,
        prefecture=prefecture,
        category=category,
        status=status_enum,
        shelter_date_from=shelter_date_from,
        shelter_date_to=shelter_date_to,
        q=q,
        limit=limit,
        offset=offset,
    )

    # SQLAlchemy ORM モデル を AnimalPublic に変換
    animal_publics = [AnimalPublic.model_validate(orm_animal) for orm_animal in orm_animals]

    # ページネーションメタデータを計算
    # current_page: offsetから現在のページ番号を計算（1-indexed）
    import math

    if limit > 0:
        current_page = math.ceil((offset + limit) / limit)
        total_pages = math.ceil(total_count / limit)
    else:
        current_page = 1
        total_pages = 0
    has_next = (offset + limit) < total_count

    meta = PaginationMeta(
        total_count=total_count,
        limit=limit,
        offset=offset,
        current_page=current_page,
        total_pages=total_pages,
        has_next=has_next,
    )

    return PaginatedResponse(items=animal_publics, meta=meta)


@router.get("/animals/{animal_id}", response_model=AnimalPublic)
async def get_animal(
    animal_id: Annotated[int, Path(description="動物ID")],
    session: SessionDep,
) -> AnimalPublic:
    """
    動物データを個別取得

    指定されたIDの動物データを返します。
    """
    logger.info(f"GET /animals/{animal_id}")
    repository = AnimalRepository(session)

    orm_animal = await repository.get_animal_by_id_orm(animal_id)

    if orm_animal is None:
        raise HTTPException(status_code=404, detail=f"Animal with ID {animal_id} not found")

    return AnimalPublic.model_validate(orm_animal)


@router.patch(
    "/animals/{animal_id}/status",
    response_model=StatusUpdateResponse,
    dependencies=[Depends(require_internal_token)],
)
async def update_animal_status(
    animal_id: Annotated[int, Path(description="動物ID")],
    request: StatusUpdateRequest,
    session: SessionDep,
) -> StatusUpdateResponse:
    """
    動物のステータスを更新

    指定されたIDの動物のステータスを更新します。
    不正なステータス遷移は拒否されます。
    """
    logger.info(f"PATCH /animals/{animal_id}/status - new_status={request.status.value}")
    repository = AnimalRepository(session)

    try:
        # AnimalStatus に変換
        new_status = AnimalStatus(request.status.value)

        # ステータス更新
        await repository.update_status(
            animal_id=animal_id,
            new_status=new_status,
            outcome_date=request.outcome_date,
        )

        # ORM モデルを取得して AnimalPublic に変換
        orm_animal = await repository.get_animal_by_id_orm(animal_id)
        animal_public = AnimalPublic.model_validate(orm_animal)

        return StatusUpdateResponse(success=True, animal=animal_public)

    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Animal with ID {animal_id} not found")
    except StatusTransitionError as e:
        raise HTTPException(
            status_code=422,
            detail=f"無効なステータス遷移: {e.old_status.value} → {e.new_status.value}",
        )


@router.get("/animals/stats/by-prefecture")
async def stats_by_prefecture(session: SessionDep) -> dict[str, int]:
    """
    都道府県別の収容中動物数を返す（status='sheltered' のみ集計）

    日本地図ビューや統計ページで使用する。レスポンス例:
    { "高知県": 65, "徳島県": 0, ... }
    """
    from sqlalchemy import func, select

    from src.data_collector.infrastructure.database.models import Animal

    stmt = (
        select(Animal.prefecture, func.count(Animal.id))
        .where(Animal.status == "sheltered")
        .where(Animal.prefecture.isnot(None))
        .group_by(Animal.prefecture)
    )
    result = await session.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


@router.get("/health")
async def health_check(session: SessionDep) -> dict:
    """
    ヘルスチェックエンドポイント

    データベース接続テストを実行し、システムの健全性を確認します。
    """
    try:
        # データベース接続テスト（簡単なクエリを実行）
        from sqlalchemy import text

        result = await session.execute(text("SELECT 1"))
        result.scalar()

        logger.info("Health check passed")

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        # エラー詳細はログのみ。レスポンスには汎用メッセージのみ（DB ホスト名等の漏洩防止）
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": "database connection failed",
            },
        )


# === Archive Endpoints ===


@archive_router.get("/animals", response_model=PaginatedResponse[ArchivedAnimalPublic])
async def list_archived_animals(
    session: SessionDep,
    species: str | None = Query(None, description="動物種別フィルタ"),
    archived_from: date | None = Query(None, description="アーカイブ日開始"),
    archived_to: date | None = Query(None, description="アーカイブ日終了"),
    limit: Annotated[int, Query(le=1000, ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[ArchivedAnimalPublic]:
    """
    アーカイブ動物データリストを取得

    アーカイブされた動物データをフィルタリング、ページネーションして取得します。
    読み取り専用のエンドポイントです。
    """
    logger.info(
        f"GET /archive/animals - species={species}, archived_from={archived_from}, "
        f"archived_to={archived_to}, limit={limit}, offset={offset}"
    )

    repository = ArchiveRepository(session)

    # データ取得
    _animals, total_count = await repository.list_archived(
        species=species,
        archived_from=archived_from,
        archived_to=archived_to,
        limit=limit,
        offset=offset,
    )

    # ページネーションメタデータを計算
    import math

    if limit > 0:
        current_page = math.ceil((offset + limit) / limit)
        total_pages = math.ceil(total_count / limit)
    else:
        current_page = 1
        total_pages = 0
    has_next = (offset + limit) < total_count

    meta = PaginationMeta(
        total_count=total_count,
        limit=limit,
        offset=offset,
        current_page=current_page,
        total_pages=total_pages,
        has_next=has_next,
    )

    # AnimalData を ArchivedAnimalPublic に変換
    # NOTE: ArchiveRepository は AnimalData を返すが、ArchivedAnimalPublic には
    # original_id と archived_at が必要なため、ORM からの取得が必要
    from sqlalchemy import select

    from src.data_collector.infrastructure.database.models import AnimalArchive

    stmt = select(AnimalArchive)
    filters = []
    if species:
        filters.append(AnimalArchive.species == species)
    if archived_from:
        archived_from_dt = datetime.combine(archived_from, datetime.min.time())
        filters.append(AnimalArchive.archived_at >= archived_from_dt)
    if archived_to:
        archived_to_dt = datetime.combine(archived_to, datetime.max.time())
        filters.append(AnimalArchive.archived_at <= archived_to_dt)

    if filters:
        stmt = stmt.where(*filters)

    stmt = stmt.order_by(AnimalArchive.archived_at.desc())
    stmt = stmt.limit(limit).offset(offset)

    result = await session.execute(stmt)
    orm_archives = result.scalars().all()

    archived_publics = [ArchivedAnimalPublic.model_validate(a) for a in orm_archives]

    return PaginatedResponse(items=archived_publics, meta=meta)


@archive_router.get("/animals/{archive_id}", response_model=ArchivedAnimalPublic)
async def get_archived_animal(
    archive_id: Annotated[int, Path(description="アーカイブID")],
    session: SessionDep,
) -> ArchivedAnimalPublic:
    """
    アーカイブ動物データを個別取得

    指定されたIDのアーカイブ動物データを返します。
    """
    logger.info(f"GET /archive/animals/{archive_id}")

    from sqlalchemy import select

    from src.data_collector.infrastructure.database.models import AnimalArchive

    stmt = select(AnimalArchive).where(AnimalArchive.id == archive_id)
    result = await session.execute(stmt)
    orm_archive = result.scalar_one_or_none()

    if orm_archive is None:
        raise HTTPException(
            status_code=404, detail=f"Archived animal with ID {archive_id} not found"
        )

    return ArchivedAnimalPublic.model_validate(orm_archive)
