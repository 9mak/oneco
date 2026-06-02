"""add last_seen_at to animals

収集で最後にソースサイトで確認できた日時を記録する `last_seen_at` を追加する。
ソースから消えた動物 (= last_seen_at が古い) を公開面で非表示にするための鮮度指標。

- save_animal が upsert のたびに now を設定する。
- 公開の一覧/地図/統計は last_seen_at が直近のものだけを表示する。
- 既存行は移行時点を最後の確認時刻として now で backfill (移行直後に既存掲載が
  一斉に消えないようにするため)。以降、再収集されない動物は自然に古くなり非表示化する。

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-06-02 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "animals",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_animals_last_seen_at", "animals", ["last_seen_at"])
    # 既存行を now で backfill (移行直後に既存掲載が一斉非表示になるのを防ぐ)
    op.execute("UPDATE animals SET last_seen_at = now() WHERE last_seen_at IS NULL")


def downgrade() -> None:
    op.drop_index("idx_animals_last_seen_at", table_name="animals")
    op.drop_column("animals", "last_seen_at")
