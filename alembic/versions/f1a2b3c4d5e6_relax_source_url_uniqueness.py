"""relax source_url uniqueness on animals / animals_archive

岡山市の detail ページ URL が別個体に再利用される実例が確認された
(1D2026049 → 1D2025093)。同一 source_url を異なる個体が共有し得るため、
`animals.source_url` / `animals_archive.source_url` の UNIQUE 制約を
撤廃し、検索性能維持のための非ユニーク index のみ残す (T138)。

URL 再利用を検知した際は AnimalRepository.save_animal が旧レコードを
`animals_archive` へ移してから新レコードを `animals` に挿入するため、
通常運用では同一 URL の active 行は依然として高々1件になる。ただし
`animals_archive` 側は同一 URL が時系列で複数回アーカイブされ得るため
（URL が繰り返し再利用される自治体を想定）、こちらは UNIQUE を維持できない。

本番/CI は PostgreSQL のみ (backend.yml / data-collector.yml は
`postgres:15-alpine` サービス上で alembic upgrade head を実行する)。
テストは Base.metadata.create_all を直接使い alembic 経由では走らないため、
本 migration は PostgreSQL 専用の実装とする。

Revision ID: f1a2b3c4d5e6
Revises: 4f4daa168d2c
Create Date: 2026-09-09 00:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "4f4daa168d2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 元の create_animals_table / add_identity_fields_to_archive では制約名を
# 明示していないため、PostgreSQL のデフォルト命名規則 (`<table>_<column>_key`)
# に従う。
_ANIMALS_UNIQUE = "animals_source_url_key"
_ARCHIVE_UNIQUE = "animals_archive_source_url_key"


def upgrade() -> None:
    op.drop_constraint(_ANIMALS_UNIQUE, "animals", type_="unique")
    op.drop_constraint(_ARCHIVE_UNIQUE, "animals_archive", type_="unique")
    op.create_index("ix_animals_source_url", "animals", ["source_url"])
    op.create_index("ix_animals_archive_source_url", "animals_archive", ["source_url"])


def downgrade() -> None:
    op.drop_index("ix_animals_source_url", table_name="animals")
    op.drop_index("ix_animals_archive_source_url", table_name="animals_archive")
    op.create_unique_constraint(_ANIMALS_UNIQUE, "animals", ["source_url"])
    op.create_unique_constraint(_ARCHIVE_UNIQUE, "animals_archive", ["source_url"])
