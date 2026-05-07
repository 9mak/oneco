"""enable_rls_supabase_security

Supabase の "RLS not enabled on public table" 警告に対応。
全 public テーブルで Row Level Security を有効化し、anon ロール
（Supabase の公開 REST API 経由）からの読み取り専用アクセスのみを許可する。

書き込みは Cloud Run のバックエンド（postgres ロールでの直接接続）からのみ
行うため、anon に SELECT のみ付与し、INSERT/UPDATE/DELETE は拒否される。

PostgreSQL の RLS のみ。Supabase 以外（ローカル PG, SQLite）では create
されないため if_exists でガード。

Revision ID: a0b1c2d3e4f5
Revises: 9b1c2d3e4f5a
Create Date: 2026-05-07 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a0b1c2d3e4f5'
down_revision: Union[str, Sequence[str], None] = '9b1c2d3e4f5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# RLS を適用するテーブル一覧（全 public テーブル）
TABLES_PUBLIC_READ = [
    "animals",
    "animal_status_history",
    "animals_archive",
    "image_hashes",
]

TABLES_NO_PUBLIC_ACCESS = [
    "notification_users",
    "notification_preferences",
    "notification_history",
    "alembic_version",  # マイグレーション履歴 — anon 公開不要
]


def upgrade() -> None:
    """Upgrade schema - RLS 有効化と anon 用 SELECT ポリシー作成"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite 等では何もしない
        return

    for table in TABLES_PUBLIC_READ:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # 古い同名ポリシーがあれば落としてから作成（再実行可能にする）
        op.execute(f"DROP POLICY IF EXISTS public_read_{table} ON {table}")
        op.execute(
            f"""
            CREATE POLICY public_read_{table}
            ON {table}
            FOR SELECT
            USING (true)
            """
        )

    for table in TABLES_NO_PUBLIC_ACCESS:
        # 通知系は内部用。RLS 有効にするだけでポリシー無し → デフォルト deny
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Downgrade schema - RLS 無効化とポリシー削除"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in TABLES_PUBLIC_READ:
        op.execute(f"DROP POLICY IF EXISTS public_read_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    for table in TABLES_NO_PUBLIC_ACCESS:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
