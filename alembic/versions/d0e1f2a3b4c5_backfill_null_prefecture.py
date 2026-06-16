"""backfill_null_prefecture

2026-05-22 (commit e3d7166) の site_config.prefecture フォールバック導入より前に
収集され prefecture=NULL のまま残った歴史的 orphan レコード (約 36 件) を、
source_url のホストから正しい都道府県に補完する。

スキーマ変更は無く、データのみを冪等に UPDATE する (既に prefecture が入った行は
WHERE 句で除外)。当該レコードは source_url が 404 (ソース消滅) で再収集されない
ため、本バックフィルなしには都道府県 LP / フィルタで永久に不可視のままになる。
詳細・ホスト→都道府県マッピングは prefecture_backfill モジュール参照。

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-17 08:30:00.000000

"""

from collections.abc import Sequence

from alembic import op
from src.data_collector.infrastructure.database.prefecture_backfill import (
    backfill_null_prefectures,
)

revision: str = "d0e1f2a3b4c5"
down_revision: str | Sequence[str] | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """NULL prefecture を host→prefecture で補完する (冪等・データのみ)。"""
    backfill_null_prefectures(op.get_bind())


def downgrade() -> None:
    """データ補完の一方向マイグレーション。

    どの行が補完前に NULL だったかは保持しないため、元の状態は復元しない (no-op)。
    """
    pass
