"""add_prefecture_to_animals

animals テーブルに prefecture カラムを追加し、既存データを source_url
ドメインから推定してバックフィル。

Revision ID: 9b1c2d3e4f5a
Revises: 8a9b0c1d2e3f
Create Date: 2026-05-04 14:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9b1c2d3e4f5a'
down_revision: Union[str, Sequence[str], None] = '8a9b0c1d2e3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "animals",
        sa.Column("prefecture", sa.String(length=20), nullable=True),
    )
    op.create_index("idx_animals_prefecture", "animals", ["prefecture"])

    # 既存データを source_url ドメインから推定してバックフィル
    op.execute(
        """
        UPDATE animals
        SET prefecture = CASE
            WHEN source_url LIKE '%kochi-apc.com%' THEN '高知県'
            WHEN source_url LIKE '%douai-tokushima.com%' THEN '徳島県'
            WHEN source_url LIKE '%kagawa%' THEN '香川県'
            WHEN source_url LIKE '%ehime%' THEN '愛媛県'
            ELSE prefecture
        END
        WHERE prefecture IS NULL
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_animals_prefecture", table_name="animals")
    op.drop_column("animals", "prefecture")
