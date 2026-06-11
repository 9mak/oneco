"""add_identity_fields_to_archive

animals_archive テーブルに個体識別4フィールド (breed/name/management_number/description)
を追加する。active 側 (animals) の b8c9d0e1f2a3 と同一構成・additive nullable。

アーカイブテーブルは公開しないため breed の索引は付けない (容量節約)。

列長は DataNormalizer の長さ定数および Animal テーブルと厳密に一致させること
(breed=50 / name=100 / management_number=50。不一致は INSERT 失敗でアーカイブ全損)。

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-11 10:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("animals_archive", sa.Column("breed", sa.String(length=50), nullable=True))
    op.add_column("animals_archive", sa.Column("name", sa.String(length=100), nullable=True))
    op.add_column(
        "animals_archive", sa.Column("management_number", sa.String(length=50), nullable=True)
    )
    op.add_column("animals_archive", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("animals_archive", "description")
    op.drop_column("animals_archive", "management_number")
    op.drop_column("animals_archive", "name")
    op.drop_column("animals_archive", "breed")
