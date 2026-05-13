"""
管理ダッシュボード用の集計エンドポイント

X-Internal-Token 認証で保護される。フロントエンドの /admin が
NextAuth + GitHub OAuth でゲートした上で、サーバーサイドからこの
エンドポイントを叩いて集計データを取得する想定。
"""

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from src.data_collector.infrastructure.api.dependencies import SessionDep
from src.data_collector.infrastructure.api.routes import require_internal_token
from src.data_collector.infrastructure.database.models import Animal, ImageHash
from src.data_collector.llm.config import SiteConfigLoader

logger = logging.getLogger(__name__)

_SITES_YAML_PATH = Path(__file__).resolve().parents[3] / "data_collector" / "config" / "sites.yaml"

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
    status_counts = dict.fromkeys(_KNOWN_STATUSES, 0)
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
    by_species = dict(rows.all())

    # カテゴリ別
    rows = await session.execute(
        select(Animal.category, func.count(Animal.id)).group_by(Animal.category)
    )
    by_category = dict(rows.all())

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
                    await session.execute(select(func.count(Animal.id)).where(column.is_(None)))
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

    # 最新の収容日（DB 全体の MAX(shelter_date)）
    last_shelter_date_value = (
        await session.execute(select(func.max(Animal.shelter_date)))
    ).scalar()
    last_shelter_date = last_shelter_date_value.isoformat() if last_shelter_date_value else None

    # サイトカバレッジ: sites.yaml の全サイトに対し、DB に少なくとも1件の
    # animals.source_url が同一ホストで存在するサイト数をカウント
    site_coverage = _compute_site_coverage(await _list_db_hosts(session))

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
        "site_coverage": site_coverage,
        "last_shelter_date": last_shelter_date,
        "generated_at": datetime.now(UTC).isoformat(),
    }


async def _list_db_hosts(session) -> set[str]:
    """DB の animals.source_url から distinct なホスト集合を返す"""
    rows = await session.execute(select(Animal.source_url).distinct())
    hosts: set[str] = set()
    for (url,) in rows.all():
        host = urlparse(url).netloc
        if host:
            hosts.add(host)
    return hosts


def _compute_site_coverage(db_hosts: set[str]) -> dict:
    """sites.yaml の各サイトについて、DB に同一ホストの動物データがあるかを判定する。

    sites.yaml の load 失敗時は 0 を返してダッシュボードを壊さない。
    """
    try:
        config = SiteConfigLoader.load(_SITES_YAML_PATH)
    except Exception as e:
        logger.warning(f"sites.yaml load 失敗: {e}")
        return {"sites_total": 0, "sites_with_data": 0, "sites_without_data": 0}

    sites_total = len(config.sites)
    with_data = 0
    for site in config.sites:
        host = urlparse(str(site.list_url)).netloc
        if host and host in db_hosts:
            with_data += 1

    return {
        "sites_total": sites_total,
        "sites_with_data": with_data,
        "sites_without_data": sites_total - with_data,
    }
