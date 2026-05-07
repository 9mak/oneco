"""disable_graphql_exposure

Supabase Security Advisor の Warning 「Public Can See Object in GraphQL Schema」対応。

oneco は Supabase の自動 REST/GraphQL エンドポイントを一切使わず、Cloud Run の
バックエンド API（postgres ロールでの直接接続）経由のみでデータにアクセスする。

そのため public schema のテーブルが Supabase の GraphQL エンドポイントで anon
（公開）に露出していること自体が不要なリスクとなる。pg_graphql の COMMENT 制御
で対象テーブルを GraphQL スキーマから除外する。

これでも anon ロールには SELECT 権限を残しているため、postgres 直接接続経由
（Cloud Run）からは引き続き読み取り可能。あくまで Supabase の自動 GraphQL
エンドポイントからの参照を遮断する。

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-07 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# GraphQL 露出を遮断する全 public テーブル
TABLES_TO_HIDE_FROM_GRAPHQL = [
    "animals",
    "animal_status_history",
    "animals_archive",
    "image_hashes",
    "notification_users",
    "notification_preferences",
    "notification_history",
    "alembic_version",
]


def upgrade() -> None:
    """pg_graphql の COMMENT メタデータで対象テーブルを GraphQL スキーマから除外"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in TABLES_TO_HIDE_FROM_GRAPHQL:
        # pg_graphql のメタデータ規約: COMMENT で `@graphql({"totally_skip": true})`
        # を付与すると当該テーブルが GraphQL スキーマから完全に除外される
        op.execute(
            f"""COMMENT ON TABLE {table} IS '@graphql({{"totally_skip": true}})'"""
        )


def downgrade() -> None:
    """COMMENT を空文字に戻して GraphQL スキーマに再露出"""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for table in TABLES_TO_HIDE_FROM_GRAPHQL:
        op.execute(f"COMMENT ON TABLE {table} IS NULL")
