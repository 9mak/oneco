"""revoke_usage_from_public_role

Supabase の schema public への USAGE 権限は PUBLIC 疑似ロール（全ロールが
継承する仮想ロール）経由で付与されているため、anon から直接 REVOKE しても
継承で残る。PUBLIC 疑似ロール自体から REVOKE する必要がある。

前バージョン d3e4f5a6b7c8 で `REVOKE USAGE ... FROM anon, authenticated`
としたが、anon は元々直接付与されていなかったため no-op だった。本マイグレーションで
PUBLIC からも REVOKE する。

これで anon は public schema 自体に入れなくなる → Supabase の REST/GraphQL
からは何も見えない（最強の遮断）。

Cloud Run は postgres ロール直接接続なので影響なし。
service_role と postgres は USAGE を持つため Supabase 内部処理は継続。

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-07 10:55:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """PUBLIC 疑似ロールから schema public への USAGE を REVOKE"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("REVOKE USAGE ON SCHEMA public FROM PUBLIC")


def downgrade() -> None:
    """元に戻す（PUBLIC に USAGE を再付与）"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
