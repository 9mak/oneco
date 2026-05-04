"""
SQLAlchemy データベースモデル定義

このモジュールは動物データの永続化のためのデータベーススキーマを定義します。
PostgreSQL を対象としていますが、テストでは SQLite も使用可能です。
"""

from datetime import date, datetime

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


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
    prefecture: str | None = Column(String(20), nullable=True, index=True)
    source_url: str = Column(Text, nullable=False, unique=True)

    # 準必須フィールド（デフォルト値あり）
    sex: str = Column(String(20), nullable=False, default="不明", index=True)
    category: str = Column(
        String(20),
        nullable=False,
        default="adoption",
        server_default="adoption",
        index=True,
    )

    # オプショナルフィールド
    age_months: int = Column(Integer, nullable=True)
    color: str = Column(String(100), nullable=True)
    size: str = Column(String(50), nullable=True)
    phone: str = Column(String(20), nullable=True)

    # JSON配列（PostgreSQLではJSONB、SQLiteではJSONとして扱う）
    image_urls: list[str] = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )

    # === animal-repository 拡張フィールド ===

    # ステータス管理フィールド
    status: str = Column(
        String(20),
        nullable=False,
        default="sheltered",
        server_default="sheltered",
        index=True,
    )
    status_changed_at: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    outcome_date: date | None = Column(
        Date,
        nullable=True,
    )

    # 画像永続化フィールド
    local_image_paths: list[str] = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )

    # ステータス履歴へのリレーション
    status_history = relationship(
        "AnimalStatusHistory",
        back_populates="animal",
        cascade="all, delete-orphan",
    )

    # 複合検索用インデックス
    __table_args__ = (
        Index("idx_animals_search", "species", "sex", "location", "category"),
        Index("idx_animals_status", "status"),
        Index("idx_animals_status_changed", "status_changed_at"),
        Index("idx_animals_outcome_date", "outcome_date"),
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現"""
        return (
            f"<Animal(id={self.id}, species={self.species}, "
            f"shelter_date={self.shelter_date}, location={self.location})>"
        )


class AnimalStatusHistory(Base):
    """
    動物ステータス履歴テーブル

    動物のステータス変更を追跡するためのテーブルモデル。
    各ステータス遷移を記録し、監査ログとして機能します。
    """

    __tablename__ = "animal_status_history"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # 外部キー
    animal_id: int = Column(
        Integer,
        ForeignKey("animals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ステータス遷移情報
    old_status: str = Column(String(20), nullable=False)
    new_status: str = Column(String(20), nullable=False)
    changed_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    changed_by: str | None = Column(String(100), nullable=True)

    # Animal へのリレーション
    animal = relationship("Animal", back_populates="status_history")

    # インデックス
    __table_args__ = (
        Index("idx_status_history_animal", "animal_id"),
        Index("idx_status_history_changed_at", "changed_at"),
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現"""
        return (
            f"<AnimalStatusHistory(id={self.id}, animal_id={self.animal_id}, "
            f"{self.old_status} → {self.new_status})>"
        )


class ImageHash(Base):
    """
    画像ハッシュテーブル

    画像の重複検出のためのハッシュ情報を管理するテーブルモデル。
    SHA-256 ハッシュと保存パスの対応を記録します。
    """

    __tablename__ = "image_hashes"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # ハッシュ情報
    hash: str = Column(String(64), nullable=False, unique=True, index=True)
    local_path: str = Column(Text, nullable=False)
    file_size: int = Column(Integer, nullable=False)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現"""
        return f"<ImageHash(id={self.id}, hash={self.hash[:8]}...)>"


class AnimalArchive(Base):
    """
    動物アーカイブテーブル

    アーカイブされた動物データを保持するためのテーブルモデル。
    アクティブテーブルと同一スキーマを持ち、読み取り専用アクセスを提供します。
    """

    __tablename__ = "animals_archive"

    # Primary Key
    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # 元のレコード情報
    original_id: int = Column(Integer, nullable=False, index=True)

    # 動物情報（animals テーブルと同一スキーマ）
    species: str = Column(String(50), nullable=False, index=True)
    sex: str = Column(String(20), nullable=False, default="不明")
    age_months: int | None = Column(Integer, nullable=True)
    color: str | None = Column(String(100), nullable=True)
    size: str | None = Column(String(50), nullable=True)
    shelter_date: date = Column(Date, nullable=False)
    location: str = Column(Text, nullable=False)
    phone: str | None = Column(String(20), nullable=True)
    image_urls: list[str] = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    local_image_paths: list[str] = Column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=list,
        server_default="[]",
    )
    source_url: str = Column(Text, nullable=False, unique=True)
    category: str = Column(String(20), nullable=False)
    status: str = Column(String(20), nullable=False)
    status_changed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    outcome_date: date | None = Column(Date, nullable=True)

    # アーカイブ情報
    archived_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現"""
        return (
            f"<AnimalArchive(id={self.id}, original_id={self.original_id}, species={self.species})>"
        )
