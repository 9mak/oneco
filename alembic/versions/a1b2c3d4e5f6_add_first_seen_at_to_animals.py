"""add first_seen_at to animals and archive

SNS 日次まとめ (T160) が「前日の新着」を判定する基準列 `first_seen_at`
(初回収集日時) を追加する。shelter_date (自治体側の収容日) は自治体ごとの
欠損・上書きバグ (T055) があり新着判定に使えないため、新設する。

- AnimalRepository._to_orm (新規行生成経路のみ) が現在時刻を設定する。
- 既存行は本 migration の実行時刻で backfill する (真の初回収集日ではない
  ため、日次まとめの初回投稿は移行翌日から意味を持つ。設計書 T151 参照)。
- animals_archive は active 側と同一スキーマを保つ既存方針 (models.py の
  AnimalArchive コメント) に従い同列を追加するが、nullable のまま backfill
  しない (旧アーカイブ行の初回収集日時は追跡していないため不明)。

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-09-11 00:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. nullable で追加
    op.add_column(
        "animals",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 2. 既存行を migration 実行時刻で backfill (server_default ではなく
    #    アプリ側から見える一貫した値にするため明示 UPDATE)
    op.execute("UPDATE animals SET first_seen_at = now() WHERE first_seen_at IS NULL")
    # 3. NOT NULL 化
    op.alter_column("animals", "first_seen_at", nullable=False)
    # 4. 検索用 index (日次まとめが範囲検索する列)
    op.create_index("idx_animals_first_seen_at", "animals", ["first_seen_at"])

    # animals_archive は同一スキーマ維持方針のため列だけ追加する。旧アーカイブ
    # 行の初回収集日時は不明なため backfill せず NULL のまま残す。
    op.add_column(
        "animals_archive",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("animals_archive", "first_seen_at")
    op.drop_index("idx_animals_first_seen_at", table_name="animals")
    op.drop_column("animals", "first_seen_at")
