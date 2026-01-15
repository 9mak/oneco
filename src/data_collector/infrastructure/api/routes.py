"""
API ルート定義

動物データ取得のためのREST APIエンドポイントを提供します。
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Annotated, Optional
from datetime import date, datetime
from src.data_collector.infrastructure.api.dependencies import SessionDep
from src.data_collector.infrastructure.api.schemas import (
    AnimalPublic,
    PaginationMeta,
    PaginatedResponse,
)
from src.data_collector.infrastructure.database.repository import AnimalRepository
from src.data_collector.infrastructure.logging_config import get_logger


logger = get_logger(__name__)
router = APIRouter(tags=["animals"])


@router.get("/animals", response_model=PaginatedResponse[AnimalPublic])
async def list_animals(
    session: SessionDep,
    species: Optional[str] = Query(None, description="動物種別フィルタ"),
    sex: Optional[str] = Query(None, description="性別フィルタ"),
    location: Optional[str] = Query(None, description="場所フィルタ（部分一致）"),
    shelter_date_from: Optional[date] = Query(None, description="収容日開始"),
    shelter_date_to: Optional[date] = Query(None, description="収容日終了"),
    limit: Annotated[int, Query(le=1000, ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaginatedResponse[AnimalPublic]:
    """
    動物データリストを取得

    フィルタリング、ソート、ページネーション機能を提供します。
    """
    logger.info(
        f"GET /animals - species={species}, sex={sex}, location={location}, "
        f"shelter_date_from={shelter_date_from}, shelter_date_to={shelter_date_to}, "
        f"limit={limit}, offset={offset}"
    )
    repository = AnimalRepository(session)

    # データ取得（ORMモデルとして取得）
    orm_animals, total_count = await repository.list_animals_orm(
        species=species,
        sex=sex,
        location=location,
        shelter_date_from=shelter_date_from,
        shelter_date_to=shelter_date_to,
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
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            },
        )
