"""
SQLAlchemy データベースモデル定義

このモジュールは動物データの永続化のためのデータベーススキーマを定義します。
PostgreSQL を対象としていますが、テストでは SQLite も使用可能です。
"""

from typing import List
from datetime import date
from sqlalchemy import Column, Integer, String, Date, Text, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy の宣言的ベースクラス"""

    pass


class Animal(Base):
    """
    動物データテーブル

    保護動物の情報を永続化するためのテーブルモデル。
    AnimalData (Pydantic) との相互変換をサポートし、
    upsert 操作のために source_url にユニーク制約を持ちます。
    """

    __tablename__ = "animals"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # 必須フィールド
    species: str = Column(String(50), nullable=False, index=True)
    shelter_date: date = Column(Date, nullable=False, index=True)
    location: str = Column(Text, nullable=False, index=True)
    source_url: str = Column(Text, nullable=False, unique=True)

    # 準必須フィールド（デフォルト値あり）
    sex: str = Column(String(20), nullable=False, default="不明", index=True)

    # オプショナルフィールド
    age_months: int = Column(Integer, nullable=True)
    color: str = Column(String(100), nullable=True)
    size: str = Column(String(50), nullable=True)
    phone: str = Column(String(20), nullable=True)

    # JSON配列（PostgreSQLではJSONB、SQLiteではJSONとして扱う）
    image_urls: List[str] = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )

    # 複合検索用インデックス
    __table_args__ = (Index("idx_animals_search", "species", "sex", "location"),)

    def __repr__(self) -> str:
        """デバッグ用の文字列表現"""
        return (
            f"<Animal(id={self.id}, species={self.species}, "
            f"shelter_date={self.shelter_date}, location={self.location})>"
        )
