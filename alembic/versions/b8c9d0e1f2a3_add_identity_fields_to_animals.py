"""add_identity_fields_to_animals

animals テーブルに個体識別4フィールド (breed/name/management_number/description)
を追加する。全て nullable・additive で後方互換（既存行は NULL 埋め、server_default
不要）。breed は検索（カナ正規化）で使うため索引を付与。

列長は DataNormalizer の長さ定数と厳密に一致させること
(breed=50 / name=100 / management_number=50。不一致は INSERT 失敗で1サイト全損)。

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-10 02:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("animals", sa.Column("breed", sa.String(length=50), nullable=True))
    op.add_column("animals", sa.Column("name", sa.String(length=100), nullable=True))
    op.add_column("animals", sa.Column("management_number", sa.String(length=50), nullable=True))
    op.add_column("animals", sa.Column("description", sa.Text(), nullable=True))
    op.create_index("idx_animals_breed", "animals", ["breed"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_animals_breed", table_name="animals")
    op.drop_column("animals", "description")
    op.drop_column("animals", "management_number")
    op.drop_column("animals", "name")
    op.drop_column("animals", "breed")
