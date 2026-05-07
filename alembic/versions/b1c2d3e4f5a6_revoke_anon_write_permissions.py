"""revoke_anon_write_permissions

Supabase Security Advisor の警告対応・第2弾。

Supabase デフォルトでは public schema のテーブルに対して anon ロールに
ALL（SELECT/INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER）が grant
されている。RLS policy で実際の操作は deny されるが、Linter は「anon
が書き込み権限を持っていること自体」を警告する。

このマイグレーションで anon ロールから書き込み権限を REVOKE し、
SELECT のみを必要なテーブルに限って付与する。authenticated ロール
（Supabase Auth ログインユーザー）も同様に絞る。

書き込みは Cloud Run の postgres ロール（直接接続）が常に行うため、
anon/authenticated に書き込み権限は不要。

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-05-07 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a0b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 公開読み取り対象テーブル
TABLES_PUBLIC_READ = [
    "animals",
    "animal_status_history",
    "animals_archive",
    "image_hashes",
]


def upgrade() -> None:
    """anon/authenticated から書き込み権限を REVOKE、SELECT のみ付与"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # public schema 配下の全テーブル/シーケンスから anon と authenticated の権限を全 REVOKE
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated")
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated")

    # 公開読み取り対象テーブルに SELECT を再付与（anon のみ。authenticated は今は使わない）
    for table in TABLES_PUBLIC_READ:
        op.execute(f"GRANT SELECT ON {table} TO anon")

    # 今後 alembic などが新しいテーブルを作っても anon にデフォルト ALL が付かないようにする
    # （Supabase の自動 grant をオフにするには bare table 単位で REVOKE するのが確実だが
    #  ここでは public への DEFAULT PRIVILEGES だけリセットしておく）
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated")


def downgrade() -> None:
    """元の Supabase デフォルトに戻す（ALL を anon/authenticated に再付与）"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated")
    op.execute("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated")
    op.execute("GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated")
