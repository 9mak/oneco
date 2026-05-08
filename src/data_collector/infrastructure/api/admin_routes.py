"""
管理ダッシュボード用の集計エンドポイント

X-Internal-Token 認証で保護される。フロントエンドの /admin が
NextAuth + GitHub OAuth でゲートした上で、サーバーサイドからこの
エンドポイントを叩いて集計データを取得する想定。
"""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from src.data_collector.infrastructure.api.dependencies import SessionDep
from src.data_collector.infrastructure.api.routes import require_internal_token
from src.data_collector.infrastructure.database.models import Animal, ImageHash

admin_router = APIRouter(prefix="/admin", tags=["admin"])

_KNOWN_STATUSES = ("sheltered", "adopted", "returned", "deceased")
_UNCATEGORIZED_LABEL = "(未分類)"


@admin_router.get("/stats")
async def get_admin_stats(
    session: SessionDep,
    _: Annotated[None, Depends(require_internal_token)] = None,
) -> dict:
    """
    ダッシュボード用の集計を一括返却する。

    - total_animals: 全件数（アーカイブ前）
    - by_status: ステータス別件数（既知ステータスは0埋め）
    - by_prefecture: 県別件数（降順、prefecture None は (未分類)）
    - by_species: 種別件数
    - by_category: カテゴリ別件数
    - image_hash_summary: ハッシュテーブル統計
    - generated_at: 集計時刻
    """
    # 全体件数
    total = (await session.execute(select(func.count(Animal.id)))).scalar_one()

    # ステータス別
    rows = await session.execute(
        select(Animal.status, func.count(Animal.id)).group_by(Animal.status)
    )
    status_counts = {s: 0 for s in _KNOWN_STATUSES}
    for status, cnt in rows.all():
        status_counts[status] = cnt

    # 県別
    rows = await session.execute(
        select(Animal.prefecture, func.count(Animal.id)).group_by(Animal.prefecture)
    )
    by_prefecture = [
        {
            "prefecture": pref if pref is not None else _UNCATEGORIZED_LABEL,
            "count": cnt,
        }
        for pref, cnt in rows.all()
    ]
    by_prefecture.sort(key=lambda r: r["count"], reverse=True)

    # 種別
    rows = await session.execute(
        select(Animal.species, func.count(Animal.id)).group_by(Animal.species)
    )
    by_species = {species: cnt for species, cnt in rows.all()}

    # カテゴリ別
    rows = await session.execute(
        select(Animal.category, func.count(Animal.id)).group_by(Animal.category)
    )
    by_category = {category: cnt for category, cnt in rows.all()}

    # 画像ハッシュ
    img_total = (await session.execute(select(func.count(ImageHash.id)))).scalar_one()
    img_oldest = (await session.execute(select(func.min(ImageHash.created_at)))).scalar()
    img_newest = (await session.execute(select(func.max(ImageHash.created_at)))).scalar()

    return {
        "total_animals": total,
        "by_status": status_counts,
        "by_prefecture": by_prefecture,
        "by_species": by_species,
        "by_category": by_category,
        "image_hash_summary": {
            "total": img_total,
            "oldest": img_oldest.isoformat() if img_oldest else None,
            "newest": img_newest.isoformat() if img_newest else None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
