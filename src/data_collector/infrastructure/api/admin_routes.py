"""
管理ダッシュボード用の集計エンドポイント

X-Internal-Token 認証で保護される。フロントエンドの /admin が
NextAuth + GitHub OAuth でゲートした上で、サーバーサイドからこの
エンドポイントを叩いて集計データを取得する想定。
"""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from src.data_collector.infrastructure.api.dependencies import SessionDep
from src.data_collector.infrastructure.api.routes import require_internal_token
from src.data_collector.infrastructure.database.models import Animal, ImageHash

admin_router = APIRouter(prefix="/admin", tags=["admin"])

_KNOWN_STATUSES = ("sheltered", "adopted", "returned", "deceased")
_UNCATEGORIZED_LABEL = "(未分類)"
_PREFECTURES_TOTAL = 47
_QUALITY_FIELDS = ("prefecture", "image_urls", "color", "size", "phone", "age_months")


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

    # 県別カバー率（None や (未分類) を除く実県数）
    prefectures_covered = sum(
        1 for row in by_prefecture if row["prefecture"] != _UNCATEGORIZED_LABEL
    )

    # フィールド欠損率
    field_missing_ratio: dict[str, float] = {}
    if total > 0:
        # JSON配列の長さ取得は dialect 別。Postgres は JSONB, SQLite は JSON。
        dialect_name = session.bind.dialect.name if session.bind else "sqlite"
        if dialect_name == "postgresql":
            json_array_length = func.jsonb_array_length
        else:
            json_array_length = func.json_array_length

        for field_name in _QUALITY_FIELDS:
            column = getattr(Animal, field_name)
            if field_name == "image_urls":
                # JSON 配列が空 or NULL を欠損扱い
                missing = (
                    await session.execute(
                        select(func.count(Animal.id)).where(
                            (column.is_(None)) | (json_array_length(column) == 0)
                        )
                    )
                ).scalar_one()
            else:
                missing = (
                    await session.execute(
                        select(func.count(Animal.id)).where(column.is_(None))
                    )
                ).scalar_one()
            field_missing_ratio[field_name] = round(missing / total, 4)

    # 直近7日間の収容（liveness 指標）
    today = date.today()
    seven_days_ago = today - timedelta(days=7)
    added_recently = (
        await session.execute(
            select(func.count(Animal.id)).where(Animal.shelter_date >= seven_days_ago)
        )
    ).scalar_one()

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
        "quality": {
            "prefectures_covered": prefectures_covered,
            "prefectures_total": _PREFECTURES_TOTAL,
            "field_missing_ratio": field_missing_ratio,
            "added_in_last_7days": added_recently,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
