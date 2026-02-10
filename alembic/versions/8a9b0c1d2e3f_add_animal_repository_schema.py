"""add_animal_repository_schema

animal-repository 機能のためのスキーマ拡張:
- animals テーブルに status, status_changed_at, outcome_date, local_image_paths カラムを追加
- animal_status_history テーブルを作成
- image_hashes テーブルを作成
- animals_archive テーブルを作成

Revision ID: 8a9b0c1d2e3f
Revises: 7a8b9c0d1e2f
Create Date: 2026-01-27 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8a9b0c1d2e3f'
down_revision: Union[str, Sequence[str], None] = '7a8b9c0d1e2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # === 1. animals テーブルに新規カラムを追加 ===

    # status カラム（デフォルト 'sheltered'）
    op.add_column(
        'animals',
        sa.Column(
            'status',
            sa.String(20),
            nullable=False,
            server_default='sheltered'
        )
    )

    # status_changed_at カラム
    op.add_column(
        'animals',
        sa.Column(
            'status_changed_at',
            sa.DateTime(timezone=True),
            nullable=True
        )
    )

    # outcome_date カラム
    op.add_column(
        'animals',
        sa.Column(
            'outcome_date',
            sa.Date(),
            nullable=True
        )
    )

    # local_image_paths カラム（JSONB / JSON）
    op.add_column(
        'animals',
        sa.Column(
            'local_image_paths',
            sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'),
            nullable=False,
            server_default='[]'
        )
    )

    # animals テーブルのインデックス追加
    op.create_index('idx_animals_status', 'animals', ['status'])
    op.create_index('idx_animals_status_changed', 'animals', ['status_changed_at'])
    op.create_index('idx_animals_outcome_date', 'animals', ['outcome_date'])

    # === 2. animal_status_history テーブルを作成 ===

    op.create_table(
        'animal_status_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'animal_id',
            sa.Integer(),
            sa.ForeignKey('animals.id', ondelete='CASCADE'),
            nullable=False
        ),
        sa.Column('old_status', sa.String(20), nullable=False),
        sa.Column('new_status', sa.String(20), nullable=False),
        sa.Column(
            'changed_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        ),
        sa.Column('changed_by', sa.String(100), nullable=True),
        sa.CheckConstraint(
            "old_status IN ('sheltered', 'adopted', 'returned', 'deceased')",
            name='chk_status_history_old_status'
        ),
        sa.CheckConstraint(
            "new_status IN ('sheltered', 'adopted', 'returned', 'deceased')",
            name='chk_status_history_new_status'
        )
    )

    op.create_index('idx_status_history_animal', 'animal_status_history', ['animal_id'])
    op.create_index('idx_status_history_changed_at', 'animal_status_history', ['changed_at'])

    # === 3. image_hashes テーブルを作成 ===

    op.create_table(
        'image_hashes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('hash', sa.String(64), nullable=False, unique=True),
        sa.Column('local_path', sa.Text(), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        )
    )

    op.create_index('idx_image_hashes_hash', 'image_hashes', ['hash'])

    # === 4. animals_archive テーブルを作成 ===

    op.create_table(
        'animals_archive',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('original_id', sa.Integer(), nullable=False),
        sa.Column('species', sa.String(50), nullable=False),
        sa.Column('sex', sa.String(20), nullable=False, server_default='不明'),
        sa.Column('age_months', sa.Integer(), nullable=True),
        sa.Column('color', sa.String(100), nullable=True),
        sa.Column('size', sa.String(50), nullable=True),
        sa.Column('shelter_date', sa.Date(), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column(
            'image_urls',
            sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'),
            nullable=False,
            server_default='[]'
        ),
        sa.Column(
            'local_image_paths',
            sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'),
            nullable=False,
            server_default='[]'
        ),
        sa.Column('source_url', sa.Text(), nullable=False, unique=True),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('status_changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome_date', sa.Date(), nullable=True),
        sa.Column(
            'archived_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now()
        )
    )

    op.create_index('idx_archive_species', 'animals_archive', ['species'])
    op.create_index('idx_archive_archived_at', 'animals_archive', ['archived_at'])
    op.create_index('idx_archive_original_id', 'animals_archive', ['original_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # === 4. animals_archive テーブルを削除 ===
    op.drop_index('idx_archive_original_id', table_name='animals_archive')
    op.drop_index('idx_archive_archived_at', table_name='animals_archive')
    op.drop_index('idx_archive_species', table_name='animals_archive')
    op.drop_table('animals_archive')

    # === 3. image_hashes テーブルを削除 ===
    op.drop_index('idx_image_hashes_hash', table_name='image_hashes')
    op.drop_table('image_hashes')

    # === 2. animal_status_history テーブルを削除 ===
    op.drop_index('idx_status_history_changed_at', table_name='animal_status_history')
    op.drop_index('idx_status_history_animal', table_name='animal_status_history')
    op.drop_table('animal_status_history')

    # === 1. animals テーブルからカラムを削除 ===
    op.drop_index('idx_animals_outcome_date', table_name='animals')
    op.drop_index('idx_animals_status_changed', table_name='animals')
    op.drop_index('idx_animals_status', table_name='animals')
    op.drop_column('animals', 'local_image_paths')
    op.drop_column('animals', 'outcome_date')
    op.drop_column('animals', 'status_changed_at')
    op.drop_column('animals', 'status')
