"""add source_site to animals

収集元サイトの識別名 (SiteConfig.name) を記録する `source_site` を追加する。
ソースから消えた動物を「サイト単位」で安全に同期削除するために使う
(1ドメインに複数サイトが同居するため source_url では分離できない)。

- save_animal が収集のたびに source_site を設定する。
- 収集が成功し、かつ取得件数が 0 でないサイトについて、今回見つからなかった
  source_url の動物を削除する (= ソースから消えた)。
- 既存行は NULL のまま (going-forward で再収集時に付与される)。デプロイ後、
  健全な収集を1回確認してから `DELETE FROM animals WHERE source_site IS NULL`
  を手動実行すれば、過去の取り残し (もういないのに残っている行) を一掃できる。

Revision ID: a7b8c9d0e1f2
Revises: e4f5a6b7c8d9
Create Date: 2026-06-02 16:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("animals", sa.Column("source_site", sa.String(length=255), nullable=True))
    op.create_index("idx_animals_source_site", "animals", ["source_site"])


def downgrade() -> None:
    op.drop_index("idx_animals_source_site", table_name="animals")
    op.drop_column("animals", "source_site")
