"""add_category_column_to_animals

Revision ID: 6134989ff064
Revises: 33c0ccd7c108
Create Date: 2026-01-19 11:45:36.033104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6134989ff064'
down_revision: Union[str, Sequence[str], None] = '33c0ccd7c108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # カテゴリカラムを追加（デフォルト値 'adoption' で既存データを自動設定）
    op.add_column(
        'animals',
        sa.Column(
            'category',
            sa.String(20),
            nullable=False,
            server_default='adoption'
        )
    )

    # カテゴリカラムにインデックスを作成
    op.create_index('ix_animals_category', 'animals', ['category'])

    # 既存の複合インデックスを削除
    op.drop_index('idx_animals_search', table_name='animals')

    # カテゴリを含む新しい複合インデックスを作成
    op.create_index(
        'idx_animals_search',
        'animals',
        ['species', 'sex', 'location', 'category']
    )


def downgrade() -> None:
    """Downgrade schema."""
    # カテゴリを含む複合インデックスを削除
    op.drop_index('idx_animals_search', table_name='animals')

    # カテゴリなしの複合インデックスを再作成
    op.create_index(
        'idx_animals_search',
        'animals',
        ['species', 'sex', 'location']
    )

    # カテゴリインデックスを削除
    op.drop_index('ix_animals_category', table_name='animals')

    # カテゴリカラムを削除
    op.drop_column('animals', 'category')
