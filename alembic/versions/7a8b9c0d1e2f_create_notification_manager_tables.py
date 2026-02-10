"""create_notification_manager_tables

Revision ID: 7a8b9c0d1e2f
Revises: 6134989ff064
Create Date: 2026-01-24 12:00:00.000000

notification-manager用テーブルの作成:
- notification_users: LINEユーザー情報
- notification_preferences: ユーザー通知条件
- notification_history: 通知送信履歴

Requirements: 1.1, 1.3, 1.4, 5.1, 5.2, 5.3, 7.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7a8b9c0d1e2f'
down_revision: Union[str, Sequence[str], None] = '6134989ff064'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notification-manager tables."""
    # notification_users テーブル
    op.create_table(
        'notification_users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('line_user_id_encrypted', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('line_user_id_encrypted', name='uq_notification_users_line_user_id'),
    )

    # アクティブユーザー検索用のインデックス
    op.create_index(
        'idx_notification_users_line_user_id',
        'notification_users',
        ['line_user_id_encrypted']
    )
    op.create_index(
        'idx_notification_users_active',
        'notification_users',
        ['is_active'],
        postgresql_where=sa.text('is_active = true')
    )

    # notification_preferences テーブル
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('species', sa.String(20), nullable=True),
        sa.Column('prefectures', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('age_min_months', sa.Integer(), nullable=True),
        sa.Column('age_max_months', sa.Integer(), nullable=True),
        sa.Column('size', sa.String(20), nullable=True),
        sa.Column('sex', sa.String(20), nullable=True),
        sa.Column('notifications_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['notification_users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_notification_preferences_user_id'),
    )

    # アクティブな通知条件検索用のインデックス
    op.create_index(
        'idx_notification_preferences_active',
        'notification_preferences',
        ['notifications_enabled'],
        postgresql_where=sa.text('notifications_enabled = true')
    )

    # notification_history テーブル
    op.create_table(
        'notification_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('animal_source_url', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['notification_users.id'], ondelete='CASCADE'),
    )

    # 重複通知防止のユニークインデックス
    op.create_index(
        'idx_notification_history_user_url',
        'notification_history',
        ['user_id', 'animal_source_url'],
        unique=True
    )

    # 履歴検索用の日付インデックス
    op.create_index(
        'idx_notification_history_notified_at',
        'notification_history',
        ['notified_at']
    )


def downgrade() -> None:
    """Drop notification-manager tables."""
    # インデックス削除
    op.drop_index('idx_notification_history_notified_at', table_name='notification_history')
    op.drop_index('idx_notification_history_user_url', table_name='notification_history')
    op.drop_index('idx_notification_preferences_active', table_name='notification_preferences')
    op.drop_index('idx_notification_users_active', table_name='notification_users')
    op.drop_index('idx_notification_users_line_user_id', table_name='notification_users')

    # テーブル削除
    op.drop_table('notification_history')
    op.drop_table('notification_preferences')
    op.drop_table('notification_users')
