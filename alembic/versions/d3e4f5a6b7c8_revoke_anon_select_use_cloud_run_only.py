"""revoke_anon_select_use_cloud_run_only

Supabase の Public Can See Object in GraphQL Schema 警告を完全解消。

oneco は Supabase の anon キー経由（REST/GraphQL）を一切使わず、
Cloud Run の postgres ロール直接接続のみで動作する。そのため anon ロール
には何の権限も与える必要がない。

前バージョン (b1c2d3e4f5a6) で書き込み権限は既に剥奪済みだが、SELECT が
残っていたため Linter が GraphQL 経由の公開を検出していた。SELECT も
REVOKE することで anon のアクセス可能性を完全に排除する。

更に schema public への USAGE 権限も REVOKE して、anon が公開スキーマ自体に
入れないようにする（最も強い遮断）。

Cloud Run は postgres ロールでアクセスするため影響なし。

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-07 10:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 元々 anon SELECT を許可していた public-read テーブル
TABLES_PUBLIC_READ = [
    "animals",
    "animal_status_history",
    "animals_archive",
    "image_hashes",
]


def _supabase_roles_exist(bind) -> bool:
    """anon ロールが存在する場合のみ Supabase 用 migration を実行する"""
    result = bind.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'anon'")).first()
    return result is not None


def upgrade() -> None:
    """anon ロールから SELECT を REVOKE、schema USAGE も REVOKE で完全遮断"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _supabase_roles_exist(bind):
        return

    # 1. anon の SELECT 権限を全テーブルから剥奪
    for table in TABLES_PUBLIC_READ:
        op.execute(f"REVOKE SELECT ON {table} FROM anon")

    # 2. RLS の SELECT ポリシーは形だけ残しておく（権限がないので発動しないが
    #    将来 SELECT を再付与した時の安全策として残す）

    # 3. schema public の USAGE 権限を anon から剥奪（最も強い遮断）
    #    これで Supabase の REST/GraphQL から public スキーマが見えなくなる
    op.execute("REVOKE USAGE ON SCHEMA public FROM anon, authenticated")


def downgrade() -> None:
    """schema USAGE と SELECT を anon に再付与"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    if not _supabase_roles_exist(bind):
        return

    op.execute("GRANT USAGE ON SCHEMA public TO anon, authenticated")
    for table in TABLES_PUBLIC_READ:
        op.execute(f"GRANT SELECT ON {table} TO anon")
