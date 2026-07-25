"""add last_collected_at to animals and archive

収集がいつ行われたか(クロール日時)を記録する `last_collected_at` を追加する。

これまで DB には「収容日」(shelter_date、自治体側の保護開始日)しかなく、
「oneco 側の収集がいつ最後に成功したか」を示す情報が無かった。サイトの収集が
壊れて何日も更新が止まっていても、フロントには古いデータがそのまま
「最新情報」の顔で表示され続ける問題があった(2026-07-24 発覚)。

- save_animal が upsert のたびに現在時刻を設定する。
- 既存行は NULL のまま (going-forward で再収集時に付与される)。

Revision ID: 4f4daa168d2c
Revises: d0e1f2a3b4c5
Create Date: 2026-07-25 00:16:04.606584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f4daa168d2c'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "animals", sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "animals_archive",
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("animals_archive", "last_collected_at")
    op.drop_column("animals", "last_collected_at")
